"""The ha_todo plugin: any todo.* entity as a node."""

from __future__ import annotations

import asyncio
from dataclasses import replace
import datetime as dt
from typing import Any, Literal

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.util import dt as dt_util

from ..core.model import CanonicalTask, Capabilities
from .base import NodeUnavailable, Plugin, PluginSchema

_CREATE = 1
_DELETE = 2
_UPDATE = 4
_SET_DUE_DATE = 16
_SET_DUE_DATETIME = 32
_SET_DESCRIPTION = 64

_RETRY_DELAY_SECONDS = 1.0
_RETRY_ATTEMPTS = 3

DueCapability = Literal["datetime", "date", "none"]


class HaTodoPlugin(Plugin):
    """Reads and writes a todo.* entity through its services."""

    def __init__(self, hass: HomeAssistant) -> None:
        self._hass = hass
        self.schema = PluginSchema.all_canonical("ha_todo")

    def matches(self, node: str) -> bool:
        return node.startswith("todo.")

    async def capabilities(self, node: str) -> Capabilities:
        features = self._features(node)
        if features & _SET_DUE_DATETIME:
            due: DueCapability = "datetime"
        elif features & _SET_DUE_DATE:
            due = "date"
        else:
            due = "none"
        return Capabilities(
            create=bool(features & _CREATE),
            update=bool(features & _UPDATE),
            delete=bool(features & _DELETE),
            due=due,
            description=bool(features & _SET_DESCRIPTION),
        )

    async def list(self, node: str) -> dict[str, CanonicalTask]:
        self._features(node)
        try:
            response = await self._hass.services.async_call(
                "todo",
                "get_items",
                {"entity_id": node},
                blocking=True,
                return_response=True,
            )
        except HomeAssistantError as err:
            raise NodeUnavailable(str(err)) from err
        items: list[dict[str, Any]] = response[node]["items"]
        return {item["uid"]: _to_canonical(item) for item in items}

    async def create(self, node: str, task: CanonicalTask, known_ids: frozenset[str]) -> str:
        await self._call("add_item", node, _add_fields(self._features(node), task))
        expected = replace(task, status="open")
        for attempt in range(_RETRY_ATTEMPTS):
            if attempt:
                await asyncio.sleep(_RETRY_DELAY_SECONDS)
            items = await self.list(node)
            for uid, candidate in items.items():
                if uid in known_ids or candidate != expected:
                    continue
                if task.status == "done":
                    try:
                        await self._call("update_item", node, {"item": uid, "status": "completed"})
                    except NodeUnavailable as err:
                        raise NodeUnavailable("created item not completed") from err
                return uid
        raise NodeUnavailable("created item not found")

    async def update(
        self,
        node: str,
        external_id: str,
        task: CanonicalTask,
        changed: frozenset[str],
    ) -> None:
        payload = _update_fields(self._features(node), external_id, task, changed)
        await self._call("update_item", node, payload)

    async def delete(self, node: str, external_id: str) -> None:
        await self._call("remove_item", node, {"item": [external_id]})

    async def _call(self, service: str, node: str, payload: dict[str, Any]) -> None:
        data = {"entity_id": node, **payload}
        try:
            await self._hass.services.async_call("todo", service, data, blocking=True)
        except HomeAssistantError as err:
            raise NodeUnavailable(str(err)) from err

    def _features(self, node: str) -> int:
        state = self._hass.states.get(node)
        if state is None or state.state in ("unavailable", "unknown"):
            raise NodeUnavailable(node)
        return int(state.attributes.get("supported_features", 0))


def _to_canonical(item: dict[str, Any]) -> CanonicalTask:
    return CanonicalTask(
        title=item["summary"],
        description=item.get("description"),
        status="done" if item.get("status") == "completed" else "open",
        due=_parse_due(item.get("due")),
    )


def _parse_due(value: str | None) -> dt.date | dt.datetime | None:
    if value is None:
        return None
    if len(value) == 10 and "T" not in value:
        return dt.date.fromisoformat(value)
    parsed = dt_util.parse_datetime(value)
    if parsed is None:
        raise ValueError(f"unparseable due value: {value!r}")
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt_util.get_default_time_zone())
    return parsed


def _add_fields(features: int, task: CanonicalTask) -> dict[str, Any]:
    payload: dict[str, Any] = {"item": task.title}
    if task.due is not None:
        payload.update(_due_fields(features, task.due))
    if task.description is not None and features & _SET_DESCRIPTION:
        payload["description"] = task.description
    return payload


def _update_fields(
    features: int, external_id: str, task: CanonicalTask, changed: frozenset[str]
) -> dict[str, Any]:
    payload: dict[str, Any] = {"item": external_id}
    if "title" in changed:
        payload["rename"] = task.title
    if "status" in changed:
        payload["status"] = "completed" if task.status == "done" else "needs_action"
    if "due" in changed:
        if task.due is None:
            payload["due_date"] = None
        else:
            payload.update(_due_fields(features, task.due))
    if "description" in changed and features & _SET_DESCRIPTION:
        payload["description"] = task.description
    return payload


def _due_fields(features: int, due: dt.date | dt.datetime) -> dict[str, Any]:
    if isinstance(due, dt.datetime) and features & _SET_DUE_DATETIME:
        return {"due_datetime": due}
    return {"due_date": due}
