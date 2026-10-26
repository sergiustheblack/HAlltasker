"""Diagnostics for the config entry."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN
from .coordinator import SyncCoordinator
from .core.actions import RunResult, action_to_dict
from .core.link_store import LinkStore

REDACTED_KEYS = {"title", "description"}


def _result_to_dict(result: RunResult) -> dict[str, Any]:
    return {
        "ok": result.ok,
        "error": result.error,
        "links": result.links,
        "actions_planned": [action_to_dict(action) for action in result.actions_planned],
        "actions_applied": [action_to_dict(action) for action in result.actions_applied],
        "actions_failed": [
            [action_to_dict(action), error] for action, error in result.actions_failed
        ],
    }


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    """Export the configuration and the storage with task texts redacted."""
    coordinator: SyncCoordinator | None = hass.data.get(DOMAIN, {}).get("coordinator")
    store: LinkStore | None = hass.data.get(DOMAIN, {}).get("store")
    if coordinator is None or store is None:
        return {
            "pairs": [],
            "store": async_redact_data({"schema": 2, "pairs": {}}, REDACTED_KEYS),
            "results": {},
        }
    return {
        "pairs": [asdict(pair) for pair in coordinator.pairs.values()],
        "store": async_redact_data(store.to_dict(), REDACTED_KEYS),
        "results": async_redact_data(
            {pair_id: _result_to_dict(result) for pair_id, result in coordinator.results.items()},
            REDACTED_KEYS,
        ),
    }
