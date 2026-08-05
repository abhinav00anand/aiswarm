"""Agent hierarchy — Host-1 Router, Host-2 Fast Manager, Boss, Manager, Planner, ContextSelector, Coder, PreCheck, Critics."""

from aiswarm.agents.host1.router import Host1Router
from aiswarm.agents.host2.manager import Host2CapabilityManager

__all__ = [
    "Host1Router",
    "Host2CapabilityManager",
]
