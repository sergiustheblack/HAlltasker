"""Tests for the per-pair status sensor."""

from __future__ import annotations

from typing import Any

from homeassistant.core import ServiceCall, SupportsResponse
from homeassistant.setup import async_setup_component

from custom_components.halltasker.const import DOMAIN

CONFIG = {"halltasker": {"pairs": [{"id": "p1", "a": "todo.list_a", "b": "todo.list_b"}]}}


class FakeTodoBackend:
    """Minimal in-memory todo service set, registered over the real ones."""

    def __init__(self) -> None:
        self.items: dict[str, list[dict[str, Any]]] = {"todo.list_a": [], "todo.list_b": []}
        self._next_uid = 0

    async def get_items(self, call: ServiceCall) -> dict[str, Any]:
        entity_id = call.data["entity_id"]
        return {entity_id: {"items": [dict(item) for item in self.items[entity_id]]}}

    async def add_item(self, call: ServiceCall) -> None:
        self._next_uid += 1
        item: dict[str, Any] = {
            "uid": f"uid-{self._next_uid}",
            "summary": call.data["item"],
            "status": "needs_action",
        }
        if call.data.get("description"):
            item["description"] = call.data["description"]
        self.items[call.data["entity_id"]].append(item)


def _register_overrides(hass, backend: FakeTodoBackend) -> None:
    """The todo dependency loads first, so the fakes must come after it."""
    hass.services.async_register(
        "todo", "get_items", backend.get_items, supports_response=SupportsResponse.ONLY
    )
    hass.services.async_register("todo", "add_item", backend.add_item)


def _set_states(hass) -> None:
    hass.states.async_set("todo.list_a", "0", {"supported_features": 127})
    hass.states.async_set("todo.list_b", "0", {"supported_features": 127})


async def test_sensor_shows_ok_with_links_after_cycle(hass) -> None:
    backend = FakeTodoBackend()
    assert await async_setup_component(hass, DOMAIN, CONFIG)
    await hass.async_block_till_done()
    _register_overrides(hass, backend)
    _set_states(hass)

    await hass.services.async_call(
        "todo", "add_item", {"entity_id": "todo.list_a", "item": "buy milk"}, blocking=True
    )
    await hass.services.async_call(DOMAIN, "sync_now", {"pair_id": "p1"}, blocking=True)
    await hass.async_block_till_done()

    state = hass.states.get("sensor.halltasker_p1")
    assert state is not None
    assert state.state == "ok"
    assert state.attributes["links"] == 2
    assert state.attributes["last_run"] is not None
    assert state.attributes["last_error"] is None
    assert state.attributes["last_actions"] == {"link": 1, "create": 1}
    assert backend.items["todo.list_b"][0]["summary"] == "buy milk"


async def test_sensor_shows_error_when_node_is_missing(hass) -> None:
    assert await async_setup_component(hass, DOMAIN, CONFIG)
    await hass.async_block_till_done()

    await hass.services.async_call(DOMAIN, "sync_now", {"pair_id": "p1"}, blocking=True)
    await hass.async_block_till_done()

    state = hass.states.get("sensor.halltasker_p1")
    assert state.state == "error"
    assert state.attributes["last_error"] is not None
