"""Tests for engine execution and saving (SPEC §7 scenarios A1-A9)."""

from __future__ import annotations

import datetime as dt

from custom_components.halltasker.core.engine import SyncEngine
from custom_components.halltasker.core.link_store import LinkStore
from custom_components.halltasker.core.model import (
    CanonicalTask,
    Capabilities,
    DirectionRule,
    Link,
    Snapshot,
    SyncPair,
)
from custom_components.halltasker.plugins.base import NodeUnavailable
from custom_components.halltasker.plugins.registry import PluginRegistry

from .fakes import FULL_CAPS, FakePlugin, FakeStorage

MSK = dt.timezone(dt.timedelta(hours=3))
NOW = dt.datetime(2026, 10, 25, 12, 0, tzinfo=MSK)

NODE_A = "fake.a"
NODE_B = "fake.b"
TASK = CanonicalTask(title="x", description="d", due=dt.date(2026, 10, 5))

PAIR = SyncPair(id="p", a=NODE_A, b=NODE_B)
DATE_ONLY_CAPS = Capabilities(create=True, update=True, delete=True, due="date", description=True)


class FailingCreatePlugin(FakePlugin):
    """A plugin whose create always fails, to test error isolation."""

    async def create(self, node: str, task: CanonicalTask, known_ids: frozenset[str]) -> str:
        raise RuntimeError("create failed")


class FailOnceDeletePlugin(FakePlugin):
    async def delete(self, node: str, external_id: str) -> None:
        if not hasattr(self, "delete_failed"):
            self.delete_failed = True
            raise RuntimeError("delete failed")
        await super().delete(node, external_id)


class FailOnceUpdatePlugin(FakePlugin):
    fail_next_update = False

    async def update(
        self,
        node: str,
        external_id: str,
        task: CanonicalTask,
        changed: frozenset[str],
    ) -> None:
        if self.fail_next_update:
            self.fail_next_update = False
            raise RuntimeError("update failed")
        await super().update(node, external_id, task, changed)


class FailingStorage(FakeStorage):
    async def async_save(self, data: dict) -> None:
        raise RuntimeError("storage failed")


def _engine(plugin: FakePlugin | None = None):
    storage = FakeStorage()
    store = LinkStore(storage).for_pair(PAIR)
    plugin = plugin if plugin is not None else FakePlugin()
    plugin.caps[NODE_A] = FULL_CAPS
    plugin.caps[NODE_B] = FULL_CAPS
    registry = PluginRegistry()
    registry.register(plugin)
    engine = SyncEngine(store, registry, clock=lambda: NOW)
    return engine, store, storage, plugin


async def _seed_linked(plugin: FakePlugin, engine: SyncEngine) -> None:
    """One task present in A, then synced so that both sides hold a linked copy."""
    plugin.add(NODE_A, TASK)
    result = await engine.run_pair(PAIR, dry_run=False)
    assert result.ok is True


def _only(tasks: dict[str, CanonicalTask]) -> CanonicalTask:
    assert len(tasks) == 1
    return next(iter(tasks.values()))


async def test_a1_create_in_a_appears_in_b() -> None:
    engine, store, storage, plugin = _engine()
    plugin.add(NODE_A, TASK)
    result = await engine.run_pair(PAIR, dry_run=False)
    assert result.ok is True
    assert [(a.kind, a.node) for a in result.actions_applied] == [
        ("link", NODE_A),
        ("create", NODE_B),
    ]
    assert _only(plugin.items[NODE_B]) == TASK
    assert len(store.links_for_pair(NODE_A, NODE_B)) == 1
    assert storage.saves >= 2


