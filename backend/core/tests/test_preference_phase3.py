"""Tests for Phase 3: staleness decay and per-user USER.md overrides."""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

from tank_backend.preferences.store import PreferenceStore


class TestStalenessDecay:
    def test_fresh_entries_not_removed(self, tmp_path: Path):
        store = PreferenceStore(tmp_path, max_entries=20)
        store.add_if_new("Jackson", "Prefers Celsius")

        # Reload store to trigger staleness check
        store2 = PreferenceStore(tmp_path, max_entries=20)
        assert store2.list_for_user("Jackson") == ["Prefers Celsius"]

    def test_stale_entries_auto_removed(self, tmp_path: Path):
        store = PreferenceStore(tmp_path, max_entries=20)

        # Manually create a stale entry (91 days old)
        stale_date = (date.today() - timedelta(days=91)).isoformat()
        prefs_file = tmp_path / "users" / "jackson" / "preferences.md"
        prefs_file.parent.mkdir(parents=True, exist_ok=True)
        prefs_file.write_text(f"- Prefers Celsius [inferred, {stale_date}]\n")

        # Load should auto-remove stale entry
        assert store.list_for_user("Jackson") == []

        # File should be rewritten without the stale entry
        content = prefs_file.read_text()
        assert "Prefers Celsius" not in content

    def test_mixed_fresh_and_stale(self, tmp_path: Path):
        store = PreferenceStore(tmp_path, max_entries=20)

        stale_date = (date.today() - timedelta(days=91)).isoformat()
        fresh_date = date.today().isoformat()
        prefs_file = tmp_path / "users" / "jackson" / "preferences.md"
        prefs_file.parent.mkdir(parents=True, exist_ok=True)
        prefs_file.write_text(
            f"- Stale preference [inferred, {stale_date}]\n"
            f"- Fresh preference [inferred, {fresh_date}]\n"
        )

        entries = store.list_for_user("Jackson")
        assert len(entries) == 1
        assert "Fresh preference" in entries
        assert "Stale preference" not in entries

    def test_exactly_90_days_not_stale(self, tmp_path: Path):
        store = PreferenceStore(tmp_path, max_entries=20)

        # Exactly 90 days old should NOT be removed
        edge_date = (date.today() - timedelta(days=90)).isoformat()
        prefs_file = tmp_path / "users" / "jackson" / "preferences.md"
        prefs_file.parent.mkdir(parents=True, exist_ok=True)
        prefs_file.write_text(f"- Edge case [inferred, {edge_date}]\n")

        assert store.list_for_user("Jackson") == ["Edge case"]


class TestReinforce:
    def test_reinforce_updates_timestamp(self, tmp_path: Path):
        store = PreferenceStore(tmp_path, max_entries=20)

        # Create an old entry
        old_date = (date.today() - timedelta(days=30)).isoformat()
        prefs_file = tmp_path / "users" / "jackson" / "preferences.md"
        prefs_file.parent.mkdir(parents=True, exist_ok=True)
        prefs_file.write_text(f"- Prefers Celsius [inferred, {old_date}]\n")

        # Reinforce it
        assert store.reinforce("Jackson", "Celsius") is True

        # Check file was updated with today's date
        content = prefs_file.read_text()
        assert date.today().isoformat() in content
        assert old_date not in content

    def test_reinforce_nonexistent_returns_false(self, tmp_path: Path):
        store = PreferenceStore(tmp_path, max_entries=20)
        store.add_if_new("Jackson", "Prefers Celsius")
        assert store.reinforce("Jackson", "nonexistent") is False

    def test_reinforce_prevents_staleness(self, tmp_path: Path):
        store = PreferenceStore(tmp_path, max_entries=20)

        # Create an entry that's 89 days old (close to stale)
        old_date = (date.today() - timedelta(days=89)).isoformat()
        prefs_file = tmp_path / "users" / "jackson" / "preferences.md"
        prefs_file.parent.mkdir(parents=True, exist_ok=True)
        prefs_file.write_text(f"- Prefers Celsius [inferred, {old_date}]\n")

        # Reinforce it
        store.reinforce("Jackson", "Celsius")

        # Fast-forward 10 days (would be 99 days old without reinforce)
        # Simulate by manually setting a date 99 days ago
        very_old_date = (date.today() - timedelta(days=99)).isoformat()
        prefs_file.write_text(f"- Prefers Celsius [inferred, {very_old_date}]\n")

        # Without reinforce, this would be stale
        assert store.list_for_user("Jackson") == []

        # But with reinforce (today's date), it survives
        prefs_file.write_text(f"- Prefers Celsius [inferred, {date.today().isoformat()}]\n")
        assert store.list_for_user("Jackson") == ["Prefers Celsius"]


