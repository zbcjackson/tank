#!/usr/bin/env python3
"""Generate WAV test fixtures from text using Edge TTS.

Output: 16 kHz mono Int16 PCM WAV files, named after the spoken text.
These files are used by both E2E tests (Playwright fake mic) and backend
integration tests (fed directly into ASR pipeline).

Usage:
    # Generate default test phrases (English + Chinese)
    python scripts/generate_test_audio.py

    # Generate specific phrases
    python scripts/generate_test_audio.py "hello" "what time is it"

    # Custom output directory
    python scripts/generate_test_audio.py -o /tmp/audio "hello"

    # Chinese voice
    python scripts/generate_test_audio.py --lang zh "你好" "现在几点"
"""

from __future__ import annotations

import argparse
import asyncio
import re
import sys
from io import BytesIO
from pathlib import Path

import edge_tts
from pydub import AudioSegment

TARGET_SAMPLE_RATE = 16000
TARGET_CHANNELS = 1

DEFAULT_PHRASES = [
    ("en", "hello"),
    ("en", "what time is it"),
    ("en", "how is the weather today"),
    ("en", "thank you"),
    ("zh", "你好"),
    ("zh", "现在几点"),
]

VOICES = {
    "en": "en-US-JennyNeural",
    "zh": "zh-CN-XiaoxiaoNeural",
}


def sanitize_filename(text: str) -> str:
    """Convert text to a safe filename: lowercase, spaces to underscores."""
    name = text.strip().lower()
    name = re.sub(r"[^\w\s-]", "", name)
    name = re.sub(r"\s+", "_", name)
    return name


async def synthesize(text: str, voice: str) -> AudioSegment:
    """Run Edge TTS and return a pydub AudioSegment."""
    communicate = edge_tts.Communicate(text, voice)
    buf = BytesIO()
    async for chunk in communicate.stream():
        if chunk["type"] == "audio":
            buf.write(chunk["data"])
    buf.seek(0)
    return AudioSegment.from_mp3(buf)


def convert_to_test_format(segment: AudioSegment) -> AudioSegment:
    """Convert to 16 kHz mono 16-bit PCM."""
    return (
        segment
        .set_frame_rate(TARGET_SAMPLE_RATE)
        .set_channels(TARGET_CHANNELS)
        .set_sample_width(2)  # 16-bit
    )


async def generate_one(text: str, lang: str, output_dir: Path) -> Path:
    """Generate a single WAV file. Returns the output path."""
    voice = VOICES[lang]
    filename = sanitize_filename(text) + ".wav"
    out_path = output_dir / filename

    segment = await synthesize(text, voice)
    segment = convert_to_test_format(segment)

    # Silence padding: 1.5s at start (so browser calibration only sees silence),
    # 2s at end (so backend ASR detects endpoint before Chrome loops back to speech).
    pre_silence = AudioSegment.silent(duration=1500, frame_rate=TARGET_SAMPLE_RATE)
    post_silence = AudioSegment.silent(duration=2000, frame_rate=TARGET_SAMPLE_RATE)
    segment = pre_silence + segment + post_silence

    segment.export(str(out_path), format="wav")
    duration_s = len(segment) / 1000
    print(f"  ✓ {out_path.name}  ({duration_s:.1f}s, {lang})")
    return out_path


async def main_async(phrases: list[tuple[str, str]], output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    print(f"Generating {len(phrases)} test audio files → {output_dir}/\n")
    for lang, text in phrases:
        await generate_one(text, lang, output_dir)
    print(f"\nDone. Files ready in {output_dir}/")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate WAV test fixtures from text using Edge TTS.",
    )
    parser.add_argument(
        "texts",
        nargs="*",
        help="Texts to synthesize. If omitted, generates default phrases.",
    )
    parser.add_argument(
        "-o", "--output-dir",
        type=Path,
        default=Path(__file__).resolve().parent.parent / "test" / "fixtures" / "audio",
        help="Output directory (default: test/fixtures/audio/)",
    )
    parser.add_argument(
        "--lang",
        choices=["en", "zh"],
        default="en",
        help="Language/voice for custom texts (default: en)",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    if args.texts:
        phrases = [(args.lang, t) for t in args.texts]
    else:
        phrases = DEFAULT_PHRASES

    try:
        asyncio.run(main_async(phrases, args.output_dir))
    except KeyboardInterrupt:
        print("\nAborted.")
        sys.exit(1)


if __name__ == "__main__":
    main()