async def test_a2_rename_in_b_changes_in_a_and_repeat_cycle_writes_nothing() -> None:
    engine, _store, storage, plugin = _engine()
    await _seed_linked(plugin, engine)
    ext_b = next(iter(plugin.items[NODE_B]))
    plugin.items[NODE_B][ext_b] = CanonicalTask(
        title="renamed", description="d", due=dt.date(2026, 10, 5)
    )
    saves_before = storage.saves
    result = await engine.run_pair(PAIR, dry_run=False)
    assert result.ok is True
    assert _only(plugin.items[NODE_A]).title == "renamed"
    assert storage.saves == saves_before + 1

    saves_before = storage.saves
    first_repeat = await engine.run_pair(PAIR, dry_run=False)
    assert first_repeat.actions_applied == []
    assert storage.saves == saves_before + 1  # one echo update is persisted once

    saves_settled = storage.saves
    second_repeat = await engine.run_pair(PAIR, dry_run=False)
    assert second_repeat.actions_applied == []
    assert storage.saves == saves_settled  # a converged cycle writes nothing


async def test_a3_complete_and_uncomplete_propagate() -> None:
    engine, _store, _storage, plugin = _engine()
    await _seed_linked(plugin, engine)
    ext_a = next(iter(plugin.items[NODE_A]))
    plugin.items[NODE_A][ext_a] = CanonicalTask(
        title="x", description="d", status="done", due=dt.date(2026, 10, 5)
    )
    await engine.run_pair(PAIR, dry_run=False)
    assert _only(plugin.items[NODE_B]).status == "done"
    plugin.items[NODE_A][ext_a] = TASK
    await engine.run_pair(PAIR, dry_run=False)
    assert _only(plugin.items[NODE_B]).status == "open"


async def test_a4_deletion_with_delete_true_removes_in_b() -> None:
    engine, store, _storage, plugin = _engine()
    await _seed_linked(plugin, engine)
    ext_a = next(iter(plugin.items[NODE_A]))
    del plugin.items[NODE_A][ext_a]
    result = await engine.run_pair(PAIR, dry_run=False)
    assert result.ok is True
    assert plugin.items[NODE_B] == {}
    canonical = store.links_for_pair(NODE_A, NODE_B)
    assert all(link.tombstone for links in canonical.values() for link in links.values())


async def test_a4_deletion_with_delete_soft_marks_done_in_b() -> None:
    engine, _store, _storage, plugin = _engine()
    await _seed_linked(plugin, engine)
    pair = SyncPair(id="p", a=NODE_A, b=NODE_B, a_to_b=DirectionRule(delete="soft"))
    ext_a = next(iter(plugin.items[NODE_A]))
    del plugin.items[NODE_A][ext_a]
    await engine.run_pair(pair, dry_run=False)
    assert _only(plugin.items[NODE_B]).status == "done"


async def test_a4_deletion_with_delete_false_keeps_b_and_recreates_nothing() -> None:
    engine, _store, _storage, plugin = _engine()
    await _seed_linked(plugin, engine)
    pair = SyncPair(id="p", a=NODE_A, b=NODE_B, a_to_b=DirectionRule(delete="false"))
    ext_a = next(iter(plugin.items[NODE_A]))
    del plugin.items[NODE_A][ext_a]
    result = await engine.run_pair(pair, dry_run=False)
    assert result.ok is True
    assert _only(plugin.items[NODE_B]) == TASK
    assert plugin.items[NODE_A] == {}
    assert all(a.kind != "create" for a in result.actions_applied)


async def test_a5_non_overlapping_changes_apply_on_both_sides() -> None:
    engine, _store, _storage, plugin = _engine()
    await _seed_linked(plugin, engine)
    ext_a = next(iter(plugin.items[NODE_A]))
    ext_b = next(iter(plugin.items[NODE_B]))
    plugin.items[NODE_A][ext_a] = CanonicalTask(
        title="from a", description="d", due=dt.date(2026, 10, 5)
    )
    plugin.items[NODE_B][ext_b] = CanonicalTask(
        title="x", description="d", due=dt.date(2026, 10, 7)
    )
    await engine.run_pair(PAIR, dry_run=False)
    assert _only(plugin.items[NODE_A]).title == "from a"
    assert _only(plugin.items[NODE_A]).due == dt.date(2026, 10, 7)
    assert _only(plugin.items[NODE_B]).title == "from a"
    assert _only(plugin.items[NODE_B]).due == dt.date(2026, 10, 7)


