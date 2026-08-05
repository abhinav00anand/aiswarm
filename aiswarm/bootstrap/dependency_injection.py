"""Dependency injection container — provides shared service instances."""

from __future__ import annotations

from typing import Any


class ServiceContainer:
    """
    Simple dependency injection container.

    Stores singleton service instances by type name.
    Supports lazy initialization via factory functions.
    """

    def __init__(self) -> None:
        self._singletons: dict[str, Any] = {}
        self._factories: dict[str, Any] = {}

    def register_singleton(self, name: str, instance: Any) -> None:
        self._singletons[name] = instance

    def register_factory(self, name: str, factory: Any) -> None:
        self._factories[name] = factory

    def resolve(self, name: str) -> Any:
        if name in self._singletons:
            return self._singletons[name]
        if name in self._factories:
            instance = self._factories[name]()
            self._singletons[name] = instance  # cache after first creation
            return instance
        raise KeyError(f"Service '{name}' not registered in container")

    def is_registered(self, name: str) -> bool:
        return name in self._singletons or name in self._factories


# Global DI container
container = ServiceContainer()
