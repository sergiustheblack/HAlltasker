"""Tests for the plugin registry."""

from __future__ import annotations

import pytest

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
