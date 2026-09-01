#!/usr/bin/env python3
"""Capture a human-recorded Smart Turn A/B fixture.

Complements the TTS fixtures in ``scripts/smart_turn_ab/`` with real
recordings — TTS cannot reproduce genuine hesitation prosody (held pitch,
trailing fillers), which is exactly the signal the classifier might use to
judge an utterance incomplete. Human files go under a separate language
tag (``zh-hu``/``en-hu``) so ``eval_smart_turn.py`` reports them as their
own group next to the TTS baseline.

Two input paths:

- ``--from-file`` (primary): any recording a phone/laptop produced
  (m4a/mp3/wav — anything ffmpeg reads) is resampled to 16 kHz mono and
  cut with the same treatment as the TTS set: at the first internal pause
  >= 250 ms plus 250 ms of tail (incomplete), or at last speech + 250 ms
  when the clip has no internal pause (complete).
- ``--mic SECONDS``: record from the default input device. Requires the
  PortAudio library (``libportaudio2``); unavailable hosts should record
  externally and use ``--from-file``.

Recording guide (incomplete items): speak the FULL sentence but hold a
deliberate >= 0.5 s pause mid-sentence at the marked point — keep the
pitch hanging (do not drop to sentence-final intonation), a filler
(``呃``/``嗯``) is welcome. Complete items: speak naturally, no deliberate
pause.

Usage (from backend/):
    uv run python scripts/record_ab_fixture.py --from-file ~/clip.m4a \
        zh-hu incomplete check_weather_hu1
    uv run python scripts/record_ab_fixture.py --mic 6 \
        zh-hu complete weather_today_hu1
    uv run python scripts/eval_smart_turn.py --model-path \
        models/smart-turn/smart-turn-v3.2-cpu.onnx
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import wave
from pathlib import Path

import numpy as np

SR = 16000
THRESH = 0.004
PAUSE_MS = 250  # candidate boundary the pipeline actually acts on
TAIL_MS = 250


def load_from_file(path: Path) -> np.ndarray:
    raw = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", str(path), "-f", "s16le",
         "-ac", "1", "-ar", str(SR), "-"],
        capture_output=True, check=True,
    ).stdout
    return np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0


def load_from_mic(seconds: float) -> np.ndarray:
    import sounddevice as sd

    print(f"Recording {seconds:.0f}s — speak now…")
    audio = sd.rec(int(seconds * SR), samplerate=SR, channels=1, dtype=np.float32)
    sd.wait()
    return audio.flatten()


def cut_like_fixtures(pcm: np.ndarray) -> tuple[np.ndarray, str]:
    """Apply the TTS-set cut: first internal pause, else end of speech."""
    win = int(SR * 0.05)
    n = len(pcm) // win
    rms = np.array([
        float(np.sqrt((pcm[i * win:(i + 1) * win] ** 2).mean())) for i in range(n)
    ])
    # Adaptive speech threshold: room noise (this VM's mic idles at
    # rms ~0.006) must read as silence or no pause is ever found, so
    # scale from the quietest 10% of windows, floored at the TTS-set
    # threshold for already-clean recordings.
    thresh = max(THRESH, float(np.percentile(rms, 10)) * 3.0)
    loud = np.where(rms > thresh)[0]
    if not len(loud):
        raise SystemExit("no speech detected in the clip (all windows below threshold)")
    start, end = loud[0] * win, (loud[-1] + 1) * win
    tail = int(SR * TAIL_MS / 1000)
    pause = int(SR * PAUSE_MS / 1000)

    lo, hi = start + int(SR * 0.3), end - int(SR * 0.3)
    i = lo // win
    while i * win < hi:
        if rms[i] <= thresh:
            j = i
            while j < len(rms) and rms[j] <= thresh:
                j += 1
            if (j - i) * win >= pause:
                cut = min(i * win + tail, end)
                return pcm[:cut], f"cut at first internal pause ({i * win / SR:.2f}s)"
            i = j
        else:
            i += 1
    cut = min(end + tail, len(pcm))
    return pcm[:cut], f"no internal pause — trimmed to speech end ({end / SR:.2f}s)"


def main() -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    src = parser.add_mutually_exclusive_group(required=True)
    src.add_argument("--from-file", type=Path, help="existing recording (any ffmpeg format)")
    src.add_argument("--mic", type=float, metavar="SECONDS", help="record from default input")
    parser.add_argument("lang", help="language tag, use zh-hu / en-hu for human clips")
    parser.add_argument("label", choices=("complete", "incomplete"))
    parser.add_argument("name", help="fixture name (without extension)")
    parser.add_argument(
        "--fixtures-dir", type=Path,
        default=Path(__file__).resolve().parent / "smart_turn_ab",
    )
    args = parser.parse_args()

    if args.from_file is not None:
        pcm = load_from_file(args.from_file)
        source = str(args.from_file)
    elif args.mic is not None:
        pcm = load_from_mic(args.mic)
        source = "microphone"
    else:
        raise SystemExit("either --from-file or --mic is required")

    clipped, how = cut_like_fixtures(pcm)
    out = args.fixtures_dir / args.lang / args.label / f"{args.name}.wav"
    out.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(out), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes((np.clip(clipped, -1, 1) * 32767).astype(np.int16).tobytes())
    print(f"{source} -> {out} ({len(clipped) / SR:.2f}s, {how})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
