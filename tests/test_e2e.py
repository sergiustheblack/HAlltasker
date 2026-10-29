"""End-to-end acceptance tests through the real todo services."""

from __future__ import annotations

import datetime as dt
from typing import Any

from homeassistant.components.todo.const import TodoListEntityFeature
from homeassistant.core import HomeAssistant
from homeassistant.setup import async_setup_component
from homeassistant.util import dt as dt_util
import pytest

from custom_components.halltasker.const import DOMAIN

from .todo_platform import setup_memory_todo

NODE_A = "todo.list_a"
NODE_B = "todo.list_b"
FULL_FEATURES = (
    TodoListEntityFeature.CREATE_TODO_ITEM
    | TodoListEntityFeature.DELETE_TODO_ITEM
    | TodoListEntityFeature.UPDATE_TODO_ITEM
    | TodoListEntityFeature.SET_DUE_DATE_ON_ITEM
    | TodoListEntityFeature.SET_DUE_DATETIME_ON_ITEM
    | TodoListEntityFeature.SET_DESCRIPTION_ON_ITEM
)
DATE_ONLY_FEATURES = FULL_FEATURES & ~TodoListEntityFeature.SET_DUE_DATETIME_ON_ITEM
CONFIG = {
    "halltasker": {
        "pairs": [{"id": "p1", "a": NODE_A, "b": NODE_B, "interval": 3600}],
    }
}


async def _setup_pair(hass: HomeAssistant, features_b: int = FULL_FEATURES) -> None:
    await setup_memory_todo(hass, "list_a", FULL_FEATURES)
    await setup_memory_todo(hass, "list_b", features_b)
    assert await async_setup_component(hass, DOMAIN, CONFIG)
    await hass.async_block_till_done()


async def _sync(hass: HomeAssistant) -> None:
    await hass.services.async_call(DOMAIN, "sync_now", {"pair_id": "p1"}, blocking=True)


async def _items(hass: HomeAssistant, entity_id: str) -> list[dict[str, Any]]:
    response = await hass.services.async_call(
        "todo",
        "get_items",
        {"entity_id": entity_id},
        blocking=True,
        return_response=True,
    )
    return response[entity_id]["items"]


async def _add_item(hass: HomeAssistant, entity_id: str, **fields: Any) -> None:
    await hass.services.async_call(
        "todo", "add_item", {"entity_id": entity_id, **fields}, blocking=True
    )


async def test_a1_create_replicates_all_fields_through_todo_services(hass) -> None:
    await _setup_pair(hass)
    due = dt.datetime(2026, 10, 5, 23, 30, tzinfo=dt.UTC)
    await _add_item(hass, NODE_A, item="x", due_datetime=due, description="details")

    await _sync(hass)

    items = await _items(hass, NODE_B)
    assert len(items) == 1
    assert items[0]["summary"] == "x"
    assert items[0]["due"] == due.astimezone(dt_util.get_default_time_zone()).isoformat()
    assert items[0]["description"] == "details"


async def test_a2_rename_in_b_reaches_a_and_repeated_cycle_is_idle(hass) -> None:
    await _setup_pair(hass)
    await _add_item(hass, NODE_A, item="before")
    await _sync(hass)
    item_b = (await _items(hass, NODE_B))[0]

    await hass.services.async_call(
        "todo",
        "update_item",
        {"entity_id": NODE_B, "item": item_b["uid"], "rename": "after"},
        blocking=True,
    )
    await _sync(hass)

    assert (await _items(hass, NODE_A))[0]["summary"] == "after"
    settled = await _items(hass, NODE_B)
    await _sync(hass)
    assert await _items(hass, NODE_B) == settled


async def test_a3_completion_and_reopening_reach_b(hass) -> None:
    await _setup_pair(hass)
    await _add_item(hass, NODE_A, item="x")
    await _sync(hass)
    uid_a = (await _items(hass, NODE_A))[0]["uid"]

    await hass.services.async_call(
        "todo",
        "update_item",
        {"entity_id": NODE_A, "item": uid_a, "status": "completed"},
        blocking=True,
    )
    await _sync(hass)
    assert (await _items(hass, NODE_B))[0]["status"] == "completed"

    await hass.services.async_call(
        "todo",
        "update_item",
        {"entity_id": NODE_A, "item": uid_a, "status": "needs_action"},
        blocking=True,
    )
    await _sync(hass)
    assert (await _items(hass, NODE_B))[0]["status"] == "needs_action"


async def test_a4_delete_true_removes_item_from_b(hass) -> None:
    await _setup_pair(hass)
    await _add_item(hass, NODE_A, item="x")
    await _sync(hass)
    uid_a = (await _items(hass, NODE_A))[0]["uid"]

    await hass.services.async_call(
        "todo", "remove_item", {"entity_id": NODE_A, "item": [uid_a]}, blocking=True
    )
    await _sync(hass)

    assert await _items(hass, NODE_A) == []
    assert await _items(hass, NODE_B) == []


