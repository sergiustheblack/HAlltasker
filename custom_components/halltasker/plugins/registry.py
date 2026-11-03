"""Plugin registration and connection-scoped plugin bindings."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
import re
from types import MappingProxyType
from typing import Any

from ..core.model import CanonicalItem, Capabilities, Connection, FieldSpec, Node, NodeListing
from .base import (
    AuthFailed,
    DependencyUnavailable,
    NodeUnavailable,
    Plugin,
    PluginDescriptor,
    UnsupportedTransition,
)

SecretsProvider = Callable[[str], Mapping[str, Any]]

_URL_USERINFO = re.compile(r"(\w+://)[^/@\s]+@")


def _frozen_mapping(values: Mapping[str, Any]) -> Mapping[str, Any]:
    return MappingProxyType(dict(values))


class PluginRegistry:
    """Registry of static plugin descriptors and legacy node matchers."""

    def __init__(self, plugins: Iterable[Plugin] = ()) -> None:
        self._plugins: dict[str, Plugin] = {}
        self._legacy_plugins: list[Plugin] = []
        for plugin in plugins:
            self.register(plugin)

    def register(self, plugin: Plugin) -> None:
        """Register a v2 plugin or retain a v1 matcher during migration."""
        descriptor = getattr(plugin, "descriptor", None)
        if descriptor is None:
            self._legacy_plugins.append(plugin)
            return
        self._validate_descriptor(descriptor)
        if descriptor.plugin_id in self._plugins:
            raise ValueError(f"duplicate plugin id: {descriptor.plugin_id}")
        self._plugins[descriptor.plugin_id] = plugin

    def get(self, plugin_id: str) -> Plugin:
        return self._plugins[plugin_id]

    def descriptors(self) -> dict[str, PluginDescriptor]:
        return {plugin_id: plugin.descriptor for plugin_id, plugin in self._plugins.items()}

    def bind(self, node: Node, connection: Connection, secrets: SecretsProvider) -> BoundNode:
        if node.connection_id != connection.id:
            raise ValueError("node connection_id does not match the supplied connection")
        plugin = self.get(connection.plugin_id)
        return BoundNode(plugin, node, connection, secrets)

    def for_node(self, node: str) -> Plugin:
        """Return the first matching v1 plugin during the migration window."""
        for plugin in self._legacy_plugins:
            matches = getattr(plugin, "matches", None)
            if matches is not None and matches(node):
                return plugin
        raise KeyError(f"no registered plugin serves node {node!r}")

    @staticmethod
    def _validate_descriptor(descriptor: PluginDescriptor) -> None:
        if descriptor.min_interval < 15:
            raise ValueError("min_interval must be at least 15")
        if descriptor.default_interval < descriptor.min_interval:
            raise ValueError("default_interval must not be below min_interval")
        for key, metadata in descriptor.settings_schema.items():
            if bool(metadata.get("secret", False)):
                raise ValueError(f"setting {key!r} must not be secret")
        for key in descriptor.identity_settings:
            if key not in descriptor.settings_schema:
                raise ValueError(f"identity setting {key!r} is undeclared")
        for key in descriptor.identity_credentials:
            metadata = descriptor.credentials_schema.get(key)
            if metadata is None:
                raise ValueError(f"identity credential {key!r} is undeclared")
            if bool(metadata.get("secret", False)):
                raise ValueError(f"identity credential {key!r} cannot be a secret")
        for spec in descriptor.fields:
            _validate_numeric_bounds(spec)


class BoundNode:
    """A runtime binding of one node, connection, plugin and secret provider."""

    def __init__(
        self,
        plugin: Plugin,
        node: Node,
        connection: Connection,
        secrets: SecretsProvider,
    ) -> None:
        self._plugin = plugin
        self._node = node
        self._connection = connection
        self._secrets_provider = secrets
        self.node_id = node.id
        self.connection_id = connection.id

    async def fields(self) -> tuple[FieldSpec, ...]:
        return self._plugin.descriptor.fields

    async def capabilities(self) -> Capabilities:
        return await self._call(self._plugin.capabilities)

    async def list(self) -> NodeListing:
        listing = await self._call(self._plugin.list)
        if not listing.items.keys().isdisjoint(listing.filtered_ids):
            raise NodeUnavailable("listing contains overlapping eligible and filtered ids")
        return listing

    async def create(self, item: CanonicalItem, known_ids: frozenset[str]) -> str:
        return await self._call(self._plugin.create, item, known_ids)

    async def update(self, external_id: str, item: CanonicalItem, changed: frozenset[str]) -> None:
        await self._call(self._plugin.update, external_id, item, changed)

    async def delete(self, external_id: str) -> None:
        await self._call(self._plugin.delete, external_id)

    async def _call(self, operation: Callable[..., Any], *args: Any) -> Any:
        secrets = _frozen_mapping(self._secrets_provider(self.connection_id))
        try:
            return await operation(self._connection, self._node, *args, secrets)
        except UnsupportedTransition:
            raise
        except DependencyUnavailable as err:
            raise DependencyUnavailable(err.domain, self._redact(str(err), secrets)) from None
        except (AuthFailed, NodeUnavailable) as err:
            raise type(err)(self._redact(str(err), secrets)) from None
        except Exception as err:
            raise NodeUnavailable(self._redact(str(err), secrets)) from None

    def _redact(self, message: str, secrets: Mapping[str, Any]) -> str:
        redacted = _URL_USERINFO.sub(r"\1***@", message)
        for value in secrets.values():
            if isinstance(value, str) and value:
                redacted = redacted.replace(value, "***")
        return redacted


def _validate_numeric_bounds(spec: FieldSpec) -> None:
    if (spec.minimum is not None or spec.maximum is not None) and spec.type != "int":
        raise ValueError("numeric bounds are valid only for int fields")
    if spec.minimum is not None and spec.maximum is not None and spec.minimum > spec.maximum:
        raise ValueError("minimum must not exceed maximum")
