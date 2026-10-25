"""Tests for diagnostics."""

from __future__ import annotations

from typing import Any

from homeassistant.core import ServiceCall, SupportsResponse
from homeassistant.setup import async_setup_component

from custom_components.halltasker.const import DOMAIN
from custom_components.halltasker.diagnostics import async_get_config_entry_diagnostics

CONFIG = {"halltasker": {"pairs": [{"id": "p1", "a": "todo.list_a", "b": "todo.list_b"}]}}


async def test_diagnostics_returns_pairs_store_and_results(hass) -> None:
    async def get_items(call: ServiceCall) -> dict[str, Any]:
        return {call.data["entity_id"]: {"items": []}}

    assert await async_setup_component(hass, DOMAIN, CONFIG)
    await hass.async_block_till_done()
    hass.services.async_register(
        "todo", "get_items", get_items, supports_response=SupportsResponse.ONLY
    )
    hass.states.async_set("todo.list_a", "0", {"supported_features": 127})
    hass.states.async_set("todo.list_b", "0", {"supported_features": 127})

    await hass.services.async_call(DOMAIN, "sync_now", {"pair_id": "p1"}, blocking=True)
    await hass.async_block_till_done()

    entry = hass.config_entries.async_entries(DOMAIN)[0]
    data = await async_get_config_entry_diagnostics(hass, entry)

    assert set(data) == {"pairs", "store", "results"}
    assert data["pairs"][0]["id"] == "p1"
    assert data["pairs"][0]["a_to_b"]["create"] is True
    assert data["store"]["initialized_pairs"] == ["p1"]
    assert data["results"]["p1"]["ok"] is True
    assert data["results"]["p1"]["links"] == 0


async def test_diagnostics_without_loaded_coordinator_is_empty(hass) -> None:
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    entry = MockConfigEntry(domain=DOMAIN)
    entry.add_to_hass(hass)
    data = await async_get_config_entry_diagnostics(hass, entry)
    assert data == {"pairs": [], "store": {"links": [], "initialized_pairs": []}, "results": {}}
