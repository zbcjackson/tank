"""Tests for preferences.store — PreferenceStore."""

from __future__ import annotations

from pathlib import Path

from tank_backend.preferences.store import PreferenceStore, _similarity, _slugify


class TestSlugify:
    def test_normal_name(self):
        assert _slugify("Jackson") == "jackson"

    def test_name_with_spaces(self):
        assert _slugify("John Doe") == "john_doe"

    def test_unknown_returns_default(self):
        assert _slugify("Unknown") == "_default"

    def test_empty_returns_default(self):
        assert _slugify("") == "_default"

    def test_special_chars(self):
        assert _slugify("José María") == "jos__mar_a"


class TestSimilarity:
    def test_identical(self):
        assert _similarity("prefers celsius", "prefers celsius") == 1.0

    def test_no_overlap(self):
        assert _similarity("hello world", "foo bar") == 0.0

    def test_partial_overlap(self):
        score = _similarity("prefers weather in celsius", "prefers celsius")
        assert 0.5 < score <= 1.0

    def test_empty_string(self):
        assert _similarity("", "hello") == 0.0
        assert _similarity("hello", "") == 0.0


class TestPreferenceStoreAdd:
    def test_add_creates_file(self, tmp_path: Path):
        store = PreferenceStore(tmp_path, max_entries=20)
        added = store.add_if_new("Jackson", "Prefers Celsius")
        assert added is True

        prefs_file = tmp_path / "users" / "jackson" / "preferences.md"
        assert prefs_file.exists()
        content = prefs_file.read_text()
        assert "Prefers Celsius" in content

    def test_add_deduplicates(self, tmp_path: Path):
        store = PreferenceStore(tmp_path, max_entries=20)
        store.add_if_new("Jackson", "Prefers Celsius")
        added = store.add_if_new("Jackson", "Prefers Celsius")
        assert added is False

    def test_add_allows_different_entries(self, tmp_path: Path):
        store = PreferenceStore(tmp_path, max_entries=20)
        store.add_if_new("Jackson", "Prefers Celsius")
        added = store.add_if_new("Jackson", "Likes brief greetings")
        assert added is True
        assert len(store.list_for_user("Jackson")) == 2

    def test_add_empty_text_rejected(self, tmp_path: Path):
        store = PreferenceStore(tmp_path, max_entries=20)
        assert store.add_if_new("Jackson", "") is False
        assert store.add_if_new("Jackson", "   ") is False

    def test_max_entries_drops_oldest(self, tmp_path: Path):
        store = PreferenceStore(tmp_path, max_entries=3)
        store.add_if_new("Jackson", "Pref A", source="explicit")
        store.add_if_new("Jackson", "Pref B", source="explicit")
        store.add_if_new("Jackson", "Pref C", source="explicit")
        store.add_if_new("Jackson", "Pref D", source="explicit")

        entries = store.list_for_user("Jackson")
        assert len(entries) == 3
        assert "Pref A" not in entries
        assert "Pref D" in entries

    def test_per_user_isolation(self, tmp_path: Path):
        store = PreferenceStore(tmp_path, max_entries=20)
        store.add_if_new("Jackson", "Prefers Chinese")
        store.add_if_new("Alice", "Prefers English")

        assert len(store.list_for_user("Jackson")) == 1
        assert len(store.list_for_user("Alice")) == 1
        assert "Prefers Chinese" in store.list_for_user("Jackson")
        assert "Prefers English" in store.list_for_user("Alice")

    def test_unknown_user_goes_to_default(self, tmp_path: Path):
        store = PreferenceStore(tmp_path, max_entries=20)
        store.add_if_new("Unknown", "Some pref")

        prefs_file = tmp_path / "users" / "_default" / "preferences.md"
        assert prefs_file.exists()


class TestPreferenceStoreRemove:
    def test_remove_by_substring(self, tmp_path: Path):
        store = PreferenceStore(tmp_path, max_entries=20)
        store.add_if_new("Jackson", "Prefers Celsius")
        store.add_if_new("Jackson", "Likes brief greetings")

        removed = store.remove("Jackson", "Celsius")
        assert removed is True
        assert len(store.list_for_user("Jackson")) == 1
        assert "Likes brief greetings" in store.list_for_user("Jackson")

    def test_remove_nonexistent(self, tmp_path: Path):
        store = PreferenceStore(tmp_path, max_entries=20)
        store.add_if_new("Jackson", "Prefers Celsius")
        assert store.remove("Jackson", "nonexistent") is False

    def test_remove_case_insensitive(self, tmp_path: Path):
        store = PreferenceStore(tmp_path, max_entries=20)
        store.add_if_new("Jackson", "Prefers Celsius")
        assert store.remove("Jackson", "celsius") is True


class TestPreferenceStoreRender:
    def test_render_empty(self, tmp_path: Path):
        store = PreferenceStore(tmp_path, max_entries=20)
        assert store.render_for_user("Jackson") == ""

    def test_render_bullet_list(self, tmp_path: Path):
        store = PreferenceStore(tmp_path, max_entries=20)
        store.add_if_new("Jackson", "Prefers Celsius")
        store.add_if_new("Jackson", "Likes brief greetings")

        rendered = store.render_for_user("Jackson")
        assert "- Prefers Celsius" in rendered
        assert "- Likes brief greetings" in rendered

    def test_render_strips_metadata(self, tmp_path: Path):
        """Rendered output should contain clean text, not [source, date] suffixes."""
        store = PreferenceStore(tmp_path, max_entries=20)
        store.add_if_new("Jackson", "Prefers Celsius", source="explicit")

        rendered = store.render_for_user("Jackson")
        assert "- Prefers Celsius" in rendered
        # Metadata suffix should NOT appear in rendered output
        assert "[explicit" not in rendered


class TestPreferenceStoreFileFormat:
    def test_file_contains_metadata(self, tmp_path: Path):
        store = PreferenceStore(tmp_path, max_entries=20)
        store.add_if_new("Jackson", "Prefers Celsius", source="explicit")

        prefs_file = tmp_path / "users" / "jackson" / "preferences.md"
        raw = prefs_file.read_text()
        assert "[explicit," in raw

    def test_roundtrip_preserves_entries(self, tmp_path: Path):
        store = PreferenceStore(tmp_path, max_entries=20)
        store.add_if_new("Jackson", "Prefers Celsius", source="explicit")
        store.add_if_new("Jackson", "Likes brief greetings", source="inferred")

        # Create a new store instance to force re-read from disk
        store2 = PreferenceStore(tmp_path, max_entries=20)
        entries = store2.list_for_user("Jackson")
        assert len(entries) == 2
        assert "Prefers Celsius" in entries
        assert "Likes brief greetings" in entries