async def test_a7_datetime_is_written_as_date_on_date_only_node(hass) -> None:
    await _setup_pair(hass, features_b=DATE_ONLY_FEATURES)
    due = dt.datetime(2026, 10, 5, 23, 30, tzinfo=dt.UTC)
    await _add_item(hass, NODE_A, item="x", due_datetime=due)

    await _sync(hass)
    await _sync(hass)

    items = await _items(hass, NODE_B)
    assert len(items) == 1
    assert items[0]["due"] == "2026-10-05"
    assert (await _items(hass, NODE_A))[0]["due"] == due.astimezone(
        dt_util.get_default_time_zone()
    ).isoformat()


async def test_a9_initial_merge_links_identical_items_without_duplicates(hass) -> None:
    await setup_memory_todo(hass, "list_a", FULL_FEATURES)
    await setup_memory_todo(hass, "list_b", FULL_FEATURES)
    due = dt.date(2026, 10, 5)
    await _add_item(hass, NODE_A, item="existing", due_date=due)
    await _add_item(hass, NODE_B, item="existing", due_date=due)
    assert await async_setup_component(hass, DOMAIN, CONFIG)
    await hass.async_block_till_done()

    await _sync(hass)

    items_a = await _items(hass, NODE_A)
    items_b = await _items(hass, NODE_B)
    assert len(items_a) == 1
    assert len(items_b) == 1
    assert items_a[0]["summary"] == items_b[0]["summary"] == "existing"
    assert items_a[0]["due"] == items_b[0]["due"] == due.isoformat()


def _config(*pairs: dict[str, Any]) -> dict[str, Any]:
    return {"halltasker": {"pairs": [{**pair, "interval": 3600} for pair in pairs]}}


async def _setup(hass: HomeAssistant, config: dict[str, Any], *suffixes: str) -> None:
    for suffix in suffixes:
        await setup_memory_todo(hass, suffix, FULL_FEATURES)
    assert await async_setup_component(hass, DOMAIN, config)
    await hass.async_block_till_done()


async def _rename(hass: HomeAssistant, entity_id: str, uid: str, title: str) -> None:
    await hass.services.async_call(
        "todo",
        "update_item",
        {"entity_id": entity_id, "item": uid, "rename": title},
        blocking=True,
    )


async def _set_status(hass: HomeAssistant, entity_id: str, uid: str, status: str) -> None:
    await hass.services.async_call(
        "todo",
        "update_item",
        {"entity_id": entity_id, "item": uid, "status": status},
        blocking=True,
    )


async def _set_due(hass: HomeAssistant, entity_id: str, uid: str, due: dt.date) -> None:
    await hass.services.async_call(
        "todo",
        "update_item",
        {"entity_id": entity_id, "item": uid, "due_date": due.isoformat()},
        blocking=True,
    )


async def _remove(hass: HomeAssistant, entity_id: str, uid: str) -> None:
    await hass.services.async_call(
        "todo", "remove_item", {"entity_id": entity_id, "item": [uid]}, blocking=True
    )


async def _uid(hass: HomeAssistant, entity_id: str, summary: str) -> str:
    return next(item["uid"] for item in await _items(hass, entity_id) if item["summary"] == summary)


@pytest.mark.xfail(reason="IT-47: stale last_written misclassifies the revert as echo")
async def test_a3_reopen_after_engine_write_to_same_side_reaches_b(hass) -> None:
    # Mirrors the IT-44 manual run: the engine wrote the title to A, so A's
    # last_written holds the open task; completing and reopening A must not
    # be swallowed by the echo check against that stale snapshot.
    await _setup(hass, CONFIG, "list_a", "list_b")
    await _add_item(hass, NODE_A, item="x")
    await _sync(hass)
    uid_b = (await _items(hass, NODE_B))[0]["uid"]
    await _rename(hass, NODE_B, uid_b, "engine-written")
    await _sync(hass)
    uid_a = (await _items(hass, NODE_A))[0]["uid"]

    await _set_status(hass, NODE_A, uid_a, "completed")
    await _sync(hass)
    assert (await _items(hass, NODE_B))[0]["status"] == "completed"

    await _set_status(hass, NODE_A, uid_a, "needs_action")
    await _sync(hass)
    await _sync(hass)
    assert (await _items(hass, NODE_B))[0]["status"] == "needs_action"


async def test_a4_delete_soft_marks_item_done_in_b(hass) -> None:
    config = _config(
        {"id": "p1", "a": NODE_A, "b": NODE_B, "a_to_b": {"delete": "soft"}},
    )
    await _setup(hass, config, "list_a", "list_b")
    await _add_item(hass, NODE_A, item="x")
    await _sync(hass)
    uid_a = (await _items(hass, NODE_A))[0]["uid"]

    await _remove(hass, NODE_A, uid_a)
    await _sync(hass)

    items_b = await _items(hass, NODE_B)
    assert len(items_b) == 1
    assert items_b[0]["status"] == "completed"
    await _sync(hass)
    assert len(await _items(hass, NODE_A)) == 0


