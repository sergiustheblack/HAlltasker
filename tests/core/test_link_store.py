"""Tests for the per-pair link namespaces (schema 3, contract-checked)."""

from __future__ import annotations

import datetime as dt
import logging

import pytest

from custom_components.halltasker.core.link_store import (
    LinkCompatibilityError,
    LinkStore,
    PairContract,
)
from custom_components.halltasker.core.model import (
    CanonicalTask,
    Link,
    Pair,
    Snapshot,
    SyncPair,
)

from .fakes import FakeStorage

NOW = dt.datetime(2026, 11, 27, 12, 0, tzinfo=dt.UTC)

NODE_A = "3f1c9a0e2b7d4c51a8e6f0b9d2c4e7a1"
NODE_B = "7d0e5b2c9a4f4b1e8c3a6d9f2e5b8c1a"
PAIR_ID = "9b2e4c7a1f3d4e8b9a6c5d2e1f0a3b4c"

PAIR = Pair(id=PAIR_ID, name="Sync", a=NODE_A, b=NODE_B, mapping=())
PAIR_SWAPPED = Pair(id=PAIR_ID, name="Sync", a=NODE_B, b=NODE_A, mapping=())
CONTRACT_AB = PairContract(binding="binding-ab", slots={"title": "fp-title", "status": "fp-status"})
CONTRACT_ADDITIVE = PairContract(
    binding="binding-ab",
    slots={"title": "fp-title", "status": "fp-status", "due": "fp-due"},
)
CONTRACT_OTHER_BINDING = PairContract(binding="binding-other", slots={"title": "fp-title"})
CONTRACT_CHANGED_SLOT = PairContract(binding="binding-ab", slots={"title": "fp-title-2"})

PAIR_AB = SyncPair(id="ab", a="todo.a", b="todo.b")
PAIR_BC = SyncPair(id="bc", a="todo.b", b="todo.c")


def _link(canonical_id: str, node: str, external_id: str, **kwargs: object) -> Link:
    return Link(canonical_id=canonical_id, node=node, external_id=external_id, **kwargs)  # type: ignore[arg-type]


def _store_with_schema3_data(data: dict) -> LinkStore:
    storage = FakeStorage(data={"schema": 3, "pairs": {PAIR_ID: data}})
    store = LinkStore(storage)
    return store


async def test_load_empty_storage_starts_with_no_namespaces() -> None:
    store = LinkStore(FakeStorage())
    await store.load()
    assert store.pair_ids() == []
    namespace = store.for_pair(PAIR, CONTRACT_AB)
    assert namespace.nodes == (NODE_A, NODE_B)
    assert namespace.pair_initialized(PAIR_ID) is False


async def test_for_pair_creates_namespace_with_stored_contract() -> None:
    store = LinkStore(FakeStorage())
    namespace = store.for_pair(PAIR, CONTRACT_AB)
    assert namespace.contract == CONTRACT_AB
    assert store.to_dict()["pairs"][PAIR_ID]["binding"] == "binding-ab"


async def test_for_pair_returns_the_same_object_for_the_same_id() -> None:
    store = LinkStore(FakeStorage())
    assert store.for_pair(PAIR, CONTRACT_AB) is store.for_pair(PAIR, CONTRACT_AB)
    assert store.pair_ids() == [PAIR_ID]


async def test_binding_mismatch_raises_and_keeps_namespace_untouched() -> None:
    storage = FakeStorage()
    store = LinkStore(storage)
    namespace = store.for_pair(PAIR, CONTRACT_AB)
    namespace.upsert(_link("c1", NODE_A, "uid-1"))
    before = store.to_dict()

    with pytest.raises(LinkCompatibilityError):
        store.for_pair(PAIR, CONTRACT_OTHER_BINDING)

    assert namespace.get(NODE_A, "uid-1") is not None
    assert store.to_dict() == before


