#!/usr/bin/env python3
"""Benchmark first-audio latency of a running Tank backend.

Connects to the backend WebSocket, sends a text input (skipping ASR to
isolate the LLM→TTS→playback path), and measures per turn:

  - ``ready_ms``        connect → ready signal (connection overhead)
  - ``first_text_ms``   input → first streamed LLM text frame
  - ``first_audio_ms``  input → first binary TTS audio frame
  - ``last_audio_ms``   input → last binary frame (turn fully spoken)
  - ``turn_end_ms``     input → processing_ended signal (brain finished)

After ``processing_ended`` the collector keeps draining for a quiet
window (``--drain``) so trailing TTS chunks are still counted toward
``last_audio_ms``.

Requires a running backend; not part of the pytest suite.

Usage:
    uv run python scripts/benchmark_pipeline.py [--rounds 5] [--out result.json]
"""

from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import sys
import uuid
from typing import Any

import websockets

DEFAULT_PROMPT = (
    "请用中文详细介绍丝绸之路的历史、主要路线和文化遗产，大约写二十句话，不要省略。"
)


async def run_round(
    base_url: str,
    prompt: str,
    stall_timeout_s: float,
    drain_s: float,
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
        await ws.send(json.dumps({"type": "input", "content": prompt}))

        first_text_ms: float | None = None
        first_audio_ms: float | None = None
        last_audio_ms: float | None = None
        turn_end_ms: float | None = None
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
                    and data.get("content") == "processing_ended"
                ):
                    turn_end_ms = (now - t0) * 1000

    return {
        "session": session,
        "ready_ms": round(ready_ms, 1),
        "first_text_ms": _round(first_text_ms),
        "first_audio_ms": _round(first_audio_ms),
        "last_audio_ms": _round(last_audio_ms),
        "turn_end_ms": _round(turn_end_ms),
        "audio_chunks": audio_chunks,
        "audio_bytes": audio_bytes,
        "text_chars": text_chars,
    }


def _round(value: float | None) -> float | None:
    return round(value, 1) if value is not None else None


def summarize(rounds: list[dict[str, Any]]) -> dict[str, Any]:
    """Aggregate per-metric min/mean/p50/p95/max across rounds."""
    summary: dict[str, Any] = {}
    for key in ("ready_ms", "first_text_ms", "first_audio_ms", "last_audio_ms",
                "turn_end_ms"):
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


async def main() -> int:
    parser = argparse.ArgumentParser(
        description="Benchmark first-audio latency over the Tank WebSocket API.",
    )
    parser.add_argument("-u", "--url", default="ws://localhost:8000",
                        help="Backend base WS URL (default: ws://localhost:8000)")
    parser.add_argument("-n", "--rounds", type=int, default=5,
                        help="Measured rounds (default: 5)")
    parser.add_argument("--warmup", type=int, default=1,
                        help="Warmup turns excluded from stats (default: 1)")
    parser.add_argument("-p", "--prompt", default=DEFAULT_PROMPT,
                        help="Input prompt (should elicit a long answer)")
    parser.add_argument("--timeout", type=float, default=180.0,
                        help="Per-turn stall timeout in seconds (default: 180)")
    parser.add_argument("--drain", type=float, default=3.0,
                        help="Quiet window after processing_ended in seconds "
                             "(default: 3)")
    parser.add_argument("--out", default=None,
                        help="Also write the JSON result to this file")
    args = parser.parse_args()

    for i in range(args.warmup):
        print(f"[warmup {i + 1}/{args.warmup}] ...", file=sys.stderr)
        await run_round(args.url, args.prompt, args.timeout, args.drain)

    rounds: list[dict[str, Any]] = []
    for i in range(args.rounds):
        print(f"[round {i + 1}/{args.rounds}] ...", file=sys.stderr)
        result = await run_round(args.url, args.prompt, args.timeout, args.drain)
        rounds.append(result)
        print(
            f"  first_text={result['first_text_ms']}ms "
            f"first_audio={result['first_audio_ms']}ms "
            f"turn_end={result['turn_end_ms']}ms "
            f"({result['audio_chunks']} chunks, {result['text_chars']} chars)",
            file=sys.stderr,
        )

    report = {
        "prompt": args.prompt,
        "url": args.url,
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
