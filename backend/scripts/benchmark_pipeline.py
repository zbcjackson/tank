#!/usr/bin/env python3
"""Benchmark first-audio latency of a running Tank backend.

Connects to the backend WebSocket and drives a turn, measuring per round:

  - ``ready_ms``        connect → ready signal (connection overhead)
  - ``first_text_ms``   input → first streamed LLM text frame
  - ``first_audio_ms``  input → first binary TTS audio frame
  - ``last_audio_ms``   input → last binary frame (turn fully spoken)
  - ``turn_end_ms``     input → processing_ended signal (brain finished)

Two input modes:

  - ``text`` (default): sends a JSON text input, skipping VAD/ASR to
    isolate the LLM→TTS→playback path.
  - ``voice``: streams a WAV fixture (Int16 PCM, 16 kHz) as mic audio so
    the turn crosses VAD → ASR → brain → TTS. After the utterance, a
    trailing silence window lets the backend endpoint the turn; the round
    additionally reports ``voice_end_ms`` (speech finished streaming) and
    ``endpoint_ms`` (last speech chunk → processing_started, i.e. the
    turn-taking latency).

``--concurrency N`` splits the measured rounds across N simultaneous
sessions (synthetic stress, s2s's synthetic-conversation analog).

After ``processing_ended`` the collector keeps draining for a quiet
window (``--drain``) so trailing TTS chunks are still counted toward
``last_audio_ms``.

Requires a running backend; not part of the pytest suite.

Usage:
    uv run python scripts/benchmark_pipeline.py [--mode voice] [--rounds 5]
        [--concurrency 4] [--out result.json]
"""

from __future__ import annotations

import argparse
import asyncio
import json
import math
import statistics
import sys
import uuid
from pathlib import Path
from typing import Any

import websockets

DEFAULT_PROMPT = (
    "请用中文详细介绍丝绸之路的历史、主要路线和文化遗产，大约写二十句话，不要省略。"
)

# Default voice fixture: a real recorded utterance (also used by the E2E
# voice-input scenarios), 44-byte WAV header + Int16 mono PCM at 16 kHz.
_DEFAULT_AUDIO = Path(__file__).resolve().parents[2] / "test/fixtures/audio/你好.wav"

SAMPLE_RATE = 16000
CHUNK_MS = 100  # mic chunks are streamed at real-time pace
# Trailing silence after the utterance — must exceed min_silence_ms +
# Smart Turn adjudication + the speculative reopen window.
ENDPOINT_SILENCE_MS = 2500


def load_wav_pcm(path: Path) -> bytes:
    """Read a WAV file as raw Int16 PCM (skips the 44-byte canonical header)."""
    data = path.read_bytes()
    if len(data) <= 44:
        raise SystemExit(f"Audio file too small: {path}")
    return data[44:]


async def _stream_utterance(
    ws: Any, pcm: bytes, t0: float, endpoint_silence_ms: int,
) -> float:
    """Stream PCM as mic audio at real-time pace, then trailing silence.

    Returns ``voice_end_ms`` — the offset from ``t0`` at which the last
    speech chunk was sent (endpoint latency is measured from here).
    """
    loop = asyncio.get_running_loop()
    chunk_bytes = int(SAMPLE_RATE * CHUNK_MS / 1000) * 2  # Int16 → bytes
    voice_end_ms = 0.0
    for off in range(0, len(pcm), chunk_bytes):
        await ws.send(pcm[off:off + chunk_bytes])
        voice_end_ms = (loop.time() - t0) * 1000
        await asyncio.sleep(CHUNK_MS / 1000)
    silence = b"\x00" * chunk_bytes
    for _ in range(math.ceil(endpoint_silence_ms / CHUNK_MS)):
        await ws.send(silence)
        await asyncio.sleep(CHUNK_MS / 1000)
    return voice_end_ms


