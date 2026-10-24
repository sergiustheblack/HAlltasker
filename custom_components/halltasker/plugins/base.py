"""The plugin contract: one abstraction for every kind of node."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from ..core.model import FIELDS, CanonicalTask, Capabilities


@dataclass(frozen=True)
class PluginSchema:
    """What a plugin can read and write."""

    plugin_id: str
    fields: frozenset[str]
    extensions: frozenset[str]

    @classmethod
    def all_canonical(cls, plugin_id: str) -> PluginSchema:
        return cls(plugin_id=plugin_id, fields=frozenset(FIELDS), extensions=frozenset())


class Plugin(ABC):
    """Converts between canonical tasks and items of one kind of node."""

    schema: PluginSchema

    @abstractmethod
    def matches(self, node: str) -> bool:
        """Whether the plugin serves the node string."""

    @abstractmethod
    async def capabilities(self, node: str) -> Capabilities:
        """Capabilities of the given node. Raises NodeUnavailable."""

    @abstractmethod
    async def list(self, node: str) -> dict[str, CanonicalTask]:
        """Full list: external_id -> task. Raises NodeUnavailable on any error.

        Returning a partial result is forbidden."""

    @abstractmethod
    async def create(self, node: str, task: CanonicalTask, known_ids: frozenset[str]) -> str:
        """Creates an item, returns external_id. known_ids — ids already known to the core."""

    @abstractmethod
    async def update(
        self, node: str, external_id: str, task: CanonicalTask, changed: frozenset[str]
    ) -> None:
        """Writes only the fields from changed."""

    @abstractmethod
    async def delete(self, node: str, external_id: str) -> None: ...


class NodeUnavailable(Exception):
    """The node cannot be read or written right now."""
