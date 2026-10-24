"""Tests for the coordinator scheduling."""

from __future__ import annotations

import asyncio
import datetime as dt

from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import async_fire_time_changed

from custom_components.halltasker.const import EVENT_DEBOUNCE_SECONDS
from custom_components.halltasker.coordinator import SyncCoordinator
from custom_components.halltasker.core.actions import RunResult
from custom_components.halltasker.core.engine import SyncEngine
from custom_components.halltasker.core.link_store import LinkStore
from custom_components.halltasker.core.model import SyncPair
from custom_components.halltasker.plugins.registry import PluginRegistry

from .core.fakes import FakeStorage

NODE_A = "fake.a"
NODE_B = "fake.b"
PAIR = SyncPair(id="p1", a=NODE_A, b=NODE_B, interval=60)

NOW = dt.datetime(2026, 10, 25, 12, 0, 0, tzinfo=dt.UTC)


class CountingEngine(SyncEngine):
    """Counts cycles and can simulate overlap."""

    def __init__(self, delay: float = 0.0) -> None:
        super().__init__(LinkStore(FakeStorage()), PluginRegistry(), clock=lambda: NOW)
        self.runs = 0
        self.active = False
        self.overlapped = False
        self._delay = delay

    async def run_pair(self, pair: SyncPair, *, dry_run: bool) -> RunResult:
        if self.active:
            self.overlapped = True
        self.active = True
        try:
            await asyncio.sleep(self._delay)
            self.runs += 1
            return RunResult(ok=True, error=None, links=self.runs)
        finally:
            self.active = False


def _coordinator(hass: HomeAssistant, engine: SyncEngine) -> SyncCoordinator:
    return SyncCoordinator(hass, [PAIR], engine)


async def test_cycle_runs_on_interval(hass: HomeAssistant) -> None:
    engine = CountingEngine()
    coordinator = _coordinator(hass, engine)
    await coordinator.async_start()
    start = dt_util.utcnow()
    async_fire_time_changed(hass, start + dt.timedelta(seconds=5))
    await hass.async_block_till_done()
    assert engine.runs == 0

    async_fire_time_changed(hass, start + dt.timedelta(seconds=61))
    await hass.async_block_till_done()
    assert engine.runs >= 1
    assert coordinator.results["p1"].ok is True
    await coordinator.async_stop()


async def test_state_change_runs_cycle_once_after_debounce(hass: HomeAssistant) -> None:
    engine = CountingEngine()
    coordinator = _coordinator(hass, engine)
    await coordinator.async_start()
    start = dt_util.utcnow()
    hass.states.async_set(NODE_A, "1")
    hass.states.async_set(NODE_A, "2")
    await hass.async_block_till_done()
    assert engine.runs == 0

    async_fire_time_changed(hass, start + dt.timedelta(seconds=EVENT_DEBOUNCE_SECONDS + 1))
    await hass.async_block_till_done()
    assert engine.runs == 1
    await coordinator.async_stop()


async def test_concurrent_runs_of_one_pair_are_serialized(hass: HomeAssistant) -> None:
    engine = CountingEngine(delay=0.01)
    coordinator = _coordinator(hass, engine)
    await coordinator.async_start()
    results = await asyncio.gather(
        coordinator.async_run_pair("p1"),
        coordinator.async_run_pair("p1"),
    )
    assert engine.runs == 2
    assert engine.overlapped is False
    assert all(result.ok for result in results)
    await coordinator.async_stop()


async def test_subscribe_notifies_about_pair_results(hass: HomeAssistant) -> None:
    engine = CountingEngine()
    coordinator = _coordinator(hass, engine)
    notified: list[str] = []
    unsubscribe = coordinator.subscribe(notified.append)
    await coordinator.async_run_pair("p1")
    assert notified == ["p1"]
    unsubscribe()
    await coordinator.async_run_pair("p1")
    assert notified == ["p1"]


async def test_stop_cancels_timers(hass: HomeAssistant) -> None:
    engine = CountingEngine()
    coordinator = _coordinator(hass, engine)
    await coordinator.async_start()
    await coordinator.async_stop()
    async_fire_time_changed(hass, dt_util.utcnow() + dt.timedelta(seconds=3600))
    await hass.async_block_till_done()
    assert engine.runs == 0
