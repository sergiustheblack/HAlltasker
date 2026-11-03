"""The pure v2 plugin contract."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Literal

from ..core.model import (
    FIELDS,
    CanonicalItem,
    CanonicalTask,
    Capabilities,
    Connection,
    Container,
    FieldSpec,
    Node,
    NodeListing,
    ValueMap,
)


def _frozen_mapping(values: Mapping[str, Any]) -> Mapping[str, Any]:
    return MappingProxyType(dict(values))


@dataclass(frozen=True)
class PluginDescriptor:
    """Static metadata describing one plugin implementation."""

    plugin_id: str
    name: str
    credentials_schema: Mapping[str, Any]
    settings_schema: Mapping[str, Any]
    fields: tuple[FieldSpec, ...]
    credential_kind: Literal["none", "basic", "token"]
    default_interval: int = 300
    min_interval: int = 15
    kinds: tuple[str, ...] = ("task",)
    default_value_maps: Mapping[str, ValueMap] = field(default_factory=dict)
    single_connection: bool = False
    identity_settings: tuple[str, ...] = ()
    identity_credentials: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "credentials_schema", _frozen_mapping(self.credentials_schema))
        object.__setattr__(self, "settings_schema", _frozen_mapping(self.settings_schema))
        object.__setattr__(self, "fields", tuple(self.fields))
        object.__setattr__(self, "kinds", tuple(self.kinds))
        object.__setattr__(self, "default_value_maps", _frozen_mapping(self.default_value_maps))
        object.__setattr__(self, "identity_settings", tuple(self.identity_settings))
        object.__setattr__(self, "identity_credentials", tuple(self.identity_credentials))


@dataclass(frozen=True)
class PluginSchema:
    """The retained v1 schema facade."""

    plugin_id: str
    fields: frozenset[str]
    extensions: frozenset[str]

    @classmethod
    def all_canonical(cls, plugin_id: str) -> PluginSchema:
        return cls(plugin_id=plugin_id, fields=frozenset(FIELDS), extensions=frozenset())


class AuthFailed(Exception):
    """The supplied credentials were rejected."""


class NodeUnavailable(Exception):
    """The node cannot be read or written right now."""


class UnsupportedTransition(Exception):
    """A valid node cannot perform the requested transition."""


class DependencyUnavailable(NodeUnavailable):
    """A required Home Assistant integration is unavailable."""

    def __init__(self, domain: str, message: str) -> None:
        super().__init__(message)
        self.domain = domain


async def _legacy_validate(connection: Connection, secrets: Mapping[str, str]) -> None:
    return None


async def _legacy_containers(connection: Connection, secrets: Mapping[str, Any]) -> list[Container]:
    raise NotImplementedError


class Plugin(ABC):
    """Converts between one plugin's native items and core items."""

    descriptor: PluginDescriptor

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        if "matches" in cls.__dict__:
            if "validate" not in cls.__dict__:
                cls.validate = _legacy_validate
            if "containers" not in cls.__dict__:
                cls.containers = _legacy_containers

    @abstractmethod
    async def validate(self, connection: Connection, secrets: Mapping[str, str]) -> None:
        """Validate credentials before a connection is stored."""
        raise NotImplementedError

    @abstractmethod
    async def containers(
        self, connection: Connection, secrets: Mapping[str, Any]
    ) -> list[Container]:
        """Return containers visible to the supplied connection."""
        raise NotImplementedError

    @abstractmethod
    async def capabilities(
        self, connection: Connection, node: Node, secrets: Mapping[str, Any]
    ) -> Capabilities:
        """Return native capabilities for one bound node."""
        raise NotImplementedError

    @abstractmethod
    async def list(
        self, connection: Connection, node: Node, secrets: Mapping[str, Any]
    ) -> NodeListing:
        """Return a complete native listing."""
        raise NotImplementedError

    @abstractmethod
    async def create(
        self,
        connection: Connection,
        node: Node,
        item: CanonicalItem,
        known_ids: frozenset[str],
        secrets: Mapping[str, Any],
    ) -> str:
        """Create one native item and return its external id."""
        raise NotImplementedError

    @abstractmethod
    async def update(
        self,
        connection: Connection,
        node: Node,
        external_id: str,
        item: CanonicalItem,
        changed: frozenset[str],
        secrets: Mapping[str, Any],
    ) -> None:
        """Write exactly the changed native fields."""
        raise NotImplementedError

    @abstractmethod
    async def delete(
        self,
        connection: Connection,
        node: Node,
        external_id: str,
        secrets: Mapping[str, Any],
    ) -> None:
        """Delete one native item."""
        raise NotImplementedError


LegacyTask = CanonicalTask