async def test_changed_slot_fingerprint_raises_and_blocks_writes() -> None:
    store = LinkStore(FakeStorage())
    namespace = store.for_pair(PAIR, CONTRACT_AB)
    namespace.upsert(_link("c1", NODE_A, "uid-1"))

    with pytest.raises(LinkCompatibilityError):
        store.for_pair(PAIR, CONTRACT_CHANGED_SLOT)
    assert store.incompatible_pairs({PAIR_ID: CONTRACT_CHANGED_SLOT}) == {PAIR_ID}
    namespace.upsert(_link("c2", NODE_B, "uid-2"))
    assert namespace.get(NODE_B, "uid-2") is not None


async def test_incompatible_pairs_reports_binding_and_slot_mismatches() -> None:
    store = LinkStore(FakeStorage())
    store.for_pair(PAIR, CONTRACT_AB)
    other = Pair(id="other", name="Other", a=NODE_A, b=NODE_B, mapping=())
    store.for_pair(other, CONTRACT_AB)

    incompatible = store.incompatible_pairs(
        {
            PAIR_ID: CONTRACT_OTHER_BINDING,
            "other": CONTRACT_CHANGED_SLOT,
        }
    )
    assert incompatible == {PAIR_ID, "other"}


async def test_incompatible_pairs_ignores_unknown_and_compatible_pairs() -> None:
    store = LinkStore(FakeStorage())
    store.for_pair(PAIR, CONTRACT_AB)
    result = store.incompatible_pairs({PAIR_ID: CONTRACT_AB, "ghost": CONTRACT_AB})
    assert result == frozenset()


async def test_additive_slot_contract_merges_and_preserves_links() -> None:
    storage = FakeStorage()
    store = LinkStore(storage)
    namespace = store.for_pair(PAIR, CONTRACT_AB)
    namespace.upsert(_link("c1", NODE_A, "uid-1"))

    merged = store.for_pair(PAIR, CONTRACT_ADDITIVE)

    assert merged is namespace
    assert merged.contract == CONTRACT_ADDITIVE
    assert merged.get(NODE_A, "uid-1") is not None
    await store.save()
    assert storage.data is not None
    assert storage.data["pairs"][PAIR_ID]["slots"]["due"] == "fp-due"


async def test_removed_stored_slot_is_incompatible() -> None:
    store = LinkStore(FakeStorage())
    store.for_pair(PAIR, CONTRACT_ADDITIVE)
    shrunk = PairContract(binding="binding-ab", slots={"title": "fp-title", "status": "fp-status"})
    with pytest.raises(LinkCompatibilityError):
        store.for_pair(PAIR, shrunk)
    assert store.incompatible_pairs({PAIR_ID: shrunk}) == {PAIR_ID}


async def test_retained_namespace_reintroduction_requires_confirmation() -> None:
    storage = FakeStorage()
    store = LinkStore(storage)
    namespace = store.for_pair(PAIR, CONTRACT_AB)
    namespace.upsert(_link("c1", NODE_A, "uid-1"))
    namespace.mark_pair_initialized(PAIR_ID)
    await store.save()

    # The pair is removed from the configuration; its namespace is kept untouched.
    assert PAIR_ID in store.pair_ids()

    # Reintroduction with an incompatible contract cannot bypass confirmation.
    with pytest.raises(LinkCompatibilityError):
        store.for_pair(PAIR, CONTRACT_OTHER_BINDING)
    assert namespace.get(NODE_A, "uid-1") is not None

    store.reset(PAIR_ID)
    fresh = store.for_pair(PAIR, CONTRACT_OTHER_BINDING)
    assert fresh is not namespace
    assert fresh.get(NODE_A, "uid-1") is None
    assert fresh.pair_initialized(PAIR_ID) is False


async def test_reset_drops_the_namespace_and_next_for_pair_creates_empty() -> None:
    store = LinkStore(FakeStorage())
    namespace = store.for_pair(PAIR, CONTRACT_AB)
    namespace.upsert(_link("c1", NODE_A, "uid-1"))

    store.reset(PAIR_ID)
    assert store.pair_ids() == []
    fresh = store.for_pair(PAIR, CONTRACT_AB)
    assert fresh is not namespace
    assert fresh.get(NODE_A, "uid-1") is None


async def test_reset_of_unknown_pair_is_a_noop() -> None:
    store = LinkStore(FakeStorage())
    store.reset("ghost")
    assert store.pair_ids() == []