async def test_a4_delete_false_keeps_item_live_in_b(hass) -> None:
    config = _config(
        {"id": "p1", "a": NODE_A, "b": NODE_B, "a_to_b": {"delete": False}},
    )
    await _setup(hass, config, "list_a", "list_b")
    await _add_item(hass, NODE_A, item="x")
    await _sync(hass)
    uid_a = (await _items(hass, NODE_A))[0]["uid"]

    await _remove(hass, NODE_A, uid_a)
    await _sync(hass)
    await _sync(hass)

    items_b = await _items(hass, NODE_B)
    assert len(items_b) == 1
    assert items_b[0]["status"] == "needs_action"
    assert await _items(hass, NODE_A) == []


async def test_a5_title_and_due_changes_apply_on_both_sides(hass) -> None:
    await _setup(hass, CONFIG, "list_a", "list_b")
    await _add_item(hass, NODE_A, item="x", due_date=dt.date(2026, 10, 30))
    await _sync(hass)
    uid_a = (await _items(hass, NODE_A))[0]["uid"]
    uid_b = (await _items(hass, NODE_B))[0]["uid"]

    await _rename(hass, NODE_A, uid_a, "title from A")
    await _set_due(hass, NODE_B, uid_b, dt.date(2026, 10, 31))
    await _sync(hass)

    for entity_id in (NODE_A, NODE_B):
        item = (await _items(hass, entity_id))[0]
        assert item["summary"] == "title from A"
        assert item["due"] == "2026-10-31"


async def test_a6_conflicting_titles_resolve_by_prefer_a(hass) -> None:
    await _setup(hass, CONFIG, "list_a", "list_b")
    await _add_item(hass, NODE_A, item="x")
    await _sync(hass)
    uid_a = (await _items(hass, NODE_A))[0]["uid"]
    uid_b = (await _items(hass, NODE_B))[0]["uid"]

    await _rename(hass, NODE_A, uid_a, "title from A")
    await _rename(hass, NODE_B, uid_b, "title from B")
    await _sync(hass)

    for entity_id in (NODE_A, NODE_B):
        assert (await _items(hass, entity_id))[0]["summary"] == "title from A"


async def test_a8_dry_run_reports_plan_without_writing(hass) -> None:
    await _setup(hass, CONFIG, "list_a", "list_b")
    await _add_item(hass, NODE_A, item="x")
    await _sync(hass)
    uid_b = (await _items(hass, NODE_B))[0]["uid"]

    await _rename(hass, NODE_B, uid_b, "renamed on B")
    response = await hass.services.async_call(
        DOMAIN,
        "dry_run",
        {"pair_id": "p1"},
        blocking=True,
        return_response=True,
    )

    plan = response["pairs"]["p1"]
    assert [(action["kind"], action["node"]) for action in plan] == [("update", NODE_A)]
    assert (await _items(hass, NODE_A))[0]["summary"] == "x"

    await _sync(hass)
    assert (await _items(hass, NODE_A))[0]["summary"] == "renamed on B"


async def test_a10_star_propagates_create_and_delete_across_shared_node(hass) -> None:
    node_c = "todo.list_c"
    config = _config(
        {"id": "p1", "a": NODE_A, "b": NODE_B},
        {"id": "p2", "a": NODE_B, "b": node_c},
    )
    await _setup(hass, config, "list_a", "list_b", "list_c")

    await _add_item(hass, NODE_A, item="x")
    await _sync(hass)
    assert len(await _items(hass, NODE_B)) == 1
    await hass.services.async_call(DOMAIN, "sync_now", {"pair_id": "p2"}, blocking=True)
    assert len(await _items(hass, node_c)) == 1

    await _remove(hass, NODE_A, (await _items(hass, NODE_A))[0]["uid"])
    await _sync(hass)
    assert await _items(hass, NODE_B) == []
    await hass.services.async_call(DOMAIN, "sync_now", {"pair_id": "p2"}, blocking=True)
    assert await _items(hass, node_c) == []

    await _sync(hass)
    await hass.services.async_call(DOMAIN, "sync_now", {"pair_id": "p2"}, blocking=True)
    assert await _items(hass, NODE_B) == []
    assert await _items(hass, node_c) == []


async def test_a11_blocked_update_is_accepted_locally_without_leaking(hass) -> None:
    config = _config(
        {"id": "p1", "a": NODE_A, "b": NODE_B, "a_to_b": {"update": False}},
    )
    await _setup(hass, config, "list_a", "list_b")
    await _add_item(hass, NODE_A, item="x", due_date=dt.date(2026, 10, 30))
    await _sync(hass)
    uid_a = (await _items(hass, NODE_A))[0]["uid"]
    uid_b = (await _items(hass, NODE_B))[0]["uid"]

    await _rename(hass, NODE_A, uid_a, "renamed on A")
    await _sync(hass)
    await _sync(hass)
    assert (await _items(hass, NODE_B))[0]["summary"] == "x"

    await _set_due(hass, NODE_B, uid_b, dt.date(2026, 11, 5))
    await _sync(hass)

    item_a = (await _items(hass, NODE_A))[0]
    item_b = (await _items(hass, NODE_B))[0]
    assert item_a["summary"] == "renamed on A"
    assert item_a["due"] == "2026-11-05"
    assert item_b["summary"] == "x"
    assert item_b["due"] == "2026-11-05"
