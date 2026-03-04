#!/usr/bin/env python3
"""Record audio and save as .npy for testing speaker identification."""

import argparse
import sys

import numpy as np
import sounddevice as sd


def record_audio(duration: float = 5.0, sample_rate: int = 16000) -> np.ndarray:
    """Record audio from microphone."""
    print(f"Recording {duration} seconds of audio...")
    print("Speak now!")

    audio = sd.rec(
        int(duration * sample_rate),
        samplerate=sample_rate,
        channels=1,
        dtype=np.float32,
    )
    sd.wait()

    print("Recording complete!")
    return audio.flatten()


def main():
    parser = argparse.ArgumentParser(description="Record audio for speaker identification")
    parser.add_argument(
        "output_file",
        help="Output file path (.npy format)",
    )
    parser.add_argument(
        "--duration",
        type=float,
        default=5.0,
        help="Recording duration in seconds (default: 5.0)",
    )
    parser.add_argument(
        "--sample-rate",
        type=int,
        default=16000,
        help="Sample rate in Hz (default: 16000)",
    )

    args = parser.parse_args()

    try:
        audio = record_audio(args.duration, args.sample_rate)
        np.save(args.output_file, audio)
        print(f"✓ Saved audio to {args.output_file}")
        print(f"  Duration: {len(audio) / args.sample_rate:.2f}s")
        print(f"  Sample rate: {args.sample_rate} Hz")
        print(f"  Samples: {len(audio)}")
    except Exception as e:
        print(f"✗ Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
