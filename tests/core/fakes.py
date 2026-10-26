"""Test fakes for the core: storage and plugin doubles."""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from custom_components.halltasker.core.model import (
    CanonicalTask,
    Capabilities,
)
from custom_components.halltasker.plugins.base import (
    NodeUnavailable,
    Plugin,
    PluginSchema,
)

FULL_CAPS = Capabilities(create=True, update=True, delete=True, due="datetime", description=True)


class FakeStorage:
    """In-memory replacement for the HA storage helper."""

    def __init__(self, data: dict[str, Any] | None = None) -> None:
        self.data = data
        self.saves = 0

    async def async_load(self) -> dict[str, Any] | None:
        return self.data

    async def async_save(self, data: dict[str, Any]) -> None:
        self.data = data
        self.saves += 1


class FakePlugin(Plugin):
    """In-memory node double with controllable lists, caps, failures, and a call log."""

    def __init__(self) -> None:
        self.schema = PluginSchema.all_canonical("fake")
        self.items: dict[str, dict[str, CanonicalTask]] = {}
        self.caps: dict[str, Capabilities] = {}
        self.calls: list[tuple] = []
        self.fail: set[str] = set()
        self._next_id = 0

    def matches(self, node: str) -> bool:
        return node.startswith("fake.")

    def add(self, node: str, task: CanonicalTask) -> str:
        """Puts a task into a node and returns its external id."""
        self._next_id += 1
        external_id = f"ext-{self._next_id}"
        self.items.setdefault(node, {})[external_id] = task
        self.caps.setdefault(node, FULL_CAPS)
        return external_id

    async def capabilities(self, node: str) -> Capabilities:
        self.calls.append(("capabilities", node))
        if node in self.fail:
            raise NodeUnavailable(node)
        return self.caps[node]

    async def list(self, node: str) -> dict[str, CanonicalTask]:
        self.calls.append(("list", node))
        if node in self.fail:
            raise NodeUnavailable(node)
        return dict(self.items.get(node, {}))

    async def create(self, node: str, task: CanonicalTask, known_ids: frozenset[str]) -> str:
        external_id = self.add(node, task)
        self.calls.append(("create", node, external_id, task))
        return external_id

    async def update(
        self,
        node: str,
        external_id: str,
        task: CanonicalTask,
        changed: frozenset[str],
    ) -> None:
        current = self.items[node][external_id]
        merged = replace(
            current,
            **{field: getattr(task, field) for field in changed},
        )
        self.items[node][external_id] = merged
        self.calls.append(("update", node, external_id, task, changed))

    async def delete(self, node: str, external_id: str) -> None:
        del self.items[node][external_id]
        self.calls.append(("delete", node, external_id))