async def test_to_dict_round_trips_through_load() -> None:
    storage = FakeStorage()
    store = LinkStore(storage)
    ns = store.for_pair(PAIR, CONTRACT_AB)
    ns.mark_pair_initialized(PAIR_ID)
    task = CanonicalTask(title="x", due=dt.date(2026, 11, 5))
    snapshot = Snapshot.of(task)
    ns.upsert(
        _link(
            "c1",
            NODE_A,
            "uid-1",
            last_observed=snapshot,
            last_synced=snapshot,
            tombstone=True,
            tombstone_at=NOW.isoformat(),
        )
    )
    ns.upsert(_link("c2", NODE_B, "uid-2"))
    await store.save()

    restored = LinkStore(storage)
    await restored.load()
    assert restored.pair_ids() == [PAIR_ID]
    assert restored.to_dict() == store.to_dict()
    data = restored.to_dict()
    payload = data["pairs"][PAIR_ID]
    assert data["schema"] == 3
    assert payload["nodes"] == [NODE_A, NODE_B]
    assert payload["kind"] == "task"
    assert payload["binding"] == "binding-ab"
    assert payload["slots"] == {"title": "fp-title", "status": "fp-status"}
    ns2 = restored.for_pair(PAIR, CONTRACT_AB)
    assert ns2.pair_initialized(PAIR_ID) is True
    assert ns2.get(NODE_A, "uid-1") == ns.get(NODE_A, "uid-1")
    assert ns2.get(NODE_B, "uid-2") is not None


async def test_swapping_a_and_b_keeps_the_contract_namespace() -> None:
    store = LinkStore(FakeStorage())
    namespace = store.for_pair(PAIR, CONTRACT_AB)
    assert store.for_pair(PAIR_SWAPPED, CONTRACT_AB) is namespace


async def test_schema2_data_is_discarded_with_warning(caplog) -> None:
    storage = FakeStorage(
        data={
            "schema": 2,
            "pairs": {
                "ab": {
                    "nodes": ["todo.a", "todo.b"],
                    "initialized": True,
                    "links": [_link("c1", "todo.a", "uid-1").to_dict()],
                }
            },
        }
    )
    store = LinkStore(storage)
    with caplog.at_level(logging.WARNING):
        await store.load()
    assert "outdated and was discarded" in caplog.text
    assert store.pair_ids() == []


async def test_schema1_v1_0_data_is_discarded_with_warning(caplog) -> None:
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


async def test_namespace_save_writes_the_whole_store() -> None:
    storage = FakeStorage()
    store = LinkStore(storage)
    store.for_pair(PAIR, CONTRACT_AB).upsert(_link("c1", NODE_A, "uid-1"))
    other = Pair(id="other", name="Other", a=NODE_A, b=NODE_B, mapping=())
    store.for_pair(other, CONTRACT_AB).upsert(_link("c2", NODE_B, "uid-2"))
    await store.for_pair(PAIR, CONTRACT_AB).save()
    assert storage.data is not None
    assert set(storage.data["pairs"]) == {PAIR_ID, "other"}
    assert storage.saves == 1


# --- v1.3 §9 facade retained for callers not yet ported to contracts ---


def test_facade_for_pair_returns_the_same_object_for_the_same_id() -> None:
    store = LinkStore(FakeStorage())
    assert store.for_pair(PAIR_AB) is store.for_pair(PAIR_AB)
    assert store.pair_ids() == ["ab"]


def test_facade_repointed_pair_resets_its_namespace_with_warning(caplog) -> None:
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


def test_facade_swapping_a_and_b_keeps_the_namespace() -> None:
    store = LinkStore(FakeStorage())
    namespace = store.for_pair(PAIR_AB)
    assert store.for_pair(SyncPair(id="ab", a="todo.b", b="todo.a")) is namespace


def test_facade_same_item_in_two_pairs_gives_independent_links() -> None:
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


def test_facade_removed_pair_namespace_is_kept_untouched() -> None:
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
    old = "2026-10-01T00:00:00+00:00"
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
