"""Analyze captures dumped by the browser debug hook.

Expected inputs (dropped in ~/Downloads by __tankAudioSave()):
  - tank-in-<inputRate>.pcm            Int16 LE mono at <inputRate> Hz
  - tank-resampled-<ctxRate>.f32       Float32 LE mono at <ctxRate> Hz
  - tank-worklet-<ctxRate>.f32         Float32 LE mono at <ctxRate> Hz
  - tank-audio-metadata.json           rates + chunk sizes

Usage:
    uv run python scripts/analyze_browser_captures.py ~/Downloads

For each of the three captures this script reports:
  - peak, RMS, DC offset, clipping count
  - max sample-to-sample jump (unit: normalized [-1,1], which is how a 1 kHz
    sine at 48 kHz jumps ~0.13 between samples)
  - high-frequency energy ratio (hints at broadband noise or clicks)
  - detects long runs of zeros (would indicate underrun in the worklet)
  - generates .wav versions you can ffplay

The first capture that shows anomalous stats is where the noise enters.
"""

from __future__ import annotations

import argparse
import json
import struct
import sys
import wave
from pathlib import Path


def load_int16_pcm(path: Path) -> list[float]:
    data = path.read_bytes()
    if len(data) % 2 != 0:
        data = data[:-1]
    n = len(data) // 2
    if n == 0:
        return []
    samples = struct.unpack(f"<{n}h", data)
    return [s / 32768.0 for s in samples]


def load_float32(path: Path) -> list[float]:
    data = path.read_bytes()
    n = len(data) // 4
    if n == 0:
        return []
    return list(struct.unpack(f"<{n}f", data))


def stats(name: str, samples: list[float], rate: int) -> None:
    n = len(samples)
    if n == 0:
        print(f"  {name}: empty")
        return

    peak = max(abs(s) for s in samples)
    rms = (sum(s * s for s in samples) / n) ** 0.5
    dc = sum(samples) / n
    clips = sum(1 for s in samples if abs(s) >= 0.999)

    # Sample-to-sample jumps. A 1 kHz sine at 48 kHz has max jump ~0.13.
    # Voice typically jumps <0.3 between adjacent samples at 24 kHz.
    jumps = [abs(samples[i] - samples[i - 1]) for i in range(1, n)]
    max_jump = max(jumps) if jumps else 0.0
    big_jumps = sum(1 for j in jumps if j > 0.3)
    huge_jumps = sum(1 for j in jumps if j > 0.6)

    # Long runs of zeros (underrun detection).
    run_len = 0
    max_zero_run = 0
    zero_run_count = 0  # runs longer than 128 samples
    for s in samples:
        if abs(s) < 1e-6:
            run_len += 1
            if run_len > max_zero_run:
                max_zero_run = run_len
        else:
            if run_len >= 128:
                zero_run_count += 1
            run_len = 0
    if run_len >= 128:
        zero_run_count += 1

    # Crude HF energy: first-difference RMS / signal RMS.
    # For clean voice with smooth waveforms this ratio is well under 1.0.
    # Broadband noise or clicks push it higher.
    hp = [samples[i] - samples[i - 1] for i in range(1, n)]
    hp_rms = (sum(h * h for h in hp) / len(hp)) ** 0.5 if hp else 0.0
    hf_ratio = hp_rms / rms if rms > 0 else 0.0

    duration = n / rate
    print(f"  {name}:")
    print(f"    samples    : {n} ({duration:.2f}s @ {rate}Hz)")
    print(f"    peak       : {peak:.4f}    (clips>=0.999: {clips})")
    print(f"    rms        : {rms:.4f}")
    print(f"    dc offset  : {dc:+.6f}")
    print(f"    max jump   : {max_jump:.4f}    (>0.3: {big_jumps}, >0.6: {huge_jumps})")
    print(
        f"    zero runs  : max {max_zero_run} samples "
        f"({max_zero_run / rate * 1000:.1f}ms), runs>=128: {zero_run_count}"
    )
    print(f"    hf/rms     : {hf_ratio:.3f}    (voice is typically < 0.8)")


def write_wav(path: Path, samples: list[float], rate: int) -> None:
    if not samples:
        return
    data = b"".join(
        struct.pack("<h", max(-32768, min(32767, int(s * 32767))))
        for s in samples
    )
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(data)
    print(f"    wrote {path}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "directory",
        type=Path,
        help="Directory containing the captures (e.g. ~/Downloads)",
    )
    args = parser.parse_args()

    d: Path = args.directory.expanduser()
    meta_path = d / "tank-audio-metadata.json"
    if not meta_path.exists():
        print(
            f"No {meta_path} found - did you call __tankAudioSave() in the browser?",
            file=sys.stderr,
        )
        sys.exit(1)

    meta = json.loads(meta_path.read_text())
    input_rate: int = meta["inputRate"]
    ctx_rate: int = meta["ctxRate"]

    print(f"inputRate   = {input_rate} Hz")
    print(f"ctxRate     = {ctx_rate} Hz")
    print(f"chunkCount  = {meta['chunkCount']}")
    print(f"inputDur    = {meta['inputDurationSec']:.2f}s")
    print(f"outputDur   = {meta.get('workletOutDurationSec')}")
    print()

    sizes = meta.get("chunkSizes", [])
    if sizes:
        print(
            f"chunk sizes: min={min(sizes)} max={max(sizes)} "
            f"odd={sum(1 for s in sizes if s % 2)}"
        )
        print()

    in_path = d / f"tank-in-{input_rate}.pcm"
    rs_path = d / f"tank-resampled-{ctx_rate}.f32"
    wo_path = d / f"tank-worklet-{ctx_rate}.f32"

    for p in (in_path, rs_path, wo_path):
        if not p.exists():
            print(f"Missing: {p}", file=sys.stderr)
            sys.exit(1)

    print("(A) pre-resample input (backend PCM -> playChunk input):")
    a = load_int16_pcm(in_path)
    stats("input", a, input_rate)
    write_wav(d / "tank-in.wav", a, input_rate)
    print()

    print("(B) post-resample (LinearResampler output, posted to worklet):")
    b = load_float32(rs_path)
    stats("resampled", b, ctx_rate)
    write_wav(d / "tank-resampled.wav", b, ctx_rate)
    print()

    print("(C) worklet output (what leaves the audio graph per render quantum):")
    c = load_float32(wo_path)
    stats("worklet", c, ctx_rate)
    write_wav(d / "tank-worklet.wav", c, ctx_rate)
    print()

    print("Listen in order (any that sounds bad is where noise first enters):")
    print(f"  ffplay -autoexit -nodisp {d / 'tank-in.wav'}")
    print(f"  ffplay -autoexit -nodisp {d / 'tank-resampled.wav'}")
    print(f"  ffplay -autoexit -nodisp {d / 'tank-worklet.wav'}")


if __name__ == "__main__":
    main()
