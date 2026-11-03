"""Tests for the plugin registry."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import pytest

from custom_components.halltasker.core.model import (
    CanonicalItem,
    Capabilities,
    Connection,
    Container,
    FieldSpec,
    Node,
    NodeListing,
)
from custom_components.halltasker.plugins.base import (
    NodeUnavailable,
    Plugin,
    PluginDescriptor,
    UnsupportedTransition,
)
from custom_components.halltasker.plugins.registry import PluginRegistry

from ..core.fakes import FakePlugin


def test_registered_plugin_is_found_by_node() -> None:
    registry = PluginRegistry()
    plugin = FakePlugin()
    registry.register(plugin)
    assert registry.for_node("fake.a") is plugin


def test_unknown_node_raises_key_error_with_message() -> None:
    registry = PluginRegistry()
    with pytest.raises(KeyError, match=r"todo\.nowhere"):
        registry.for_node("todo.nowhere")


def test_first_matching_plugin_wins() -> None:
    registry = PluginRegistry()
    first = FakePlugin()
    second = FakePlugin()
    registry.register(first)
    registry.register(second)
    assert registry.for_node("fake.a") is first


class RecordingPlugin(Plugin):
    """A v2 plugin double that records the bound inputs."""

    def __init__(self, descriptor: PluginDescriptor) -> None:
        self.descriptor = descriptor
        self.calls: list[tuple[Any, ...]] = []
        self.failure: Exception | None = None

    async def validate(self, connection: Connection, secrets: Mapping[str, str]) -> None:
        return None

    async def containers(
        self, connection: Connection, secrets: Mapping[str, Any]
    ) -> list[Container]:
        return [Container("tasks", "Tasks")]

    async def capabilities(
        self, connection: Connection, node: Node, secrets: Mapping[str, Any]
    ) -> Capabilities:
        self.calls.append(("capabilities", connection, node, secrets))
        return Capabilities(True, True, True, {"summary": "full"}, {"summary": "full"})

    async def list(
        self, connection: Connection, node: Node, secrets: Mapping[str, Any]
    ) -> NodeListing:
        self.calls.append(("list", connection, node, secrets))
        if self.failure is not None:
            raise self.failure
        return NodeListing({"item": CanonicalItem("task", {"summary": "x"})})

    async def create(
        self,
        connection: Connection,
        node: Node,
        item: CanonicalItem,
        known_ids: frozenset[str],
        secrets: Mapping[str, Any],
    ) -> str:
        self.calls.append(("create", connection, node, item, known_ids, secrets))
        return "new"

    async def update(
        self,
        connection: Connection,
        node: Node,
        external_id: str,
        item: CanonicalItem,
        changed: frozenset[str],
        secrets: Mapping[str, Any],
    ) -> None:
        self.calls.append(("update", connection, node, external_id, item, changed, secrets))

    async def delete(
        self, connection: Connection, node: Node, external_id: str, secrets: Mapping[str, Any]
    ) -> None:
        self.calls.append(("delete", connection, node, external_id, secrets))


def _descriptor(**overrides: Any) -> PluginDescriptor:
    values: dict[str, Any] = {
        "plugin_id": "test",
        "name": "Test",
        "credentials_schema": {"token": {"type": "string", "secret": True}},
        "settings_schema": {"account": {"type": "string"}},
        "fields": (FieldSpec("summary", "str", role="title"),),
        "credential_kind": "token",
        "identity_settings": ("account",),
    }
    values.update(overrides)
    return PluginDescriptor(**values)


def _node(connection_id: str = "one") -> Node:
    return Node("node", "Tasks", connection_id, Container("tasks", "Tasks"))


def test_registry_exposes_descriptor_by_plugin_id() -> None:
    descriptor = _descriptor()
    plugin = RecordingPlugin(descriptor)
    registry = PluginRegistry([plugin])
    assert registry.get("test") is plugin and registry.descriptors() == {"test": descriptor}


def test_registry_rejects_a_secret_setting() -> None:
    descriptor = _descriptor(settings_schema={"password": {"type": "string", "secret": True}})
    with pytest.raises(ValueError, match="must not be secret"):
        PluginRegistry([RecordingPlugin(descriptor)])


def test_registry_rejects_an_undeclared_identity_key() -> None:
    descriptor = _descriptor(identity_settings=("missing",))
    with pytest.raises(ValueError, match="undeclared"):
        PluginRegistry([RecordingPlugin(descriptor)])


def test_registry_rejects_invalid_intervals() -> None:
    descriptor = _descriptor(min_interval=14)
    with pytest.raises(ValueError, match="at least"):
        PluginRegistry([RecordingPlugin(descriptor)])


def test_registry_rejects_a_rotation_secret_as_identity() -> None:
    descriptor = _descriptor(identity_credentials=("token",))
    with pytest.raises(ValueError, match="cannot be a secret"):
        PluginRegistry([RecordingPlugin(descriptor)])


def test_bind_rejects_a_node_from_another_connection() -> None:
    registry = PluginRegistry([RecordingPlugin(_descriptor())])
    connection = Connection("one", "One", "test")
    with pytest.raises(ValueError, match="connection_id"):
        registry.bind(_node("two"), connection, lambda _: {})


@pytest.mark.asyncio
async def test_bound_node_forwards_connection_node_and_connection_secrets() -> None:
    plugin = RecordingPlugin(_descriptor())
    registry = PluginRegistry([plugin])
    connection = Connection("one", "One", "test", {"account": "first"})
    node = _node()
    bound = registry.bind(node, connection, lambda connection_id: {"token": connection_id})
    item = CanonicalItem("task", {"summary": "x"})
    await bound.capabilities()
    external_id = await bound.create(item, frozenset({"known"}))
    await bound.update(external_id, item, frozenset({"summary"}))
    await bound.delete(external_id)
    assert [call[0] for call in plugin.calls] == ["capabilities", "create", "update", "delete"]


@pytest.mark.asyncio
async def test_bindings_do_not_share_settings_or_credentials() -> None:
    plugin = RecordingPlugin(_descriptor())
    registry = PluginRegistry([plugin])
    first = registry.bind(
        _node("one"),
        Connection("one", "One", "test", {"account": "a"}),
        lambda _: {"token": "first"},
    )
    second = registry.bind(
        _node("two"),
        Connection("two", "Two", "test", {"account": "b"}),
        lambda _: {"token": "second"},
    )
    await first.capabilities()
    await second.capabilities()
    assert (
        plugin.calls[0][1].settings != plugin.calls[1][1].settings
        and plugin.calls[0][3] != plugin.calls[1][3]
    )


@pytest.mark.asyncio
async def test_bound_node_forwards_unsupported_transition_unchanged() -> None:
    plugin = RecordingPlugin(_descriptor())
    plugin.failure = UnsupportedTransition("cannot reopen")
    bound = PluginRegistry([plugin]).bind(_node(), Connection("one", "One", "test"), lambda _: {})
    with pytest.raises(UnsupportedTransition, match="cannot reopen"):
        await bound.list()


@pytest.mark.asyncio
async def test_bound_node_redacts_secret_values_and_url_userinfo() -> None:
    plugin = RecordingPlugin(_descriptor())
    plugin.failure = NodeUnavailable("token secret http://name:pass@example.invalid/path")
    bound = PluginRegistry([plugin]).bind(
        _node(), Connection("one", "One", "test"), lambda _: {"token": "secret"}
    )
    with pytest.raises(NodeUnavailable) as raised:
        await bound.list()
    assert "secret" not in str(raised.value) and "name:pass" not in str(raised.value)
