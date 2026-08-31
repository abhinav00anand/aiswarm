"""Hashing utilities — content-addressable identifiers for code artifacts."""

from __future__ import annotations

import hashlib


def sha256_hex(content: str | bytes) -> str:
    """Return the hex SHA-256 digest of content."""
    if isinstance(content, str):
        content = content.encode("utf-8")
    return hashlib.sha256(content).hexdigest()


def xxhash_fast(content: str | bytes) -> str:
    """Return a fast xxhash digest (non-cryptographic, for cache keys)."""
    try:
        import xxhash

        if isinstance(content, str):
            content = content.encode("utf-8")
        return xxhash.xxh64(content).hexdigest()
    except ImportError:
        return sha256_hex(content)


def content_hash(task_id: str, code: str) -> str:
    """Canonical hash for a (task_id, code) pair — used for state validation."""
    return sha256_hex(f"{task_id}:{code}")
