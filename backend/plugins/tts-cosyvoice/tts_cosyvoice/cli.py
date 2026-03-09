"""CLI entry point: speak text via CosyVoice in one command."""

from __future__ import annotations

import argparse
import asyncio
import sys

import numpy as np
import sounddevice as sd

from .engine import CosyVoiceTTSEngine, COSYVOICE_SAMPLE_RATE


async def _speak(engine: CosyVoiceTTSEngine, text: str, language: str, voice: str | None = None) -> None:
    pcm = bytearray()
    sample_rate = COSYVOICE_SAMPLE_RATE
    async for chunk in engine.generate_stream(text, language=language, voice=voice):
        pcm.extend(chunk.data)
        sample_rate = chunk.sample_rate

    if not pcm:
        print("No audio generated.", file=sys.stderr)
        return

    samples = np.frombuffer(bytes(pcm), dtype=np.int16).astype(np.float32) / 32768.0
    sd.play(samples, samplerate=sample_rate, blocking=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Speak text via CosyVoice TTS")
    parser.add_argument("text", help="Text to speak")
    parser.add_argument("--url", default="http://localhost:50000", help="CosyVoice server URL")
    parser.add_argument("--lang", default="auto", help="Language: zh, en, auto (default: auto)")
    parser.add_argument("--spk", default=None, help="Speaker ID (overrides language default)")
    parser.add_argument("--rate", type=int, default=COSYVOICE_SAMPLE_RATE, help="Sample rate")
    args = parser.parse_args()

    engine = CosyVoiceTTSEngine({
        "base_url": args.url,
        "sample_rate": args.rate,
    })

    language = args.lang
    if language == "auto":
        # Simple heuristic: if any CJK character, assume Chinese
        language = "zh" if any("\u4e00" <= c <= "\u9fff" for c in args.text) else "en"

    asyncio.run(_speak(engine, args.text, language, voice=args.spk), debug=False)


if __name__ == "__main__":
    main()