async def test_a6_overlapping_title_prefers_a() -> None:
    engine, _store, _storage, plugin = _engine()
    await _seed_linked(plugin, engine)
    ext_a = next(iter(plugin.items[NODE_A]))
    ext_b = next(iter(plugin.items[NODE_B]))
    plugin.items[NODE_A][ext_a] = CanonicalTask(
        title="title a", description="d", due=dt.date(2026, 10, 5)
    )
    plugin.items[NODE_B][ext_b] = CanonicalTask(
        title="title b", description="d", due=dt.date(2026, 10, 5)
    )
    await engine.run_pair(PAIR, dry_run=False)
    assert _only(plugin.items[NODE_A]).title == "title a"
    assert _only(plugin.items[NODE_B]).title == "title a"


async def test_a7_due_datetime_downgrades_to_date_without_echo_changes() -> None:
    engine, _store, storage, plugin = _engine()
    plugin.caps[NODE_B] = DATE_ONLY_CAPS
    task = CanonicalTask(
        title="x", description="d", due=dt.datetime(2026, 10, 5, 23, 30, tzinfo=MSK)
    )
    plugin.add(NODE_A, task)
    await engine.run_pair(PAIR, dry_run=False)
    assert _only(plugin.items[NODE_B]).due == dt.date(2026, 10, 5)

    saves_before = storage.saves
    first_repeat = await engine.run_pair(PAIR, dry_run=False)
    assert first_repeat.actions_applied == []
    assert storage.saves == saves_before + 1  # one echo update is persisted once

    saves_settled = storage.saves
    second_repeat = await engine.run_pair(PAIR, dry_run=False)
    assert second_repeat.actions_applied == []
    assert storage.saves == saves_settled  # a converged cycle writes nothing


async def test_a8_dry_run_lists_actions_and_writes_nothing() -> None:
    engine, store, storage, plugin = _engine()
    plugin.add(NODE_A, TASK)
    result = await engine.run_pair(PAIR, dry_run=True)
    assert result.ok is True
    assert len(result.actions_planned) == 2
    assert result.actions_applied == []
    assert plugin.items.get(NODE_B, {}) == {}
    assert store.links_for_pair(NODE_A, NODE_B) == {}
    assert storage.saves == 0


async def test_a9_merge_initial_sync_links_identical_tasks() -> None:
    engine, _store, _storage, plugin = _engine()
    plugin.add(NODE_A, TASK)
    plugin.add(NODE_B, TASK)
    result = await engine.run_pair(PAIR, dry_run=False)
    assert [(a.kind, a.node) for a in result.actions_applied] == [
        ("link", NODE_A),
        ("link", NODE_B),
    ]
    assert len(plugin.items[NODE_A]) == 1
    assert len(plugin.items[NODE_B]) == 1
    assert all(call[0] != "create" for call in plugin.calls)


async def test_failed_create_does_not_block_other_actions() -> None:
    engine, store, _storage, plugin = _engine(FailingCreatePlugin())
    ext_a = plugin.add(NODE_A, TASK)
    ext_b = plugin.add(NODE_B, TASK)
    canonical_id = store.new_canonical_id()
    snapshot = Snapshot.of(TASK)
    for node, ext in ((NODE_A, ext_a), (NODE_B, ext_b)):
        store.upsert(
            Link(
                canonical_id=canonical_id,
                node=node,
                external_id=ext,
                last_observed=snapshot,
                last_written=snapshot,
                last_synced=snapshot,
            )
        )
    store.mark_pair_initialized(PAIR.id)
    plugin.add(NODE_A, CanonicalTask(title="second"))
    plugin.items[NODE_A][ext_a] = CanonicalTask(
        title="renamed", description="d", due=dt.date(2026, 10, 5)
    )
    result = await engine.run_pair(PAIR, dry_run=False)
    applied_kinds = [(action.kind, action.node) for action in result.actions_applied]
    assert ("update", NODE_B) in applied_kinds
    assert plugin.items[NODE_B][ext_b].title == "renamed"
    assert any(action.kind == "create" for action, _err in result.actions_failed)


