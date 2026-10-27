"""Tests for two pairs sharing a node (SPEC FR-12, scenario A10)."""

from __future__ import annotations

import datetime as dt

from custom_components.halltasker.core.engine import SyncEngine
from custom_components.halltasker.core.link_store import LinkStore
from custom_components.halltasker.core.model import CanonicalTask, DirectionRule, SyncPair
from custom_components.halltasker.plugins.registry import PluginRegistry

from .fakes import FULL_CAPS, FakePlugin, FakeStorage

NODE_A = "fake.a"
NODE_B = "fake.b"
NODE_C = "fake.c"

TASK = CanonicalTask(title="x", description="d", due=dt.date(2026, 10, 5))
RENAMED = CanonicalTask(title="renamed", description="d", due=dt.date(2026, 10, 5))

PAIR_AB = SyncPair(id="ab", a=NODE_A, b=NODE_B)
PAIR_BC = SyncPair(id="bc", a=NODE_B, b=NODE_C)

NOW = dt.datetime(2026, 10, 26, 12, 0, tzinfo=dt.UTC)


def _engines(a_to_b_ab: DirectionRule | None = None):
    storage = FakeStorage()
    store = LinkStore(storage)
    pair_ab = (
        PAIR_AB if a_to_b_ab is None else SyncPair(id="ab", a=NODE_A, b=NODE_B, a_to_b=a_to_b_ab)
    )
    plugin = FakePlugin()
    for node in (NODE_A, NODE_B, NODE_C):
        plugin.caps[node] = FULL_CAPS
    registry = PluginRegistry()
    registry.register(plugin)
    engine_ab = SyncEngine(store.for_pair(pair_ab), registry, clock=lambda: NOW)
    engine_bc = SyncEngine(store.for_pair(PAIR_BC), registry, clock=lambda: NOW)
    return engine_ab, engine_bc, pair_ab, PAIR_BC, storage, plugin


async def _run(engine, pair):
    result = await engine.run_pair(pair, dry_run=False)
    assert result.ok is True, result.error
    return result


async def test_create_in_a_reaches_c_and_cycles_settle() -> None:
    engine_ab, engine_bc, pair_ab, pair_bc, storage, plugin = _engines()
    plugin.add(NODE_A, TASK)

    await _run(engine_ab, pair_ab)  # A -> B
    await _run(engine_bc, pair_bc)  # B -> C
    await _run(engine_ab, pair_ab)
    await _run(engine_bc, pair_bc)
    assert plugin.items[NODE_A][next(iter(plugin.items[NODE_A]))] == TASK
    assert plugin.items[NODE_B][next(iter(plugin.items[NODE_B]))] == TASK
    assert plugin.items[NODE_C][next(iter(plugin.items[NODE_C]))] == TASK

    saves_before = storage.saves
    idle_ab = await _run(engine_ab, pair_ab)
    idle_bc = await _run(engine_bc, pair_bc)
    assert idle_ab.actions_applied == [] and idle_bc.actions_applied == []
    assert storage.saves == saves_before


async def test_rename_in_c_reaches_a() -> None:
    engine_ab, engine_bc, pair_ab, pair_bc, _storage, plugin = _engines()
    plugin.add(NODE_A, TASK)
    await _run(engine_ab, pair_ab)
    await _run(engine_bc, pair_bc)

    ext_c = next(iter(plugin.items[NODE_C]))
    plugin.items[NODE_C][ext_c] = RENAMED
    await _run(engine_bc, pair_bc)  # C -> B
    await _run(engine_ab, pair_ab)  # B -> A

    assert plugin.items[NODE_A][next(iter(plugin.items[NODE_A]))] == RENAMED
    assert plugin.items[NODE_B][next(iter(plugin.items[NODE_B]))] == RENAMED


async def test_delete_in_a_removes_b_then_c_and_cycles_settle() -> None:
    engine_ab, engine_bc, pair_ab, pair_bc, storage, plugin = _engines()
    ext_a = plugin.add(NODE_A, TASK)
    await _run(engine_ab, pair_ab)
    await _run(engine_bc, pair_bc)

    del plugin.items[NODE_A][ext_a]
    await _run(engine_ab, pair_ab)  # B item deleted
    assert plugin.items[NODE_B] == {}
    await _run(engine_bc, pair_bc)  # C item deleted
    assert plugin.items[NODE_C] == {}

    saves_before = storage.saves
    idle_ab = await _run(engine_ab, pair_ab)
    idle_bc = await _run(engine_bc, pair_bc)
    assert idle_ab.actions_applied == [] and idle_bc.actions_applied == []
    assert storage.saves == saves_before


async def test_delete_false_in_ab_keeps_item_in_b_and_c() -> None:
    engine_ab, engine_bc, pair_ab, pair_bc, _storage, plugin = _engines(
        a_to_b_ab=DirectionRule(delete="false")
    )
    ext_a = plugin.add(NODE_A, TASK)
    await _run(engine_ab, pair_ab)
    await _run(engine_bc, pair_bc)

    del plugin.items[NODE_A][ext_a]
    await _run(engine_ab, pair_ab)
    assert plugin.items[NODE_A] == {}
    assert len(plugin.items[NODE_B]) == 1  # kept by delete: false

    await _run(engine_bc, pair_bc)
    assert len(plugin.items[NODE_C]) == 1  # nothing deleted downstream

    await _run(engine_ab, pair_ab)
    await _run(engine_bc, pair_bc)
    assert plugin.items[NODE_A] == {}
    assert len(plugin.items[NODE_B]) == 1
    assert len(plugin.items[NODE_C]) == 1
