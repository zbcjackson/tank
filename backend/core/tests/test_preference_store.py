"""Tests for preferences.store — PreferenceStore."""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

from tank_backend.preferences.store import PreferenceStore, _similarity, _slugify


class TestSlugify:
    def test_normal_name(self):
        assert _slugify("Jackson") == "jackson"

    def test_name_with_spaces(self):
        assert _slugify("John Doe") == "john_doe"

    def test_unknown_returns_default(self):
        assert _slugify("Unknown") == "_default"

    def test_guest_returns_default(self):
        assert _slugify("Guest") == "_default"

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

    def test_guest_users_rejected(self, tmp_path: Path):
        store = PreferenceStore(tmp_path, max_entries=20)
        assert store.add_if_new("Unknown", "Some pref") is False
        assert store.add_if_new("Guest", "Some pref") is False
        assert store.add_if_new("", "Some pref") is False

        prefs_file = tmp_path / "users" / "_default" / "preferences.md"
        assert not prefs_file.exists()

    def test_guest_users_render_empty(self, tmp_path: Path):
        store = PreferenceStore(tmp_path, max_entries=20)
        assert store.render_for_user("Unknown") == ""
        assert store.render_for_user("Guest") == ""
        assert store.render_for_user("") == ""

    def test_guest_users_list_empty(self, tmp_path: Path):
        store = PreferenceStore(tmp_path, max_entries=20)
        assert store.list_for_user("Unknown") == []
        assert store.list_for_user("Guest") == []


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


class TestPreferenceStorePinnedTier:
    def test_pinned_skips_max_entries_cap(self, tmp_path: Path):
        """Adding 25 distinct pinned entries with cap=3 keeps all 25."""
        store = PreferenceStore(tmp_path, max_entries=3)
        # Use distinct phrases to avoid the >0.6 token-overlap dedup
        facts = [
            "allergic to peanuts", "drives a tesla", "speaks spanish",
            "lives in tokyo", "wakes up at 6am", "loves jazz music",
            "born in november", "has two cats", "vegetarian since 2020",
            "left handed", "wears glasses", "married to alice",
            "plays piano weekly", "studied physics", "owns a kayak",
            "afraid of heights", "former marine", "blood type O negative",
            "knows morse code", "trained as electrician",
            "rides a motorcycle", "favorite color blue", "writes poetry",
            "collects stamps", "speaks mandarin",
        ]
        for fact in facts:
            store.add_if_new("Jackson", fact, source="pinned")

        entries = store.list_for_user("Jackson")
        assert len(entries) == 25
        assert "allergic to peanuts" in entries
        assert "speaks mandarin" in entries

    def test_pinned_does_not_count_toward_cap(self, tmp_path: Path):
        """Pinned entries don't consume the cap budget — non-pinned still works."""
        store = PreferenceStore(tmp_path, max_entries=2)
        store.add_if_new("Jackson", "Pinned A", source="pinned")
        store.add_if_new("Jackson", "Pinned B", source="pinned")
        store.add_if_new("Jackson", "Pinned C", source="pinned")
        # Now add 3 inferred — only 2 should remain (cap), all 3 pinned stay.
        store.add_if_new("Jackson", "Inferred X", source="inferred")
        store.add_if_new("Jackson", "Inferred Y", source="inferred")
        store.add_if_new("Jackson", "Inferred Z", source="inferred")

        entries = store.list_for_user("Jackson")
        # 3 pinned + 2 inferred (X dropped, oldest non-pinned)
        assert len(entries) == 5
        assert "Pinned A" in entries
        assert "Pinned B" in entries
        assert "Pinned C" in entries
        assert "Inferred X" not in entries
        assert "Inferred Z" in entries

    def test_pinned_survives_staleness_sweep(self, tmp_path: Path):
        """A 100-day-old pinned entry is preserved on load."""
        store = PreferenceStore(tmp_path, max_entries=20)
        prefs_file = tmp_path / "users" / "jackson" / "preferences.md"
        prefs_file.parent.mkdir(parents=True, exist_ok=True)

        old_date = (date.today() - timedelta(days=100)).isoformat()
        prefs_file.write_text(
            f"- Allergic to peanuts [pinned, {old_date}]\n"
            f"- Old learned fact [inferred, {old_date}]\n",
            encoding="utf-8",
        )

        entries = store.list_for_user("Jackson")
        assert "Allergic to peanuts" in entries
        # Inferred should be swept away (older than 90 days)
        assert "Old learned fact" not in entries

    def test_render_pins_first(self, tmp_path: Path):
        """Pinned entries render before non-pinned in `render_for_user`."""
        store = PreferenceStore(tmp_path, max_entries=20)
        store.add_if_new("Jackson", "Inferred fact", source="inferred")
        store.add_if_new("Jackson", "Pinned fact", source="pinned")

        rendered = store.render_for_user("Jackson")
        assert rendered.index("Pinned fact") < rendered.index("Inferred fact")

    def test_unsuffixed_bullet_treated_as_pinned(self, tmp_path: Path):
        """Hand-written bullets without [source, date] suffix become pinned."""
        store = PreferenceStore(tmp_path, max_entries=20)
        prefs_file = tmp_path / "users" / "jackson" / "preferences.md"
        prefs_file.parent.mkdir(parents=True, exist_ok=True)
        prefs_file.write_text(
            "- Hand-written never-expire fact\n",
            encoding="utf-8",
        )

        # Should survive load (treated as pinned, immune to staleness)
        entries = store.list_for_user("Jackson")
        assert "Hand-written never-expire fact" in entries

        # Specifically, list_pinned should include it
        pinned = store.list_pinned("Jackson")
        assert pinned == ["Hand-written never-expire fact"]

    def test_list_pinned_returns_only_pinned(self, tmp_path: Path):
        store = PreferenceStore(tmp_path, max_entries=20)
        store.add_if_new("Jackson", "Pinned A", source="pinned")
        store.add_if_new("Jackson", "Inferred B", source="inferred")
        store.add_if_new("Jackson", "Explicit C", source="explicit")

        pinned = store.list_pinned("Jackson")
        assert pinned == ["Pinned A"]

    def test_list_pinned_guest_returns_empty(self, tmp_path: Path):
        store = PreferenceStore(tmp_path, max_entries=20)
        assert store.list_pinned("Unknown") == []
        assert store.list_pinned("Guest") == []

    def test_pinned_dedupe_still_applies(self, tmp_path: Path):
        """Pinning a duplicate is still rejected by the similarity dedupe."""
        store = PreferenceStore(tmp_path, max_entries=20)
        assert store.add_if_new("Jackson", "Allergic to peanuts", source="pinned")
        assert not store.add_if_new(
            "Jackson", "allergic to peanuts", source="pinned",
        )

    def test_pinned_roundtrip(self, tmp_path: Path):
        """Pinned source is persisted with `[pinned, date]` suffix."""
        store = PreferenceStore(tmp_path, max_entries=20)
        store.add_if_new("Jackson", "Allergic to peanuts", source="pinned")

        prefs_file = tmp_path / "users" / "jackson" / "preferences.md"
        raw = prefs_file.read_text()
        assert "[pinned," in raw

        # Reload and check it's still recognized as pinned
        store2 = PreferenceStore(tmp_path, max_entries=20)
        assert store2.list_pinned("Jackson") == ["Allergic to peanuts"]

