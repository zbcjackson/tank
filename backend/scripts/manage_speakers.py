#!/usr/bin/env python3
"""Command-line tool for managing speaker database."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np

from tank_backend.audio.input.repository_sqlite import SQLiteSpeakerRepository
from tank_backend.audio.input.voiceprint_factory import create_voiceprint_recognizer
from tank_backend.config.settings import load_config


def list_speakers(db_path: str) -> None:
    """List all registered speakers."""
    repo = SQLiteSpeakerRepository(db_path)
    speakers = repo.list_speakers()

    if not speakers:
        print("No speakers registered.")
        repo.close()
        return

    print(f"\n{'User ID':<20} {'Name':<30} {'Embeddings':<12} {'Created':<20}")
    print("-" * 82)

    for speaker in speakers:
        from datetime import datetime

        created = datetime.fromtimestamp(speaker.created_at).strftime("%Y-%m-%d %H:%M:%S")
        print(
            f"{speaker.user_id:<20} {speaker.name:<30} "
            f"{len(speaker.embeddings):<12} {created:<20}"
        )

    print(f"\nTotal: {len(speakers)} speakers")
    repo.close()


def delete_speaker(db_path: str, user_id: str) -> None:
    """Delete a speaker from the database."""
    repo = SQLiteSpeakerRepository(db_path)

    if repo.delete_speaker(user_id):
        print(f"✓ Deleted speaker: {user_id}")
    else:
        print(f"✗ Speaker not found: {user_id}")

    repo.close()


def enroll_speaker(
    db_path: str, user_id: str, name: str, audio_files: list[str], sample_rate: int = 16000
) -> None:
    """Enroll a speaker from audio files."""
    config = load_config()
    recognizer = create_voiceprint_recognizer(config)

    if not recognizer._enabled:
        print("✗ Speaker identification is disabled in configuration")
        sys.exit(1)

    for audio_file in audio_files:
        audio_path = Path(audio_file)
        if not audio_path.exists():
            print(f"✗ Audio file not found: {audio_file}")
            continue

        # Load audio (assuming .npy format for simplicity)
        if audio_path.suffix == ".npy":
            audio = np.load(audio_path)
        else:
            print(f"✗ Unsupported audio format: {audio_path.suffix}")
            print("  Supported formats: .npy (numpy array)")
            continue

        # Ensure float32
        if audio.dtype != np.float32:
            audio = audio.astype(np.float32)

        # Enroll
        try:
            recognizer.enroll(user_id, name, audio, sample_rate)
            print(f"✓ Enrolled {user_id} from {audio_file}")
        except Exception as e:
            print(f"✗ Failed to enroll from {audio_file}: {e}")

    recognizer.close()


def test_identification(db_path: str, audio_file: str, sample_rate: int = 16000) -> None:
    """Test speaker identification on an audio file."""
    config = load_config()
    recognizer = create_voiceprint_recognizer(config)

    if not recognizer._enabled:
        print("✗ Speaker identification is disabled in configuration")
        sys.exit(1)

    audio_path = Path(audio_file)
    if not audio_path.exists():
        print(f"✗ Audio file not found: {audio_file}")
        sys.exit(1)

    # Load audio
    if audio_path.suffix == ".npy":
        audio = np.load(audio_path)
    else:
        print(f"✗ Unsupported audio format: {audio_path.suffix}")
        sys.exit(1)

    # Ensure float32
    if audio.dtype != np.float32:
        audio = audio.astype(np.float32)

    # Create utterance
    from tank_backend.audio.input.voiceprint import Utterance

    utterance = Utterance(
        pcm=audio,
        sample_rate=sample_rate,
        started_at_s=0.0,
        ended_at_s=len(audio) / sample_rate,
    )

    # Identify
    user_id = recognizer.identify(utterance)
    print(f"\nIdentified speaker: {user_id}")

    recognizer.close()


def export_speakers(db_path: str, output_file: str) -> None:
    """Export speaker database to JSON."""
    import json

    repo = SQLiteSpeakerRepository(db_path)
    speakers = repo.list_speakers()

    data = []
    for speaker in speakers:
        data.append(
            {
                "user_id": speaker.user_id,
                "name": speaker.name,
                "embeddings": [emb.tolist() for emb in speaker.embeddings],
                "created_at": speaker.created_at,
                "updated_at": speaker.updated_at,
            }
        )

    with open(output_file, "w") as f:
        json.dump(data, f, indent=2)

    print(f"✓ Exported {len(speakers)} speakers to {output_file}")
    repo.close()


def import_speakers(db_path: str, input_file: str) -> None:
    """Import speaker database from JSON."""
    import json

    with open(input_file) as f:
        data = json.load(f)

    repo = SQLiteSpeakerRepository(db_path)

    for speaker_data in data:
        user_id = speaker_data["user_id"]
        name = speaker_data["name"]
        embeddings = [np.array(emb, dtype=np.float32) for emb in speaker_data["embeddings"]]

        for embedding in embeddings:
            repo.add_speaker(user_id, name, embedding)

    print(f"✓ Imported {len(data)} speakers from {input_file}")
    repo.close()


def main():
    parser = argparse.ArgumentParser(description="Manage speaker database")
    parser.add_argument(
        "--db",
        default="../data/speakers.db",
        help="Path to speaker database (default: ../data/speakers.db)",
    )

    subparsers = parser.add_subparsers(dest="command", help="Command to execute")

    # List command
    subparsers.add_parser("list", help="List all registered speakers")

    # Delete command
    delete_parser = subparsers.add_parser("delete", help="Delete a speaker")
    delete_parser.add_argument("user_id", help="User ID to delete")

    # Enroll command
    enroll_parser = subparsers.add_parser("enroll", help="Enroll a speaker")
    enroll_parser.add_argument("user_id", help="User ID")
    enroll_parser.add_argument("name", help="Display name")
    enroll_parser.add_argument("audio_files", nargs="+", help="Audio files (.npy format)")
    enroll_parser.add_argument(
        "--sample-rate", type=int, default=16000, help="Sample rate (default: 16000)"
    )

    # Test command
    test_parser = subparsers.add_parser("test", help="Test speaker identification")
    test_parser.add_argument("audio_file", help="Audio file to test (.npy format)")
    test_parser.add_argument(
        "--sample-rate", type=int, default=16000, help="Sample rate (default: 16000)"
    )

    # Export command
    export_parser = subparsers.add_parser("export", help="Export speaker database to JSON")
    export_parser.add_argument("output_file", help="Output JSON file")

    # Import command
    import_parser = subparsers.add_parser("import", help="Import speaker database from JSON")
    import_parser.add_argument("input_file", help="Input JSON file")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    if args.command == "list":
        list_speakers(args.db)
    elif args.command == "delete":
        delete_speaker(args.db, args.user_id)
    elif args.command == "enroll":
        enroll_speaker(args.db, args.user_id, args.name, args.audio_files, args.sample_rate)
    elif args.command == "test":
        test_identification(args.db, args.audio_file, args.sample_rate)
    elif args.command == "export":
        export_speakers(args.db, args.output_file)
    elif args.command == "import":
        import_speakers(args.db, args.input_file)


if __name__ == "__main__":
    main()
