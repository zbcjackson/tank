#!/usr/bin/env python3
"""Example script demonstrating speaker identification usage."""

from __future__ import annotations

import numpy as np
from pathlib import Path

from tank_backend.audio.input.voiceprint_factory import create_voiceprint_recognizer
from tank_backend.audio.input.voiceprint import Utterance
from tank_backend.plugin import AppConfig


def _get_speaker_db_path(app_config: AppConfig) -> str:
    """Read the speaker DB path from config.yaml."""
    return app_config.get_slot_config("speaker").config.get("db_path", "../data/speakers.db")


def generate_sample_audio(duration_s: float = 3.0, sample_rate: int = 16000) -> np.ndarray:
    """
    Generate sample audio for demonstration.

    In real usage, you would load actual voice recordings.
    """
    n_samples = int(duration_s * sample_rate)
    # Generate random audio (in real usage, this would be actual voice)
    audio = np.random.randn(n_samples).astype(np.float32) * 0.1
    return audio


def example_enrollment():
    """Example: Enroll multiple speakers."""
    print("=" * 60)
    print("Example 1: Speaker Enrollment")
    print("=" * 60)

    # Load configuration
    app_config = AppConfig()

    # Create recognizer
    recognizer = create_voiceprint_recognizer(app_config)

    if not recognizer.enabled:
        print("\n⚠️  Speaker identification is disabled in configuration.")
        print("   Set ENABLE_SPEAKER_ID=true in .env to enable.")
        return

    print("\n📝 Enrolling speakers...")

    # Enroll Alice with 3 samples
    print("\n1. Enrolling Alice...")
    for i in range(3):
        audio = generate_sample_audio(duration_s=3.0)
        recognizer.enroll("alice", "Alice", audio, 16000)
        print(f"   ✓ Sample {i+1}/3 enrolled")

    # Enroll Bob with 3 samples
    print("\n2. Enrolling Bob...")
    for i in range(3):
        audio = generate_sample_audio(duration_s=3.0)
        recognizer.enroll("bob", "Bob", audio, 16000)
        print(f"   ✓ Sample {i+1}/3 enrolled")

    # Enroll Charlie with 3 samples
    print("\n3. Enrolling Charlie...")
    for i in range(3):
        audio = generate_sample_audio(duration_s=3.0)
        recognizer.enroll("charlie", "Charlie", audio, 16000)
        print(f"   ✓ Sample {i+1}/3 enrolled")

    print("\n✅ Enrollment complete!")
    print("   Total speakers: 3 (Alice, Bob, Charlie)")

    recognizer.close()


def example_identification():
    """Example: Identify speakers from audio."""
    print("\n" + "=" * 60)
    print("Example 2: Speaker Identification")
    print("=" * 60)

    # Load configuration
    app_config = AppConfig()

    # Create recognizer
    recognizer = create_voiceprint_recognizer(app_config)

    if not recognizer.enabled:
        print("\n⚠️  Speaker identification is disabled.")
        return

    print("\n🔍 Testing speaker identification...")

    # Test with sample audio
    test_audio = generate_sample_audio(duration_s=2.0)

    # Create utterance
    utterance = Utterance(
        pcm=test_audio,
        sample_rate=16000,
        started_at_s=0.0,
        ended_at_s=len(test_audio) / 16000
    )

    # Identify speaker
    user_id = recognizer.identify(utterance)

    print(f"\n📢 Identified speaker: {user_id}")

    if user_id == "Unknown":
        print("   ℹ️  No match found (threshold not met)")
    else:
        print(f"   ✓ Matched with registered speaker: {user_id}")

    recognizer.close()


def example_list_speakers():
    """Example: List all registered speakers."""
    print("\n" + "=" * 60)
    print("Example 3: List Registered Speakers")
    print("=" * 60)

    from tank_backend.audio.input.repository_sqlite import SQLiteSpeakerRepository

    app_config = AppConfig()
    repo = SQLiteSpeakerRepository(_get_speaker_db_path(app_config))

    speakers = repo.list_speakers()

    if not speakers:
        print("\n📭 No speakers registered yet.")
        print("   Run example_enrollment() first to register speakers.")
    else:
        print(f"\n👥 Registered speakers: {len(speakers)}")
        print("\n" + "-" * 60)
        print(f"{'User ID':<15} {'Name':<20} {'Samples':<10} {'Created':<20}")
        print("-" * 60)

        from datetime import datetime
        for speaker in speakers:
            created = datetime.fromtimestamp(speaker.created_at).strftime("%Y-%m-%d %H:%M")
            print(f"{speaker.user_id:<15} {speaker.name:<20} {len(speaker.embeddings):<10} {created:<20}")

    repo.close()


