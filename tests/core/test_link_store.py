"""Tests for the per-pair link namespaces."""

from __future__ import annotations

import datetime as dt
import logging

import pytest

from custom_components.halltasker.core.link_store import LinkStore
from custom_components.halltasker.core.model import CanonicalTask, Link, Snapshot, SyncPair

from .fakes import FakeStorage

NOW = dt.datetime(2026, 10, 26, 12, 0, tzinfo=dt.UTC)

PAIR_AB = SyncPair(id="ab", a="todo.a", b="todo.b")
PAIR_BC = SyncPair(id="bc", a="todo.b", b="todo.c")


def _link(canonical_id: str, node: str, external_id: str, **kwargs: object) -> Link:
    return Link(canonical_id=canonical_id, node=node, external_id=external_id, **kwargs)  # type: ignore[arg-type]


async def test_load_empty_storage_starts_with_no_namespaces() -> None:
    store = LinkStore(FakeStorage())
    await store.load()
    assert store.pair_ids() == []
    namespace = store.for_pair(PAIR_AB)
    assert namespace.nodes == ("todo.a", "todo.b")
    assert namespace.pair_initialized("ab") is False


async def test_same_item_in_two_pairs_gives_independent_links() -> None:
    store = LinkStore(FakeStorage())
    ns_ab = store.for_pair(PAIR_AB)
    ns_bc = store.for_pair(PAIR_BC)
    ab_link = _link("c1", "todo.b", "uid-1")
    bc_link = _link("c9", "todo.b", "uid-1")
    ns_ab.upsert(ab_link)
    ns_bc.upsert(bc_link)

    assert ns_ab.get("todo.b", "uid-1") is ab_link
    assert ns_bc.get("todo.b", "uid-1") is bc_link
    assert ns_ab.links_for_pair("todo.a", "todo.b") == {"c1": {"todo.b": ab_link}}
    assert ns_bc.links_for_pair("todo.b", "todo.c") == {"c9": {"todo.b": bc_link}}


def test_for_pair_returns_the_same_object_for_the_same_id() -> None:
    store = LinkStore(FakeStorage())
    assert store.for_pair(PAIR_AB) is store.for_pair(PAIR_AB)
    assert store.pair_ids() == ["ab"]


def test_repointed_pair_resets_its_namespace_with_warning(caplog) -> None:
    store = LinkStore(FakeStorage())
    namespace = store.for_pair(PAIR_AB)
    namespace.upsert(_link("c1", "todo.a", "uid-1"))
    namespace.mark_pair_initialized("ab")

    with caplog.at_level(logging.WARNING):
        repointed = store.for_pair(SyncPair(id="ab", a="todo.x", b="todo.b"))

    assert repointed is not namespace
    assert repointed.get("todo.a", "uid-1") is None
    assert repointed.pair_initialized("ab") is False
    assert "its links were reset" in caplog.text


def test_swapping_a_and_b_keeps_the_namespace() -> None:
    store = LinkStore(FakeStorage())
    namespace = store.for_pair(PAIR_AB)
    swapped = store.for_pair(SyncPair(id="ab", a="todo.b", b="todo.a"))
    assert swapped is namespace


async def test_v1_0_storage_format_is_discarded_with_warning(caplog) -> None:
    storage = FakeStorage(
        data={
            "links": [_link("c1", "todo.a", "uid-1").to_dict()],
            "initialized_pairs": ["ab"],
        }
    )
    store = LinkStore(storage)
    with caplog.at_level(logging.WARNING):
        await store.load()
    assert "outdated and was discarded" in caplog.text
    assert store.pair_ids() == []


async def test_to_dict_round_trips_through_load() -> None:
    storage = FakeStorage()
    store = LinkStore(storage)
    ns_ab = store.for_pair(PAIR_AB)
    ns_ab.mark_pair_initialized("ab")
    task = CanonicalTask(title="x", due=dt.date(2026, 10, 5))
    snapshot = Snapshot.of(task)
    ns_ab.upsert(
        _link(
            "c1",
            "todo.a",
            "uid-1",
            last_observed=snapshot,
            last_synced=snapshot,
            tombstone=True,
            tombstone_at=NOW.isoformat(),
        )
    )
    ns_bc = store.for_pair(PAIR_BC)
    ns_bc.upsert(_link("c2", "todo.b", "uid-2"))
    await store.save()

    restored = LinkStore(storage)
    await restored.load()
    assert restored.pair_ids() == ["ab", "bc"]
    assert restored.to_dict() == store.to_dict()
    ns = restored.for_pair(PAIR_AB)
    assert ns.pair_initialized("ab") is True
    assert ns.get("todo.a", "uid-1") == ns_ab.get("todo.a", "uid-1")
    assert restored.for_pair(PAIR_BC).pair_initialized("bc") is False


def test_removed_pair_namespace_is_kept_untouched() -> None:
    store = LinkStore(FakeStorage())
    ns_ab = store.for_pair(PAIR_AB)
    ns_ab.upsert(_link("c1", "todo.a", "uid-1"))
    store.for_pair(PAIR_BC)
    assert store.pair_ids() == ["ab", "bc"]
    assert store.for_pair(PAIR_AB).get("todo.a", "uid-1") is not None


def test_pair_initialized_rejects_foreign_pair_id() -> None:
    namespace = LinkStore(FakeStorage()).for_pair(PAIR_AB)
    with pytest.raises(ValueError, match="bc"):
        namespace.pair_initialized("bc")
    with pytest.raises(ValueError, match="bc"):
        namespace.mark_pair_initialized("bc")


def test_purge_tombstones_respects_presence_and_age() -> None:
    store = LinkStore(FakeStorage())
    namespace = store.for_pair(PAIR_AB)
    old = "2026-09-01T00:00:00+00:00"
    namespace.upsert(_link("c1", "todo.a", "uid-gone", tombstone=True, tombstone_at=old))
    namespace.upsert(_link("c2", "todo.a", "uid-kept", tombstone=True, tombstone_at=old))
    namespace.upsert(
        _link(
            "c3",
            "todo.a",
            "uid-fresh",
            tombstone=True,
            tombstone_at=(NOW - dt.timedelta(days=5)).isoformat(),
        )
    )
    namespace.upsert(_link("c4", "todo.a", "uid-live"))

    removed = namespace.purge_tombstones(
        now=NOW, present={"todo.a": {"uid-kept", "uid-live", "uid-fresh"}}
    )

    assert removed == 1
    assert namespace.get("todo.a", "uid-gone") is None
    assert namespace.get("todo.a", "uid-kept") is not None
    assert namespace.get("todo.a", "uid-fresh") is not None
    assert namespace.get("todo.a", "uid-live") is not None


async def test_namespace_save_writes_the_whole_store() -> None:
    storage = FakeStorage()
    store = LinkStore(storage)
    store.for_pair(PAIR_AB).upsert(_link("c1", "todo.a", "uid-1"))
    store.for_pair(PAIR_BC).upsert(_link("c2", "todo.b", "uid-2"))
    await store.for_pair(PAIR_AB).save()
    assert storage.data is not None
    assert set(storage.data["pairs"]) == {"ab", "bc"}
    assert storage.saves == 1
