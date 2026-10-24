"""Choosing a plugin by the node string."""

from __future__ import annotations

from .base import Plugin


class PluginRegistry:
    """Ordered registry; the first plugin whose matches() wins."""

    def __init__(self) -> None:
        self._plugins: list[Plugin] = []

    def register(self, plugin: Plugin) -> None:
        self._plugins.append(plugin)

    def for_node(self, node: str) -> Plugin:
        for plugin in self._plugins:
            if plugin.matches(node):
                return plugin
        raise KeyError(f"no registered plugin serves node {node!r}")