class TestPerUserUserMd:
    def test_per_user_override_takes_precedence(self, tmp_path: Path):
        store = PreferenceStore(tmp_path, max_entries=20)

        # Add learned preference
        store.add_if_new("Jackson", "Prefers Celsius")

        # Create per-user USER.md override
        user_md = tmp_path / "users" / "jackson" / "USER.md"
        user_md.parent.mkdir(parents=True, exist_ok=True)
        user_md.write_text("EXPLICIT: Always use Fahrenheit\n")

        rendered = store.render_for_user("Jackson")
        assert "EXPLICIT: Always use Fahrenheit" in rendered
        assert "Prefers Celsius" in rendered
        # Explicit should come first
        assert rendered.index("EXPLICIT") < rendered.index("Celsius")

    def test_per_user_override_without_learned(self, tmp_path: Path):
        store = PreferenceStore(tmp_path, max_entries=20)

        # Only per-user USER.md, no learned preferences
        user_md = tmp_path / "users" / "jackson" / "USER.md"
        user_md.parent.mkdir(parents=True, exist_ok=True)
        user_md.write_text("Custom preferences for Jackson\n")

        rendered = store.render_for_user("Jackson")
        assert rendered == "Custom preferences for Jackson"

    def test_learned_without_per_user_override(self, tmp_path: Path):
        store = PreferenceStore(tmp_path, max_entries=20)
        store.add_if_new("Jackson", "Prefers Celsius")

        # No per-user USER.md
        rendered = store.render_for_user("Jackson")
        assert rendered == "- Prefers Celsius"

    def test_empty_per_user_override_ignored(self, tmp_path: Path):
        store = PreferenceStore(tmp_path, max_entries=20)
        store.add_if_new("Jackson", "Prefers Celsius")

        # Empty per-user USER.md
        user_md = tmp_path / "users" / "jackson" / "USER.md"
        user_md.parent.mkdir(parents=True, exist_ok=True)
        user_md.write_text("   \n")

        rendered = store.render_for_user("Jackson")
        assert rendered == "- Prefers Celsius"

    def test_per_user_override_different_users(self, tmp_path: Path):
        store = PreferenceStore(tmp_path, max_entries=20)

        # Jackson has override
        jackson_md = tmp_path / "users" / "jackson" / "USER.md"
        jackson_md.parent.mkdir(parents=True, exist_ok=True)
        jackson_md.write_text("Jackson's custom prefs\n")

        # Alice has learned only
        store.add_if_new("Alice", "Prefers Fahrenheit")

        assert "Jackson's custom prefs" in store.render_for_user("Jackson")
        assert "Prefers Fahrenheit" in store.render_for_user("Alice")
        assert "Jackson's custom prefs" not in store.render_for_user("Alice")


class TestBackwardsCompatibility:
    def test_old_format_without_date_still_works(self, tmp_path: Path):
        """Entries without dates should get today's date on load."""
        store = PreferenceStore(tmp_path, max_entries=20)

        # Old format: no date in metadata
        prefs_file = tmp_path / "users" / "jackson" / "preferences.md"
        prefs_file.parent.mkdir(parents=True, exist_ok=True)
        prefs_file.write_text("- Prefers Celsius [explicit]\n")

        # Should load successfully
        assert store.list_for_user("Jackson") == ["Prefers Celsius"]

        # After save, should have today's date
        store.add_if_new("Jackson", "Another pref")
        content = prefs_file.read_text()
        assert date.today().isoformat() in content

    def test_entries_without_metadata_get_today(self, tmp_path: Path):
        """Entries with no metadata at all should work."""
        store = PreferenceStore(tmp_path, max_entries=20)

        prefs_file = tmp_path / "users" / "jackson" / "preferences.md"
        prefs_file.parent.mkdir(parents=True, exist_ok=True)
        prefs_file.write_text("- Prefers Celsius\n")

        assert store.list_for_user("Jackson") == ["Prefers Celsius"]
