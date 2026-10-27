"""Tests for the ha_todo plugin against fake todo services."""

from __future__ import annotations

import datetime as dt
from typing import Any

from homeassistant.core import HomeAssistant, ServiceCall, SupportsResponse
from homeassistant.exceptions import HomeAssistantError
import pytest

from custom_components.halltasker.core.engine import SyncEngine
from custom_components.halltasker.core.link_store import LinkStore
from custom_components.halltasker.core.model import CanonicalTask, SyncPair
from custom_components.halltasker.plugins.base import NodeUnavailable
from custom_components.halltasker.plugins.ha_todo import HaTodoPlugin
from custom_components.halltasker.plugins.registry import PluginRegistry
from tests.core.fakes import FakePlugin, FakeStorage

NODE = "todo.list_a"
ALL_FEATURES = 127
NO_DATETIME_FEATURES = 1 | 2 | 4 | 16 | 64
DATE_ONLY_FEATURES = 1 | 2 | 4 | 16
MSK = dt.timezone(dt.timedelta(hours=3))


class FakeTodoBackend:
    """In-memory todo.* service implementation with call recording."""

    def __init__(self) -> None:
        self.items: list[dict[str, Any]] = []
        self.update_calls: list[dict[str, Any]] = []
        self.fail_update = False
        self._next_uid = 0

    async def get_items(self, call: ServiceCall) -> dict[str, Any]:
        return {call.data["entity_id"]: {"items": [dict(item) for item in self.items]}}

    async def add_item(self, call: ServiceCall) -> None:
        self._next_uid += 1
        item: dict[str, Any] = {
            "uid": f"uid-{self._next_uid}",
            "summary": call.data["item"],
            "status": "needs_action",
        }
        if "due_date" in call.data:
            item["due"] = call.data["due_date"].isoformat()
        if "due_datetime" in call.data:
            item["due"] = call.data["due_datetime"].isoformat()
        if "description" in call.data:
            item["description"] = call.data["description"]
        self.items.append(item)

    async def update_item(self, call: ServiceCall) -> None:
        if self.fail_update:
            raise HomeAssistantError("update failed")
        self.update_calls.append(dict(call.data))
        for item in self.items:
            if item["uid"] != call.data["item"]:
                continue
            if "rename" in call.data:
                item["summary"] = call.data["rename"]
            if "status" in call.data:
                item["status"] = call.data["status"]
            if call.data.get("due_date", "keep") is None:
                item.pop("due", None)
            elif "due_date" in call.data:
                item["due"] = call.data["due_date"].isoformat()
            if "due_datetime" in call.data:
                item["due"] = call.data["due_datetime"].isoformat()
            if "description" in call.data:
                item["description"] = call.data["description"]

    async def remove_item(self, call: ServiceCall) -> None:
        uids = call.data["item"]
        self.items = [item for item in self.items if item["uid"] not in uids]

    def add(self, title: str) -> dict[str, Any]:
        self._next_uid += 1
        item = {"uid": f"uid-{self._next_uid}", "summary": title, "status": "needs_action"}
        self.items.append(item)
        return item


@pytest.fixture
def backend() -> FakeTodoBackend:
    return FakeTodoBackend()


@pytest.fixture
def plugin(hass: HomeAssistant, backend: FakeTodoBackend) -> HaTodoPlugin:
    hass.services.async_register(
        "todo", "get_items", backend.get_items, supports_response=SupportsResponse.ONLY
    )
    hass.services.async_register("todo", "add_item", backend.add_item)
    hass.services.async_register("todo", "update_item", backend.update_item)
    hass.services.async_register("todo", "remove_item", backend.remove_item)
    return HaTodoPlugin(hass)


def _set_entity(hass: HomeAssistant, features: int = ALL_FEATURES) -> None:
    hass.states.async_set(NODE, "0", {"supported_features": features})