async def _collect(
    ws: Any, t0: float, stall_timeout_s: float, drain_s: float,
) -> dict[str, Any]:
    """Receive and timestamp server frames until the turn goes quiet.

    Runs concurrently with audio streaming so ``processing_started`` is
    timestamped on arrival: with the previous recv-after-streaming order,
    an endpoint firing mid-stream was only read (and dated) once the
    injected silence window finished streaming, flooring ``endpoint_ms``
    at that window. After ``processing_ended`` it keeps draining for
    ``drain_s`` so trailing TTS chunks still count toward
    ``last_audio_ms``.
    """
    first_text_ms: float | None = None
    first_audio_ms: float | None = None
    last_audio_ms: float | None = None
    turn_end_ms: float | None = None
    processing_started_ms: float | None = None
    audio_chunks = 0
    audio_bytes = 0
    text_chars = 0

    while True:
        timeout = drain_s if turn_end_ms is not None else stall_timeout_s
        try:
            raw = await asyncio.wait_for(ws.recv(), timeout=timeout)
        except asyncio.TimeoutError:
            break  # stall (before end) or quiet drain window (after end)
        now = asyncio.get_running_loop().time()
        if isinstance(raw, bytes):
            if first_audio_ms is None:
                first_audio_ms = (now - t0) * 1000
            last_audio_ms = (now - t0) * 1000
            audio_chunks += 1
            audio_bytes += len(raw)
        else:
            data = json.loads(raw)
            msg_type = data.get("type")
            if msg_type == "text":
                if first_text_ms is None:
                    first_text_ms = (now - t0) * 1000
                text_chars += len(data.get("content", ""))
            elif (
                msg_type == "signal"
                and data.get("content") == "processing_started"
            ):
                # First occurrence only: a speculative reopen re-emits the
                # signal when the brain restarts, which would overstate the
                # turn-taking latency this metric exists to capture.
                if processing_started_ms is None:
                    processing_started_ms = (now - t0) * 1000
            elif (
                msg_type == "signal"
                and data.get("content") == "processing_ended"
            ):
                turn_end_ms = (now - t0) * 1000

    return {
        "first_text_ms": first_text_ms,
        "first_audio_ms": first_audio_ms,
        "last_audio_ms": last_audio_ms,
        "turn_end_ms": turn_end_ms,
        "processing_started_ms": processing_started_ms,
        "audio_chunks": audio_chunks,
        "audio_bytes": audio_bytes,
        "text_chars": text_chars,
    }


async def run_round(
    base_url: str,
    prompt: str,
    stall_timeout_s: float,
    drain_s: float,
    *,
    audio_pcm: bytes | None = None,
    endpoint_silence_ms: int = ENDPOINT_SILENCE_MS,
) -> dict[str, Any]:
    """Run one measured turn. Returns the metric dict for this round."""
    session = f"bench-{uuid.uuid4().hex[:8]}"
    t_connect = asyncio.get_running_loop().time()

    async with websockets.connect(f"{base_url}/ws/{session}") as ws:
        # Wait for the ready signal before starting the turn.
        while True:
            raw = await asyncio.wait_for(ws.recv(), timeout=30)
            if isinstance(raw, str):
                data = json.loads(raw)
                if data.get("type") == "signal" and data.get("content") == "ready":
                    break
        ready_ms = (asyncio.get_running_loop().time() - t_connect) * 1000

        t0 = asyncio.get_running_loop().time()
        collect_task = asyncio.create_task(_collect(ws, t0, stall_timeout_s, drain_s))
        voice_end_ms: float | None = None
        if audio_pcm is not None:
            voice_end_ms = await _stream_utterance(
                ws, audio_pcm, t0, endpoint_silence_ms,
            )
        else:
            await ws.send(json.dumps({"type": "input", "content": prompt}))

        collected = await collect_task

    endpoint_ms = (
        round(collected["processing_started_ms"] - voice_end_ms, 1)
        if collected["processing_started_ms"] is not None and voice_end_ms is not None
        else None
    )
    return {
        "session": session,
        "ready_ms": round(ready_ms, 1),
        "first_text_ms": _round(collected["first_text_ms"]),
        "first_audio_ms": _round(collected["first_audio_ms"]),
        "last_audio_ms": _round(collected["last_audio_ms"]),
        "turn_end_ms": _round(collected["turn_end_ms"]),
        "voice_end_ms": _round(voice_end_ms),
        "endpoint_ms": endpoint_ms,
        "audio_chunks": collected["audio_chunks"],
        "audio_bytes": collected["audio_bytes"],
        "text_chars": collected["text_chars"],
    }


def _round(value: float | None) -> float | None:
    return round(value, 1) if value is not None else None


def summarize(rounds: list[dict[str, Any]]) -> dict[str, Any]:
    """Aggregate per-metric min/mean/p50/p95/max across rounds."""
    summary: dict[str, Any] = {}
    for key in ("ready_ms", "first_text_ms", "first_audio_ms", "last_audio_ms",
                "turn_end_ms", "endpoint_ms"):
        values = sorted(
            r[key] for r in rounds if r.get(key) is not None
        )
        if not values:
            summary[key] = None
            continue
        summary[key] = {
            "min": values[0],
            "mean": round(statistics.mean(values), 1),
            "p50": _percentile(values, 50),
            "p95": _percentile(values, 95),
            "max": values[-1],
        }
    summary["rounds_measured"] = len(rounds)
    return summary


