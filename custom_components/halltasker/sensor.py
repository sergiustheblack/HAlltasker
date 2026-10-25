"""Status sensor per pair."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import dt as dt_util

from .const import DOMAIN
from .coordinator import SyncCoordinator
from .core.actions import RunResult, action_to_dict
from .core.model import SyncPair


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Create one sensor per configured pair."""
    coordinator: SyncCoordinator = hass.data[DOMAIN]["coordinator"]
    async_add_entities(PairSensor(pair, coordinator) for pair in coordinator.pairs.values())


class PairSensor(SensorEntity):
    """Shows the last cycle result of one pair."""

    _attr_icon = "mdi:sync"

    def __init__(self, pair: SyncPair, coordinator: SyncCoordinator) -> None:
        self._pair = pair
        self._coordinator = coordinator
        self._result: RunResult | None = None
        self._last_run: str | None = None
        self._unsubscribe: Callable[[], None] | None = None
        self._attr_unique_id = f"halltasker_{pair.id}"
        self._attr_name = f"HAlltasker {pair.id}"

    async def async_added_to_hass(self) -> None:
        """Start listening for results of this pair."""
        self._unsubscribe = self._coordinator.subscribe(self._on_result)

    async def async_will_remove_from_hass(self) -> None:
        if self._unsubscribe is not None:
            self._unsubscribe()
            self._unsubscribe = None

    @callback
    def _on_result(self, pair_id: str) -> None:
        if pair_id != self._pair.id:
            return
        self._result = self._coordinator.results.get(pair_id)
        self._last_run = dt_util.now().isoformat()
        self.async_write_ha_state()

    @property
    def native_value(self) -> str | None:
        if not self._pair.enabled:
            return "disabled"
        if self._result is None:
            return None
        if not self._result.ok:
            return "error"
        if self._pair.initial_sync == "dry_run":
            return "dry_run"
        return "ok"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        result = self._result
        attributes: dict[str, Any] = {
            "links": result.links if result is not None else 0,
            "last_run": self._last_run,
        }
        if result is None:
            return attributes
        attributes["last_error"] = result.error or (
            result.actions_failed[0][1] if result.actions_failed else None
        )
        counters: dict[str, int] = {}
        for action in result.actions_applied:
            counters[action.kind] = counters.get(action.kind, 0) + 1
        attributes["last_actions"] = counters
        if self._pair.initial_sync == "dry_run":
            attributes["planned_actions"] = [
                action_to_dict(action) for action in result.actions_planned
            ]
        return attributes
