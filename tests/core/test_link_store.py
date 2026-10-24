"""Tests for the link store."""

from __future__ import annotations

import datetime as dt

from custom_components.halltasker.core.link_store import LinkStore
from custom_components.halltasker.core.model import CanonicalTask, Link, Snapshot

from .fakes import FakeStorage

NOW = dt.datetime(2026, 10, 25, 12, 0, tzinfo=dt.UTC)


def _link(canonical_id: str, node: str, external_id: str, **kwargs: object) -> Link:
    return Link(canonical_id=canonical_id, node=node, external_id=external_id, **kwargs)  # type: ignore[arg-type]


async def test_load_empty_storage_starts_clean() -> None:
    store = LinkStore(FakeStorage())
    await store.load()
    assert store.get("todo.a", "uid-1") is None
    assert store.links_of("c1") == {}
    assert store.links_for_pair("todo.a", "todo.b") == {}
    assert store.pair_initialized("p") is False


async def test_upsert_then_get_and_links_of_return_the_link() -> None:
    store = LinkStore(FakeStorage())
    link = _link("c1", "todo.a", "uid-1")
    store.upsert(link)
    assert store.get("todo.a", "uid-1") is link
    assert store.links_of("c1") == {"todo.a": link}
    assert store.get("todo.a", "uid-2") is None


async def test_upsert_with_new_external_id_drops_the_old_index_entry() -> None:
    store = LinkStore(FakeStorage())
    store.upsert(_link("c1", "todo.a", "uid-1"))
    replacement = _link("c1", "todo.a", "uid-2")
    store.upsert(replacement)
    assert store.get("todo.a", "uid-1") is None
    assert store.get("todo.a", "uid-2") is replacement
    assert store.links_of("c1") == {"todo.a": replacement}


async def test_links_for_pair_returns_tasks_linked_to_at_least_one_node() -> None:
    store = LinkStore(FakeStorage())
    a1 = _link("c1", "todo.a", "uid-1")
    b1 = _link("c1", "todo.b", "uid-2")
    a2 = _link("c2", "todo.a", "uid-3")
    store.upsert(a1)
    store.upsert(b1)
    store.upsert(a2)
    store.upsert(_link("c3", "todo.c", "uid-4"))
    result = store.links_for_pair("todo.a", "todo.b")
    assert result == {
        "c1": {"todo.a": a1, "todo.b": b1},
        "c2": {"todo.a": a2},
    }


async def test_save_then_load_restores_links_and_initialized_pairs() -> None:
    storage = FakeStorage()
    store = LinkStore(storage)
    await store.load()
    task = CanonicalTask(title="x", due=dt.date(2026, 10, 5))
    link = _link(
        "c1",
        "todo.a",
        "uid-1",
        last_observed=Snapshot.of(task),
        last_synced=Snapshot.of(task),
    )
    store.upsert(link)
    store.mark_pair_initialized("p1")
    await store.save()

    restored = LinkStore(storage)
    await restored.load()
    assert restored.get("todo.a", "uid-1") == link
    assert restored.links_for_pair("todo.a", "todo.b") == {"c1": {"todo.a": link}}
    assert restored.pair_initialized("p1") is True


async def test_purge_tombstones_removes_only_old_tombstones() -> None:
    store = LinkStore(FakeStorage())
    old_dead = _link(
        "c1", "todo.a", "uid-1", tombstone=True, tombstone_at="2026-09-01T00:00:00+00:00"
    )
    fresh_dead = _link(
        "c2",
        "todo.a",
        "uid-2",
        tombstone=True,
        tombstone_at=(NOW - dt.timedelta(days=5)).isoformat(),
    )
    alive = _link("c3", "todo.b", "uid-3")
    for link in (old_dead, fresh_dead, alive):
        store.upsert(link)

    removed = store.purge_tombstones(now=NOW)

    assert removed == 1
    assert store.get("todo.a", "uid-1") is None
    assert store.get("todo.a", "uid-2") is fresh_dead
    assert store.get("todo.b", "uid-3") is alive


def test_new_canonical_id_is_unique_hex() -> None:
    store = LinkStore(FakeStorage())
    first = store.new_canonical_id()
    second = store.new_canonical_id()
    assert len(first) == 32 and all(c in "0123456789abcdef" for c in first)
    assert first != second
