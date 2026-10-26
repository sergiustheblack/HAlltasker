"""Tests for diagnostics."""

from __future__ import annotations

from typing import Any

from homeassistant.core import ServiceCall, SupportsResponse
from homeassistant.setup import async_setup_component

from custom_components.halltasker.const import DOMAIN
from custom_components.halltasker.diagnostics import async_get_config_entry_diagnostics

CONFIG = {"halltasker": {"pairs": [{"id": "p1", "a": "todo.list_a", "b": "todo.list_b"}]}}


async def test_diagnostics_returns_pairs_store_and_results(hass) -> None:
    items: dict[str, list[dict[str, Any]]] = {"todo.list_a": [], "todo.list_b": []}
    next_uid = 0

    async def get_items(call: ServiceCall) -> dict[str, Any]:
        return {call.data["entity_id"]: {"items": [dict(i) for i in items[call.data["entity_id"]]]}}

    async def add_item(call: ServiceCall) -> None:
        nonlocal next_uid
        next_uid += 1
        items[call.data["entity_id"]].append(
            {"uid": f"uid-{next_uid}", "summary": call.data["item"], "status": "needs_action"}
        )

    assert await async_setup_component(hass, DOMAIN, CONFIG)
    await hass.async_block_till_done()
    hass.services.async_register(
        "todo", "get_items", get_items, supports_response=SupportsResponse.ONLY
    )
    hass.services.async_register("todo", "add_item", add_item)
    hass.states.async_set("todo.list_a", "0", {"supported_features": 127})
    hass.states.async_set("todo.list_b", "0", {"supported_features": 127})
    items["todo.list_a"].append({"uid": "seed-1", "summary": "buy milk", "status": "needs_action"})

    await hass.services.async_call(DOMAIN, "sync_now", {"pair_id": "p1"}, blocking=True)
    await hass.async_block_till_done()

    entry = hass.config_entries.async_entries(DOMAIN)[0]
    data = await async_get_config_entry_diagnostics(hass, entry)

    assert set(data) == {"pairs", "store", "results"}
    assert data["pairs"][0]["id"] == "p1"
    assert data["pairs"][0]["a_to_b"]["create"] is True
    assert data["store"]["schema"] == 2
    assert data["store"]["pairs"]["p1"]["initialized"] is True
    assert data["results"]["p1"]["ok"] is True
    assert data["results"]["p1"]["links"] == 2
    dumped = str(data)
    assert "buy milk" not in dumped
    assert "**REDACTED**" in dumped


async def test_diagnostics_without_loaded_coordinator_is_empty(hass) -> None:
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    entry = MockConfigEntry(domain=DOMAIN)
    entry.add_to_hass(hass)
    data = await async_get_config_entry_diagnostics(hass, entry)
    assert data == {"pairs": [], "store": {"schema": 2, "pairs": {}}, "results": {}}
