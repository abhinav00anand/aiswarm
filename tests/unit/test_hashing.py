"""Unit tests for content-hashing utilities."""

from __future__ import annotations

from aiswarm.utils.hashing import sha256_hex, xxhash_fast, content_hash


class TestSha256Hex:
    def test_known_vector_empty_string(self) -> None:
        assert (
            sha256_hex("")
            == "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"[:64]
        )

    def test_string_and_bytes_produce_same_digest(self) -> None:
        assert sha256_hex("hello") == sha256_hex(b"hello")

    def test_digest_length_is_64_hex_chars(self) -> None:
        digest = sha256_hex("aiswarm")
        assert len(digest) == 64
        assert all(c in "0123456789abcdef" for c in digest)

    def test_different_inputs_produce_different_digests(self) -> None:
        assert sha256_hex("a") != sha256_hex("b")

    def test_deterministic_across_calls(self) -> None:
        assert sha256_hex("repeat") == sha256_hex("repeat")


class TestXxhashFast:
    def test_returns_nonempty_string(self) -> None:
        assert isinstance(xxhash_fast("content"), str)
        assert len(xxhash_fast("content")) > 0

    def test_deterministic(self) -> None:
        assert xxhash_fast("same") == xxhash_fast("same")

    def test_bytes_input_supported(self) -> None:
        assert xxhash_fast(b"bytes-input") == xxhash_fast("bytes-input")


class TestContentHash:
    def test_combines_task_id_and_code(self) -> None:
        h1 = content_hash("task-1", "print(1)")
        h2 = content_hash("task-2", "print(1)")
        assert h1 != h2  # task_id changes hash even with same code

    def test_same_inputs_same_hash(self) -> None:
        assert content_hash("t", "code") == content_hash("t", "code")

    def test_code_change_changes_hash(self) -> None:
        h1 = content_hash("t", "print(1)")
        h2 = content_hash("t", "print(2)")
        assert h1 != h2