class WriteThenFailCreatePlugin(FakePlugin):
    """Writes the item but fails the uid lookup, like a lagging todo backend."""

    async def create(self, node: str, task: CanonicalTask, known_ids: frozenset[str]) -> str:
        await super().create(node, task, known_ids)
        raise NodeUnavailable("created item not found")


async def test_a12_orphan_from_failed_uid_lookup_is_linked_not_duplicated() -> None:
    engine, _store, _storage, plugin = _engine(WriteThenFailCreatePlugin())
    plugin.add(NODE_A, TASK)

    first = await engine.run_pair(PAIR, dry_run=False)
    assert any(action.kind == "create" for action, _err in first.actions_failed)
    assert len(plugin.items[NODE_A]) == 1
    assert len(plugin.items[NODE_B]) == 1

    second = await engine.run_pair(PAIR, dry_run=False)
    assert [(a.kind, a.node) for a in second.actions_applied] == [("link", NODE_B)]
    assert len(plugin.items[NODE_A]) == 1
    assert len(plugin.items[NODE_B]) == 1
    assert second.links == 2

    third = await engine.run_pair(PAIR, dry_run=False)
    assert third.actions_applied == []


async def test_a11_blocked_change_is_accepted_locally_and_does_not_leak() -> None:
    pair = SyncPair(id="p", a=NODE_A, b=NODE_B, a_to_b=DirectionRule(update=False))
    storage = FakeStorage()
    store = LinkStore(storage).for_pair(pair)
    plugin = FakePlugin()
    plugin.caps[NODE_A] = FULL_CAPS
    plugin.caps[NODE_B] = FULL_CAPS
    registry = PluginRegistry()
    registry.register(plugin)
    engine = SyncEngine(store, registry, clock=lambda: NOW)

    ext_a = plugin.add(NODE_A, TASK)
    ext_b = plugin.add(NODE_B, TASK)
    canonical_id = store.new_canonical_id()
    snapshot = Snapshot.of(TASK)
    for node, ext in ((NODE_A, ext_a), (NODE_B, ext_b)):
        store.upsert(
            Link(
                canonical_id=canonical_id,
                node=node,
                external_id=ext,
                last_observed=snapshot,
                last_written=snapshot,
                last_synced=snapshot,
            )
        )
    store.mark_pair_initialized(pair.id)

    plugin.items[NODE_A][ext_a] = CanonicalTask(
        title="renamed", description="d", due=dt.date(2026, 10, 5)
    )
    saves_before = storage.saves
    blocked = await engine.run_pair(pair, dry_run=False)
    assert blocked.ok is True
    assert blocked.actions_applied == []
    assert storage.saves == saves_before + 1  # the accepted change is saved once

    saves_settled = storage.saves
    repeated = await engine.run_pair(pair, dry_run=False)
    assert repeated.actions_applied == []
    assert storage.saves == saves_settled  # not reported again

    plugin.items[NODE_B][ext_b] = CanonicalTask(
        title="x", description="d", due=dt.date(2026, 10, 7)
    )
    merged = await engine.run_pair(pair, dry_run=False)
    assert [(a.kind, a.node) for a in merged.actions_applied] == [("update", NODE_A)]
    assert merged.actions_applied[0].changed == frozenset({"due"})
    assert _only(plugin.items[NODE_A]).title == "renamed"
    assert _only(plugin.items[NODE_A]).due == dt.date(2026, 10, 7)
    assert _only(plugin.items[NODE_B]).title == "x"