async def test_list_maps_due_none_date_and_datetime(hass, plugin, backend) -> None:
    _set_entity(hass)
    backend.items = [
        {"uid": "1", "summary": "no due", "status": "needs_action"},
        {"uid": "2", "summary": "date", "status": "needs_action", "due": "2026-10-05"},
        {
            "uid": "3",
            "summary": "datetime",
            "status": "needs_action",
            "due": "2026-10-05T23:30:00+03:00",
        },
    ]
    items = await plugin.list(NODE)
    assert items["1"].due is None
    assert items["2"].due == dt.date(2026, 10, 5)
    assert items["3"].due == dt.datetime(2026, 10, 5, 23, 30, tzinfo=MSK)


async def test_list_maps_status_and_description(hass, plugin, backend) -> None:
    _set_entity(hass)
    backend.items = [
        {"uid": "1", "summary": "open one", "status": "needs_action"},
        {"uid": "2", "summary": "done one", "status": "completed", "description": "note"},
    ]
    items = await plugin.list(NODE)
    assert items["1"].status == "open"
    assert items["2"].status == "done"
    assert items["2"].description == "note"


async def test_capabilities_follow_supported_features(hass, plugin) -> None:
    _set_entity(hass, ALL_FEATURES)
    full = await plugin.capabilities(NODE)
    assert full.due == "datetime" and full.create and full.delete and full.description

    _set_entity(hass, NO_DATETIME_FEATURES)
    date_caps = await plugin.capabilities(NODE)
    assert date_caps.due == "date"

    _set_entity(hass, DATE_ONLY_FEATURES)
    no_description = await plugin.capabilities(NODE)
    assert no_description.due == "date" and not no_description.description


async def test_update_passes_only_changed_and_supported_fields(hass, plugin, backend) -> None:
    _set_entity(hass)
    item = backend.add("old")
    new_task = CanonicalTask(title="new", status="done")
    await plugin.update(NODE, item["uid"], new_task, frozenset({"title", "status"}))
    call = backend.update_calls[0]
    assert call["rename"] == "new"
    assert call["status"] == "completed"
    assert "due_date" not in call and "description" not in call


async def test_update_skips_description_when_unsupported(hass, plugin, backend) -> None:
    _set_entity(hass, DATE_ONLY_FEATURES)
    item = backend.add("x")
    new_task = CanonicalTask(title="x", description="note")
    await plugin.update(NODE, item["uid"], new_task, frozenset({"description"}))
    assert "description" not in backend.update_calls[0]


async def test_create_finds_uid_by_content(hass, plugin, backend) -> None:
    _set_entity(hass)
    task = CanonicalTask(title="fresh", description="d", due=dt.date(2026, 10, 5))
    backend.items.append({"uid": "known", "summary": "fresh", "status": "needs_action"})
    uid = await plugin.create(NODE, task, frozenset({"known"}))
    assert uid != "known"
    assert backend.items[-1]["summary"] == "fresh"


async def test_create_done_converges_in_one_engine_cycle(hass, plugin, backend) -> None:
    _set_entity(hass)
    source = FakePlugin()
    source.add("fake.source", CanonicalTask(title="done", status="done"))
    pair = SyncPair(id="p", a="fake.source", b=NODE)
    store = LinkStore(FakeStorage()).for_pair(pair)
    registry = PluginRegistry()
    registry.register(source)
    registry.register(plugin)
    engine = SyncEngine(
        store,
        registry,
        clock=lambda: dt.datetime(2026, 10, 28, 12, 0, tzinfo=MSK),
    )

    result = await engine.run_pair(pair, dry_run=False)
    assert result.ok is True
    assert result.actions_failed == []
    assert len(backend.items) == 1
    assert backend.items[0]["status"] == "completed"
    assert backend.update_calls[-1]["status"] == "completed"


async def test_create_done_reports_failed_completion(hass, plugin, backend) -> None:
    _set_entity(hass)
    backend.fail_update = True
    with pytest.raises(NodeUnavailable, match="created item not completed"):
        await plugin.create(NODE, CanonicalTask(title="done", status="done"), frozenset())
    assert backend.items[0]["status"] == "needs_action"


async def test_unavailable_entity_raises_node_unavailable(hass, plugin) -> None:
    hass.states.async_set(NODE, "unavailable", {"supported_features": 127})
    with pytest.raises(NodeUnavailable):
        await plugin.capabilities(NODE)
    with pytest.raises(NodeUnavailable):
        await plugin.list(NODE)
