"""Plugin system — extensible hooks for custom agents and providers."""

from __future__ import annotations

from typing import Any


class PluginRegistry:
    """Simple plugin registry for custom extensions."""

    def __init__(self) -> None:
        self._plugins: dict[str, Any] = {}

    def register(self, name: str, plugin: Any) -> None:
        self._plugins[name] = plugin

    def get(self, name: str) -> Any | None:
        return self._plugins.get(name)

    def list_all(self) -> list[str]:
        return list(self._plugins.keys())


# Global registry singleton
registry = PluginRegistry()