async def test_tombstone_purge_keeps_live_item_and_drops_gone_one() -> None:
    pair = SyncPair(id="p", a=NODE_A, b=NODE_B, a_to_b=DirectionRule(delete="false"))
    storage = FakeStorage()
    store = LinkStore(storage).for_pair(pair)
    plugin = FakePlugin()
    plugin.caps[NODE_A] = FULL_CAPS
    plugin.caps[NODE_B] = FULL_CAPS
    registry = PluginRegistry()
    registry.register(plugin)
    now = {"t": NOW}
    engine = SyncEngine(store, registry, clock=lambda: now["t"])

    ext_a = plugin.add(NODE_A, TASK)
    ext_b = plugin.add(NODE_B, TASK)
    canonical_id = store.new_canonical_id()
    snapshot = Snapshot.of(TASK)
    for node, ext in ((NODE_A, ext_a), (NODE_B, ext_b)):
        store.upsert(
            Link(
                canonical_id=canonical_id,
                node=node,
                external_id=ext,
                last_observed=snapshot,
                last_written=snapshot,
                last_synced=snapshot,
            )
        )
    store.mark_pair_initialized(pair.id)

    del plugin.items[NODE_A][ext_a]
    deleted = await engine.run_pair(pair, dry_run=False)
    assert deleted.ok is True
    assert _only(plugin.items[NODE_B]) == TASK  # delete: false keeps the item

    now["t"] = NOW + dt.timedelta(days=31)
    purged_cycle = await engine.run_pair(pair, dry_run=False)

    assert purged_cycle.ok is True
    assert purged_cycle.actions_applied == []  # nothing re-created
    assert _only(plugin.items[NODE_B]) == TASK
    assert plugin.items[NODE_A] == {}
    remaining = store.links_of(canonical_id)
    assert set(remaining) == {NODE_B}  # the gone X link is purged, the live Y kept
    assert remaining[NODE_B].tombstone is True


async def test_failed_delete_skips_tombstones_and_retries_next_cycle() -> None:
    engine, store, _storage, plugin = _engine(FailOnceDeletePlugin())
    await _seed_linked(plugin, engine)
    ext_a = next(iter(plugin.items[NODE_A]))
    del plugin.items[NODE_A][ext_a]

    first = await engine.run_pair(PAIR, dry_run=False)
    assert [action.kind for action, _error in first.actions_failed] == ["delete"]
    assert _only(plugin.items[NODE_B]) == TASK
    assert not any(
        link.tombstone
        for links in store.links_for_pair(NODE_A, NODE_B).values()
        for link in links.values()
    )

    second = await engine.run_pair(PAIR, dry_run=False)
    assert [action.kind for action in second.actions_applied] == [
        "delete",
        "tombstone",
        "tombstone",
    ]
    assert plugin.items[NODE_B] == {}


async def test_failed_soft_delete_skips_tombstones_and_retries_next_cycle() -> None:
    engine, store, _storage, plugin = _engine(FailOnceUpdatePlugin())
    await _seed_linked(plugin, engine)
    pair = SyncPair(id="p", a=NODE_A, b=NODE_B, a_to_b=DirectionRule(delete="soft"))
    ext_a = next(iter(plugin.items[NODE_A]))
    del plugin.items[NODE_A][ext_a]
    plugin.fail_next_update = True

    first = await engine.run_pair(pair, dry_run=False)
    assert [action.kind for action, _error in first.actions_failed] == ["soft_delete"]
    assert _only(plugin.items[NODE_B]).status == "open"
    assert not any(
        link.tombstone
        for links in store.links_for_pair(NODE_A, NODE_B).values()
        for link in links.values()
    )

    second = await engine.run_pair(pair, dry_run=False)
    assert [action.kind for action in second.actions_applied] == [
        "soft_delete",
        "tombstone",
        "tombstone",
    ]
    assert _only(plugin.items[NODE_B]).status == "done"


async def test_storage_save_error_returns_failed_result() -> None:
    store = LinkStore(FailingStorage()).for_pair(PAIR)
    plugin = FakePlugin()
    plugin.caps[NODE_A] = FULL_CAPS
    plugin.caps[NODE_B] = FULL_CAPS
    registry = PluginRegistry()
    registry.register(plugin)
    engine = SyncEngine(store, registry, clock=lambda: NOW)
    plugin.add(NODE_A, TASK)

    result = await engine.run_pair(PAIR, dry_run=False)
    assert result.ok is False
    assert result.error == "RuntimeError: storage failed"
