"""Agent registry."""

from __future__ import annotations

from typing import Any


class AgentRegistry:
    """Central registry for all agent instances by role name."""

    def __init__(self) -> None:
        self._agents: dict[str, Any] = {}

    def register(self, role: str, agent: Any) -> None:
        if role in self._agents:
            raise ValueError(f"Agent role '{role}' already registered")
        self._agents[role] = agent

    def get(self, role: str) -> Any:
        agent = self._agents.get(role)
        if agent is None:
            raise KeyError(f"No agent registered for role '{role}'")
        return agent

    def get_optional(self, role: str) -> Any | None:
        return self._agents.get(role)

    def list_roles(self) -> list[str]:
        return list(self._agents.keys())

    def __contains__(self, role: str) -> bool:
        return role in self._agents
