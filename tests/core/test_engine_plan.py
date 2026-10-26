"""Tests for the engine plan (no writes)."""

from __future__ import annotations

import datetime as dt

from custom_components.halltasker.core.engine import SyncEngine
from custom_components.halltasker.core.link_store import LinkStore, PairLinks
from custom_components.halltasker.core.model import (
    CanonicalTask,
    DirectionRule,
    Link,
    Snapshot,
    SyncPair,
)
from custom_components.halltasker.plugins.registry import PluginRegistry

from .fakes import FULL_CAPS, FakePlugin, FakeStorage

MSK = dt.timezone(dt.timedelta(hours=3))
NOW = dt.datetime(2026, 10, 25, 12, 0, tzinfo=MSK)

NODE_A = "fake.a"
NODE_B = "fake.b"
TASK = CanonicalTask(title="x", description="d", due=dt.date(2026, 10, 5))

PAIR = SyncPair(id="p", a=NODE_A, b=NODE_B)


def _engine() -> tuple[SyncEngine, PairLinks, FakePlugin]:
    store = LinkStore(FakeStorage()).for_pair(PAIR)
    plugin = FakePlugin()
    plugin.caps[NODE_A] = FULL_CAPS
    plugin.caps[NODE_B] = FULL_CAPS
    registry = PluginRegistry()
    registry.register(plugin)
    engine = SyncEngine(store, registry, clock=lambda: NOW)
    return engine, store, plugin


def _link_both_sides(store: PairLinks, task: CanonicalTask, ext_a: str, ext_b: str) -> str:
    canonical_id = store.new_canonical_id()
    snapshot = Snapshot.of(task)
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
    return canonical_id


def _kinds(result) -> list[tuple[str, str]]:
    return [(action.kind, action.node) for action in result.actions_planned]


async def test_new_item_in_a_plans_create_in_b() -> None:
    engine, store, plugin = _engine()
    plugin.add(NODE_A, TASK)
    store.mark_pair_initialized(PAIR.id)
    result = await engine.run_pair(PAIR, dry_run=True)
    assert result.ok is True
    assert _kinds(result) == [("link", NODE_A), ("create", NODE_B)]
    assert result.actions_planned[1].task == TASK


async def test_change_in_a_plans_update_in_b() -> None:
    engine, store, plugin = _engine()
    ext_a = plugin.add(NODE_A, TASK)
    ext_b = plugin.add(NODE_B, TASK)
    _link_both_sides(store, TASK, ext_a, ext_b)
    store.mark_pair_initialized(PAIR.id)
    changed_task = CanonicalTask(title="renamed", description="d", due=dt.date(2026, 10, 5))
    plugin.items[NODE_A][ext_a] = changed_task
    result = await engine.run_pair(PAIR, dry_run=True)
    assert _kinds(result) == [("update", NODE_B)]
    action = result.actions_planned[0]
    assert action.external_id == ext_b
    assert action.changed == frozenset({"title"})
    assert action.task == changed_task


async def test_status_only_change_plans_complete() -> None:
    engine, store, plugin = _engine()
    ext_a = plugin.add(NODE_A, TASK)
    ext_b = plugin.add(NODE_B, TASK)
    _link_both_sides(store, TASK, ext_a, ext_b)
    store.mark_pair_initialized(PAIR.id)
    plugin.items[NODE_A][ext_a] = CanonicalTask(
        title="x", description="d", status="done", due=dt.date(2026, 10, 5)
    )
    result = await engine.run_pair(PAIR, dry_run=True)
    assert _kinds(result) == [("complete", NODE_B)]


async def test_deletion_with_delete_true_plans_delete_and_tombstones() -> None:
    engine, store, plugin = _engine()
    ext_a = plugin.add(NODE_A, TASK)
    ext_b = plugin.add(NODE_B, TASK)
    _link_both_sides(store, TASK, ext_a, ext_b)
    store.mark_pair_initialized(PAIR.id)
    del plugin.items[NODE_A][ext_a]
    result = await engine.run_pair(PAIR, dry_run=True)
    assert _kinds(result) == [("delete", NODE_B), ("tombstone", NODE_A), ("tombstone", NODE_B)]


async def test_deletion_with_delete_false_plans_tombstones_only() -> None:
    engine, store, plugin = _engine()
    ext_a = plugin.add(NODE_A, TASK)
    ext_b = plugin.add(NODE_B, TASK)
    _link_both_sides(store, TASK, ext_a, ext_b)
    store.mark_pair_initialized(PAIR.id)
    del plugin.items[NODE_A][ext_a]
    pair = SyncPair(id="p", a=NODE_A, b=NODE_B, a_to_b=DirectionRule(delete="false"))
    result = await engine.run_pair(pair, dry_run=True)
    assert _kinds(result) == [("tombstone", NODE_A), ("tombstone", NODE_B)]


async def test_deletion_with_delete_soft_plans_soft_delete() -> None:
    engine, store, plugin = _engine()
    ext_a = plugin.add(NODE_A, TASK)
    ext_b = plugin.add(NODE_B, TASK)
    _link_both_sides(store, TASK, ext_a, ext_b)
    store.mark_pair_initialized(PAIR.id)
    del plugin.items[NODE_A][ext_a]
    pair = SyncPair(id="p", a=NODE_A, b=NODE_B, a_to_b=DirectionRule(delete="soft"))
    result = await engine.run_pair(pair, dry_run=True)
    assert _kinds(result) == [
        ("soft_delete", NODE_B),
        ("tombstone", NODE_A),
        ("tombstone", NODE_B),
    ]


async def test_conflicting_changes_are_merged_to_both_sides() -> None:
    engine, store, plugin = _engine()
    ext_a = plugin.add(NODE_A, TASK)
    ext_b = plugin.add(NODE_B, TASK)
    _link_both_sides(store, TASK, ext_a, ext_b)
    store.mark_pair_initialized(PAIR.id)
    plugin.items[NODE_A][ext_a] = CanonicalTask(
        title="from a", description="d", due=dt.date(2026, 10, 5)
    )
    plugin.items[NODE_B][ext_b] = CanonicalTask(
        title="x", description="d", due=dt.date(2026, 10, 7)
    )
    result = await engine.run_pair(PAIR, dry_run=True)
    assert _kinds(result) == [("update", NODE_A), ("update", NODE_B)]
    by_node = {action.node: action for action in result.actions_planned}
    assert by_node[NODE_A].changed == frozenset({"due"})
    assert by_node[NODE_B].changed == frozenset({"title"})


async def test_first_cycle_drops_deletions() -> None:
    engine, store, plugin = _engine()
    ext_a = plugin.add(NODE_A, TASK)
    ext_b = plugin.add(NODE_B, TASK)
    _link_both_sides(store, TASK, ext_a, ext_b)
    del plugin.items[NODE_A][ext_a]
    result = await engine.run_pair(PAIR, dry_run=True)
    assert result.ok is True
    assert _kinds(result) == []


async def test_unavailable_node_reports_error_with_empty_plan() -> None:
    engine, _store, plugin = _engine()
    plugin.fail = {NODE_A}
    result = await engine.run_pair(PAIR, dry_run=True)
    assert result.ok is False
    assert result.error is not None
    assert result.actions_planned == []


async def test_identical_existing_items_are_linked_not_created() -> None:
    engine, _store, plugin = _engine()
    plugin.add(NODE_A, TASK)
    plugin.add(NODE_B, TASK)
    result = await engine.run_pair(PAIR, dry_run=True)
    assert _kinds(result) == [("link", NODE_A), ("link", NODE_B)]
