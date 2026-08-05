"""File ownership tracker — records which agent last modified each file."""

from __future__ import annotations

from aiswarm.memory.repository_memory import RepositoryMemory

# Convenience alias — ownership is tracked in RepositoryMemory
FileOwnershipTracker = RepositoryMemory
