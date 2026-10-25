"""Scheduling of pair cycles on intervals and state changes."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import datetime, timedelta
import logging
import time

from homeassistant.core import Event, EventStateChangedData, HomeAssistant, callback
from homeassistant.helpers.event import (
    async_call_later,
    async_track_state_change_event,
    async_track_time_interval,
)

from .const import EVENT_DEBOUNCE_SECONDS
from .core.actions import RunResult, action_to_dict
from .core.engine import SyncEngine
from .core.model import SyncPair

_LOGGER = logging.getLogger(__package__)

FIRST_RUN_DELAY_SECONDS = 10.0
WARNING_RATE_SECONDS = 600.0


class SyncCoordinator:
    """Runs pair cycles on a timer, on debounced state changes, and on demand."""

    def __init__(self, hass: HomeAssistant, pairs: list[SyncPair], engine: SyncEngine) -> None:
        self._hass = hass
        self._pairs = {pair.id: pair for pair in pairs}
        self._engine = engine
        self._results: dict[str, RunResult] = {}
        self._locks = {pair.id: asyncio.Lock() for pair in pairs}
        self._unsubscribers: list[Callable[[], None]] = []
        self._debounce_cancels: dict[str, Callable[[], None]] = {}
        self._subscribers: list[Callable[[str], None]] = []
        self._last_warning: dict[str, float] = {}

    async def async_start(self) -> None:
        """Schedule interval timers, state listeners, and the delayed first run."""
        for pair in self._pairs.values():
            if not pair.enabled:
                continue
            self._unsubscribers.append(
                async_track_time_interval(
                    self._hass,
                    self._interval_callback(pair.id),
                    timedelta(seconds=pair.interval),
                )
            )
        entity_ids = sorted({node for pair in self._pairs.values() for node in (pair.a, pair.b)})
        if entity_ids:
            self._unsubscribers.append(
                async_track_state_change_event(self._hass, entity_ids, self._on_state_changed)
            )
        self._unsubscribers.append(
            async_call_later(self._hass, FIRST_RUN_DELAY_SECONDS, self._first_run)
        )

    async def async_stop(self) -> None:
        """Cancel all timers and listeners."""
        for cancel in self._debounce_cancels.values():
            cancel()
        self._debounce_cancels.clear()
        for unsubscribe in self._unsubscribers:
            unsubscribe()
        self._unsubscribers.clear()

    async def async_run_pair(self, pair_id: str, *, dry_run: bool = False) -> RunResult:
        """Run one cycle; concurrent runs of the same pair are serialized."""
        async with self._locks[pair_id]:
            started = time.monotonic()
            result = await self._engine.run_pair(self._pairs[pair_id], dry_run=dry_run)
            duration = time.monotonic() - started
        self._results[pair_id] = result
        _LOGGER.info(
            "pair=%s ok=%s planned=%d applied=%d failed=%d links=%d duration=%.2fs",
            pair_id,
            result.ok,
            len(result.actions_planned),
            len(result.actions_applied),
            len(result.actions_failed),
            result.links,
            duration,
        )
        if result.actions_planned:
            _LOGGER.debug(
                "pair=%s planned actions=%s",
                pair_id,
                [action_to_dict(action) for action in result.actions_planned],
            )
        if not result.ok:
            self._warn_rate_limited(pair_id, result.error or "unknown error")
        for notify in self._subscribers:
            notify(pair_id)
        return result

    def _warn_rate_limited(self, pair_id: str, error: str) -> None:
        """Log a node error at most once per 10 minutes per pair."""
        now = time.monotonic()
        if now - self._last_warning.get(pair_id, 0.0) < WARNING_RATE_SECONDS:
            return
        self._last_warning[pair_id] = now
        _LOGGER.warning("pair=%s error=%s", pair_id, error)

    @property
    def results(self) -> dict[str, RunResult]:
        """The last result of every pair."""
        return dict(self._results)

    @property
    def pairs(self) -> dict[str, SyncPair]:
        """The configured pairs by id."""
        return dict(self._pairs)

    def subscribe(self, cb: Callable[[str], None]) -> Callable[[], None]:
        """Subscribe to per-pair result notifications; returns an unsubscribe."""
        self._subscribers.append(cb)

        def unsubscribe() -> None:
            self._subscribers.remove(cb)

        return unsubscribe

    @callback
    def _interval_callback(self, pair_id: str) -> Callable[[datetime], None]:
        @callback
        def on_interval(_now: datetime) -> None:
            self._hass.async_create_task(self.async_run_pair(pair_id))

        return on_interval

    @callback
    def _first_run(self, _now: datetime) -> None:
        for pair_id, pair in self._pairs.items():
            if pair.enabled:
                self._hass.async_create_task(self.async_run_pair(pair_id))

    @callback
    def _on_state_changed(self, event: Event[EventStateChangedData]) -> None:
        entity_id = event.data["entity_id"]
        pair_ids = [
            pair.id
            for pair in self._pairs.values()
            if pair.enabled and entity_id in (pair.a, pair.b)
        ]
        if not pair_ids:
            return
        cancel = self._debounce_cancels.pop(entity_id, None)
        if cancel is not None:
            cancel()
        self._debounce_cancels[entity_id] = async_call_later(
            self._hass, EVENT_DEBOUNCE_SECONDS, self._debounced_run(tuple(pair_ids))
        )

    @callback
    def _debounced_run(self, pair_ids: tuple[str, ...]) -> Callable[[datetime], None]:
        @callback
        def run_pairs(_now: datetime) -> None:
            for pair_id in pair_ids:
                self._hass.async_create_task(self.async_run_pair(pair_id))

        return run_pairs
