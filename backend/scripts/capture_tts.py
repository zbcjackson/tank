"""Debug: capture TTS output at multiple points in the pipeline.

Run from backend/:
    uv run python -m scripts.capture_tts "Hello, this is a test."

Produces files in /tmp/tank-audio-debug/:
  - raw-edge.mp3    : exactly what edge-tts streams to us
  - ffmpeg.pcm/.wav : s16le PCM after our ffmpeg decode (same path as prod)
  - plugin.pcm/.wav : PCM yielded by EdgeTTSEngine.generate_stream
                      (what the pipeline actually consumes)

Listen to each in order. The first one that sounds bad is where noise enters.
"""

from __future__ import annotations

import argparse
import asyncio
import struct
import sys
import wave
from pathlib import Path

import edge_tts

from tts_edge import create_engine


OUT_DIR = Path("/tmp/tank-audio-debug")
SAMPLE_RATE = 24000
CHANNELS = 1


async def dump_raw_mp3(text: str, voice: str) -> Path:
    """Save exactly what edge-tts streams, before our ffmpeg decode."""
    path = OUT_DIR / "raw-edge.mp3"
    communicate = edge_tts.Communicate(text, voice)
    with path.open("wb") as f:
        async for chunk in communicate.stream():
            if chunk.get("type") == "audio":
                data = chunk.get("data")
                if data:
                    f.write(data)
    print(f"  wrote {path} ({path.stat().st_size} bytes)")
    return path


async def dump_ffmpeg_output(mp3_path: Path) -> Path:
    """Decode the MP3 with the same ffmpeg args engine.py uses."""
    pcm_path = OUT_DIR / "ffmpeg.pcm"
    proc = await asyncio.create_subprocess_exec(
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-f",
        "mp3",
        "-i",
        str(mp3_path),
        "-f",
        "s16le",
        "-ar",
        str(SAMPLE_RATE),
        "-ac",
        str(CHANNELS),
        str(pcm_path),
        "-y",
    )
    await proc.wait()
    print(f"  wrote {pcm_path} ({pcm_path.stat().st_size} bytes)")
    wrap_wav(pcm_path, OUT_DIR / "ffmpeg.wav")
    return pcm_path


async def dump_plugin_output(text: str) -> Path:
    """Drive EdgeTTSEngine.generate_stream and concatenate every AudioChunk."""
    pcm_path = OUT_DIR / "plugin.pcm"
    engine = create_engine({
        "voice_en": "en-US-JennyNeural",
        "voice_zh": "zh-CN-XiaoxiaoNeural",
    })

    chunk_sizes: list[int] = []
    with pcm_path.open("wb") as f:
        async for chunk in engine.generate_stream(text, language="en"):
            f.write(chunk.data)
            chunk_sizes.append(len(chunk.data))

    print(f"  wrote {pcm_path} ({pcm_path.stat().st_size} bytes, {len(chunk_sizes)} chunks)")
    if chunk_sizes:
        odd = [s for s in chunk_sizes if s % 2 != 0]
        print(f"  chunk sizes: min={min(chunk_sizes)} max={max(chunk_sizes)} odd_count={len(odd)}")
    wrap_wav(pcm_path, OUT_DIR / "plugin.wav")
    return pcm_path


def wrap_wav(pcm_path: Path, wav_path: Path) -> None:
    """Wrap a raw s16le mono 24 kHz PCM file as a WAV for easy playback."""
    data = pcm_path.read_bytes()
    if len(data) % 2 != 0:
        print(f"  WARN: {pcm_path.name} has odd length; trimming last byte")
        data = data[:-1]
    with wave.open(str(wav_path), "wb") as w:
        w.setnchannels(CHANNELS)
        w.setsampwidth(2)
        w.setframerate(SAMPLE_RATE)
        w.writeframes(data)
    print(f"  wrote {wav_path}")


def check_pcm_stats(pcm_path: Path) -> None:
    """Sanity-check the PCM: clipping, DC offset, sample-to-sample jumps."""
    data = pcm_path.read_bytes()
    if len(data) % 2 != 0:
        data = data[:-1]
    n_samples = len(data) // 2
    if n_samples == 0:
        print("  (empty)")
        return

    samples = struct.unpack(f"<{n_samples}h", data)
    clips = sum(1 for s in samples if s >= 32767 or s <= -32768)
    mean = sum(samples) / n_samples
    peak = max(abs(s) for s in samples)

    jumps: list[tuple[int, int]] = []
    big_jump_threshold = 20000
    for i in range(1, n_samples):
        diff = samples[i] - samples[i - 1]
        if abs(diff) > big_jump_threshold:
            jumps.append((i, diff))

    duration_s = n_samples / SAMPLE_RATE
    print(
        f"  stats: {n_samples} samples ({duration_s:.2f}s), "
        f"peak={peak} (clips={clips}), dc_offset={mean:+.1f}, "
        f"big_jumps(>{big_jump_threshold})={len(jumps)}"
    )
    if jumps[:5]:
        print(f"  first big jumps (sample_idx, delta): {jumps[:5]}")


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("text", nargs="?", default=(
        "Hello, this is a test of the Tank voice assistant audio pipeline."
    ))
    parser.add_argument("--voice", default="en-US-JennyNeural")
    args = parser.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    print(f"Text: {args.text!r}")
    print(f"Voice: {args.voice}")
    print(f"Output directory: {OUT_DIR}")
    print()

    print("1. Raw edge-tts MP3 stream:")
    mp3 = await dump_raw_mp3(args.text, args.voice)

    print()
    print("2. ffmpeg decode -> s16le PCM:")
    ffmpeg_pcm = await dump_ffmpeg_output(mp3)
    check_pcm_stats(ffmpeg_pcm)

    print()
    print("3. EdgeTTSEngine.generate_stream (what pipeline consumes):")
    plugin_pcm = await dump_plugin_output(args.text)
    check_pcm_stats(plugin_pcm)

    print()
    print("Compare plugin.pcm vs ffmpeg.pcm:")
    a = ffmpeg_pcm.read_bytes()
    b = plugin_pcm.read_bytes()
    if a == b:
        print("  IDENTICAL - plugin output matches direct ffmpeg output byte-for-byte.")
    else:
        print(f"  DIFFER (ffmpeg.pcm={len(a)}B, plugin.pcm={len(b)}B)")

    print()
    print("Listen to (in order):")
    print(f"  ffplay -autoexit -nodisp {OUT_DIR / 'raw-edge.mp3'}")
    print(f"  ffplay -autoexit -nodisp {OUT_DIR / 'ffmpeg.wav'}")
    print(f"  ffplay -autoexit -nodisp {OUT_DIR / 'plugin.wav'}")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        sys.exit(1)
