"""Diagnostics for the config entry."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN
from .coordinator import SyncCoordinator
from .core.actions import RunResult, action_to_dict
from .core.link_store import LinkStore


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


def _store_dump(store: LinkStore, coordinator: SyncCoordinator) -> dict[str, Any]:
    seen: set[str] = set()
    links: list[dict[str, Any]] = []
    for pair in coordinator.pairs.values():
        for canonical_id, node_links in store.links_for_pair(pair.a, pair.b).items():
            if canonical_id in seen:
                continue
            seen.add(canonical_id)
            links.extend(link.to_dict() for link in node_links.values())
    initialized = [pid for pid in coordinator.pairs if store.pair_initialized(pid)]
    return {"links": links, "initialized_pairs": sorted(initialized)}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    """Export the configuration and the storage; there are no secrets by construction."""
    coordinator: SyncCoordinator | None = hass.data.get(DOMAIN, {}).get("coordinator")
    store: LinkStore | None = hass.data.get(DOMAIN, {}).get("store")
    if coordinator is None or store is None:
        return {"pairs": [], "store": {"links": [], "initialized_pairs": []}, "results": {}}
    return {
        "pairs": [asdict(pair) for pair in coordinator.pairs.values()],
        "store": _store_dump(store, coordinator),
        "results": {
            pair_id: _result_to_dict(result) for pair_id, result in coordinator.results.items()
        },
    }
