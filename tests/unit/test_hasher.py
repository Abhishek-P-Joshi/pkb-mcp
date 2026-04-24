import pytest
from src.connectors.hasher import hash_file, hash_text


class TestHasher:

    def test_hash_file_returns_string(self, tmp_path):
        f = tmp_path / "test.txt"
        f.write_text("hello world")
        result = hash_file(str(f))
        assert isinstance(result, str)
        assert len(result) == 32  # MD5 hex digest length

    def test_same_content_same_hash(self, tmp_path):
        f1 = tmp_path / "a.txt"
        f2 = tmp_path / "b.txt"
        f1.write_text("identical content")
        f2.write_text("identical content")
        assert hash_file(str(f1)) == hash_file(str(f2))

    def test_different_content_different_hash(self, tmp_path):
        f1 = tmp_path / "a.txt"
        f2 = tmp_path / "b.txt"
        f1.write_text("content A")
        f2.write_text("content B")
        assert hash_file(str(f1)) != hash_file(str(f2))

    def test_changing_file_changes_hash(self, tmp_path):
        f = tmp_path / "test.txt"
        f.write_text("original content")
        hash1 = hash_file(str(f))
        f.write_text("modified content")
        hash2 = hash_file(str(f))
        assert hash1 != hash2

    def test_hash_text_returns_string(self):
        result = hash_text("hello world")
        assert isinstance(result, str)
        assert len(result) == 32

    def test_hash_text_deterministic(self):
        assert hash_text("same text") == hash_text("same text")

    def test_hash_text_different_inputs_different_hashes(self):
        assert hash_text("text A") != hash_text("text B")

    def test_large_file_hashes_correctly(self, tmp_path):
        f = tmp_path / "large.txt"
        f.write_text("x" * 100_000)
        result = hash_file(str(f))
        assert isinstance(result, str)
        assert len(result) == 32