def _percentile(sorted_values: list[float], pct: float) -> float:
    """Nearest-rank percentile on a pre-sorted list."""
    rank = max(1, round(pct / 100 * len(sorted_values)))
    return round(sorted_values[rank - 1], 1)


async def _run_worker(
    worker_id: int,
    count: int,
    args: argparse.Namespace,
    audio_pcm: bytes | None,
    rounds: list[dict[str, Any]],
) -> None:
    """Run this worker's share of measured rounds."""
    for i in range(count):
        print(
            f"[worker {worker_id} round {i + 1}/{count}] ...", file=sys.stderr,
        )
        result = await run_round(
            args.url,
            args.prompt,
            args.timeout,
            args.drain,
            audio_pcm=audio_pcm,
            endpoint_silence_ms=args.endpoint_silence_ms,
        )
        result["worker"] = worker_id
        rounds.append(result)
        endpoint = (
            f" endpoint={result['endpoint_ms']}ms"
            if result["endpoint_ms"] is not None else ""
        )
        print(
            f"  first_text={result['first_text_ms']}ms "
            f"first_audio={result['first_audio_ms']}ms "
            f"turn_end={result['turn_end_ms']}ms{endpoint} "
            f"({result['audio_chunks']} chunks, {result['text_chars']} chars)",
            file=sys.stderr,
        )


async def main() -> int:
    parser = argparse.ArgumentParser(
        description="Benchmark first-audio latency over the Tank WebSocket API.",
    )
    parser.add_argument("-u", "--url", default="ws://localhost:8000",
                        help="Backend base WS URL (default: ws://localhost:8000)")
    parser.add_argument("-m", "--mode", choices=("text", "voice"), default="text",
                        help="text: JSON input (skips VAD/ASR); voice: stream a "
                             "WAV fixture through VAD/ASR (default: text)")
    parser.add_argument("--audio", type=Path, default=_DEFAULT_AUDIO,
                        help=f"WAV fixture for voice mode "
                             f"(default: {_DEFAULT_AUDIO})")
    parser.add_argument("--endpoint-silence-ms", type=int,
                        default=ENDPOINT_SILENCE_MS,
                        help="Trailing silence after the utterance in voice "
                             f"mode (default: {ENDPOINT_SILENCE_MS})")
    parser.add_argument("-n", "--rounds", type=int, default=5,
                        help="Measured rounds (default: 5)")
    parser.add_argument("-c", "--concurrency", type=int, default=1,
                        help="Simultaneous sessions sharing the rounds "
                             "(default: 1)")
    parser.add_argument("--warmup", type=int, default=1,
                        help="Warmup turns excluded from stats (default: 1)")
    parser.add_argument("-p", "--prompt", default=DEFAULT_PROMPT,
                        help="Input prompt for text mode (long answer elicits "
                             "better latency signal)")
    parser.add_argument("--timeout", type=float, default=180.0,
                        help="Per-turn stall timeout in seconds (default: 180)")
    parser.add_argument("--drain", type=float, default=3.0,
                        help="Quiet window after processing_ended in seconds "
                             "(default: 3)")
    parser.add_argument("--out", default=None,
                        help="Also write the JSON result to this file")
    args = parser.parse_args()

    audio_pcm: bytes | None = None
    if args.mode == "voice":
        audio_pcm = load_wav_pcm(args.audio)
        print(
            f"voice mode: {args.audio} "
            f"({len(audio_pcm) / 2 / SAMPLE_RATE:.2f}s utterance)",
            file=sys.stderr,
        )

    for i in range(args.warmup):
        print(f"[warmup {i + 1}/{args.warmup}] ...", file=sys.stderr)
        await run_round(
            args.url, args.prompt, args.timeout, args.drain,
            audio_pcm=audio_pcm, endpoint_silence_ms=args.endpoint_silence_ms,
        )

    concurrency = max(1, args.concurrency)
    rounds: list[dict[str, Any]] = []
    per_worker = math.ceil(args.rounds / concurrency)
    if concurrency == 1:
        await _run_worker(0, args.rounds, args, audio_pcm, rounds)
    else:
        print(
            f"stress: {concurrency} concurrent sessions × "
            f"{per_worker} rounds each",
            file=sys.stderr,
        )
        await asyncio.gather(*(
            _run_worker(w, per_worker, args, audio_pcm, rounds)
            for w in range(concurrency)
        ))

    report = {
        "prompt": args.prompt,
        "url": args.url,
        "mode": args.mode,
        "concurrency": concurrency,
        "rounds": rounds,
        "summary": summarize(rounds),
    }
    output = json.dumps(report, ensure_ascii=False, indent=2)
    print(output)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(output + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