def example_delete_speaker():
    """Example: Delete a speaker."""
    print("\n" + "=" * 60)
    print("Example 4: Delete Speaker")
    print("=" * 60)

    from tank_backend.audio.input.repository_sqlite import SQLiteSpeakerRepository

    app_config = AppConfig()
    repo = SQLiteSpeakerRepository(_get_speaker_db_path(app_config))

    # Try to delete a speaker
    user_id = "charlie"
    print(f"\n🗑️  Attempting to delete speaker: {user_id}")

    deleted = repo.delete_speaker(user_id)

    if deleted:
        print(f"   ✓ Speaker '{user_id}' deleted successfully")
    else:
        print(f"   ✗ Speaker '{user_id}' not found")

    repo.close()


def example_threshold_tuning():
    """Example: Test different thresholds."""
    print("\n" + "=" * 60)
    print("Example 5: Threshold Tuning")
    print("=" * 60)

    app_config = AppConfig()
    recognizer = create_voiceprint_recognizer(app_config)

    if not recognizer.enabled:
        print("\n⚠️  Speaker identification is disabled.")
        return

    recognizer.close()

    print("\n🎯 Testing different thresholds...")
    print("   (Lower threshold = more lenient, Higher = more strict)")

    test_audio = generate_sample_audio(duration_s=2.0)
    utterance = Utterance(
        pcm=test_audio,
        sample_rate=16000,
        started_at_s=0.0,
        ended_at_s=len(test_audio) / 16000
    )

    thresholds = [0.4, 0.5, 0.6, 0.7, 0.8]

    print("\n" + "-" * 60)
    print(f"{'Threshold':<15} {'Result':<20} {'Note':<25}")
    print("-" * 60)

    app_config = AppConfig()
    for threshold in thresholds:
        recognizer = create_voiceprint_recognizer(app_config)
        recognizer._threshold = threshold

        user_id = recognizer.identify(utterance)

        if user_id == "Unknown":
            note = "No match"
        else:
            note = f"Matched: {user_id}"

        print(f"{threshold:<15.1f} {user_id:<20} {note:<25}")

        recognizer.close()

    print("\n💡 Recommendation:")
    print("   • 0.5-0.6: Good for convenience (may have false positives)")
    print("   • 0.6-0.7: Balanced (recommended for most use cases)")
    print("   • 0.7-0.8: Strict (good for security, may reject valid users)")


def example_export_import():
    """Example: Export and import speaker database."""
    print("\n" + "=" * 60)
    print("Example 6: Export/Import Database")
    print("=" * 60)

    import json
    from tank_backend.audio.input.repository_sqlite import SQLiteSpeakerRepository

    app_config = AppConfig()
    repo = SQLiteSpeakerRepository(_get_speaker_db_path(app_config))

    # Export
    print("\n📤 Exporting speaker database...")
    speakers = repo.list_speakers()

    export_data = []
    for speaker in speakers:
        export_data.append({
            "user_id": speaker.user_id,
            "name": speaker.name,
            "embeddings": [emb.tolist() for emb in speaker.embeddings],
            "created_at": speaker.created_at,
            "updated_at": speaker.updated_at,
        })

    export_file = "speakers_backup.json"
    with open(export_file, "w") as f:
        json.dump(export_data, f, indent=2)

    print(f"   ✓ Exported {len(speakers)} speakers to {export_file}")
    print(f"   File size: {Path(export_file).stat().st_size / 1024:.1f} KB")

    # Import (demonstration only - would overwrite existing data)
    print("\n📥 Import process (demonstration):")
    print(f"   • Load data from {export_file}")
    print(f"   • Parse {len(export_data)} speaker records")
    print("   • Restore embeddings and metadata")
    print("   ℹ️  Actual import not performed to preserve existing data")

    repo.close()


def main():
    """Run all examples."""
    print("\n" + "=" * 60)
    print("🎤 Speaker Identification Examples")
    print("=" * 60)
    print("\nThis script demonstrates the speaker identification system.")
    print("Make sure you have:")
    print("  1. Downloaded the speaker model")
    print("  2. Set ENABLE_SPEAKER_ID=true in .env")
    print("\n" + "=" * 60)

    # Run examples
    try:
        example_enrollment()
        example_list_speakers()
        example_identification()
        example_threshold_tuning()
        example_delete_speaker()
        example_list_speakers()  # Show updated list
        example_export_import()

        print("\n" + "=" * 60)
        print("✅ All examples completed successfully!")
        print("=" * 60)

    except Exception as e:
        print(f"\n❌ Error: {e}")
        print("\nMake sure:")
        print("  1. Speaker model is downloaded")
        print("  2. ENABLE_SPEAKER_ID=true in .env")
        print("  3. Backend dependencies are installed")


if __name__ == "__main__":
    main()
