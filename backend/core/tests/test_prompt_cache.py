"""Tests for prompts.cache — FileCache."""

import os
import time
from pathlib import Path
from unittest.mock import patch

import pytest

from tank_backend.prompts.cache import NEGATIVE_CACHE_TTL_S, FileCache


class TestFileCache:
    @pytest.fixture
    def cache(self):
        return FileCache()

    @pytest.fixture
    def tmp_file(self, tmp_path):
        p = tmp_path / "test.md"
        p.write_text("hello world", encoding="utf-8")
        return p

    def test_read_returns_content(self, cache, tmp_file):
        assert cache.read(tmp_file) == "hello world"

    def test_second_read_uses_cache(self, cache, tmp_file):
        cache.read(tmp_file)
        # Patch os.stat to track calls — should still be called (for validation)
        # but file should NOT be re-read
        original_read = Path.read_text
        read_count = 0

        def counting_read(self_path, *a, **kw):
            nonlocal read_count
            read_count += 1
            return original_read(self_path, *a, **kw)

        with patch.object(Path, "read_text", counting_read):
            result = cache.read(tmp_file)

        assert result == "hello world"
        assert read_count == 0  # Should use cached content

    def test_invalidates_on_mtime_change(self, cache, tmp_file):
        cache.read(tmp_file)
        # Modify file (changes mtime)
        time.sleep(0.01)
        tmp_file.write_text("updated content", encoding="utf-8")
        assert cache.read(tmp_file) == "updated content"

    def test_invalidates_on_size_change(self, cache, tmp_file):
        cache.read(tmp_file)
        # Write different-length content
        tmp_file.write_text("short", encoding="utf-8")
        # Even if mtime somehow matches, size differs → cache miss
        result = cache.read(tmp_file)
        assert result == "short"

    def test_returns_none_for_missing_file(self, cache, tmp_path):
        result = cache.read(tmp_path / "nonexistent.md")
        assert result is None

    def test_negative_cache_prevents_repeated_stat(self, cache, tmp_path):
        missing = tmp_path / "gone.md"
        cache.read(missing)  # First miss → enters negative cache

        stat_count = 0
        original_stat = os.stat

        def counting_stat(path, *a, **kw):
            nonlocal stat_count
            stat_count += 1
            return original_stat(path, *a, **kw)

        with patch("tank_backend.prompts.cache.os.stat", counting_stat):
            result = cache.read(missing)

        assert result is None
        assert stat_count == 0  # Negative cache should prevent stat

    def test_negative_cache_expires(self, cache, tmp_path):
        missing = tmp_path / "gone.md"
        cache.read(missing)

        # Simulate time passing beyond TTL
        future = time.monotonic() + NEGATIVE_CACHE_TTL_S + 1
        with patch("tank_backend.prompts.cache.time.monotonic", return_value=future):
            # File still doesn't exist, but negative cache expired → re-stat
            result = cache.read(missing)

        assert result is None

    def test_invalidate_forces_reread(self, cache, tmp_file):
        cache.read(tmp_file)
        tmp_file.write_text("new content", encoding="utf-8")
        cache.invalidate(tmp_file)
        assert cache.read(tmp_file) == "new content"

    def test_invalidate_none_clears_all(self, cache, tmp_file, tmp_path):
        missing = tmp_path / "missing.md"
        cache.read(tmp_file)
        cache.read(missing)

        cache.invalidate(None)

        # Positive cache cleared — will re-read
        read_count = 0
        original_read = Path.read_text

        def counting_read(self_path, *a, **kw):
            nonlocal read_count
            read_count += 1
            return original_read(self_path, *a, **kw)

        with patch.object(Path, "read_text", counting_read):
            cache.read(tmp_file)

        assert read_count == 1

    def test_tilde_expansion(self, cache, tmp_path):
        # Create a file and read it via tilde path
        p = tmp_path / "tilde_test.md"
        p.write_text("tilde content", encoding="utf-8")
        # Read via absolute path first
        assert cache.read(str(p)) == "tilde content"

    def test_file_deleted_after_cache(self, cache, tmp_file):
        cache.read(tmp_file)
        tmp_file.unlink()
        assert cache.read(tmp_file) is None
