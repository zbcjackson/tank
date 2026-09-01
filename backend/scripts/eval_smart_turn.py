#!/usr/bin/env python3
"""Offline A/B eval of the Smart Turn endpoint classifier on labeled audio.

Answers the open question from docs/vad-smart-turn-design.md §10: the
smart-turn-v3 model is English-trained, so Chinese utterance-completeness
accuracy must be measured before trusting it in production (fall back to
``smart_turn.enabled: false`` if it misendpoints).

Fixtures live in ``scripts/smart_turn_ab/<lang>/<label>/*.wav`` where
``label`` is ``complete`` (a finished turn) or ``incomplete`` (speech that
paused mid-utterance — the class a misendpoint would cut off). The harmful
direction is an ``incomplete`` file classified ``complete``: the pipeline
would commit the turn while the user is still mid-sentence. The safe
direction (``complete`` classified ``incomplete``) only costs the
``incomplete_delay_ms`` hold.

Fixture construction (both classes identically treated so the only
variable is content/prosody): synthesize a two-clause sentence with
edge-tts, locate the inter-clause pause, and cut at pause start + 250 ms.
For ``complete`` the full sentence is kept (cut at its own final pause);
for ``incomplete`` only the pre-pause clause survives.

Usage (from backend/):
    uv run python scripts/eval_smart_turn.py [--fixtures-dir ...] [--threshold 0.5]
"""

from __future__ import annotations

import argparse
import json
import sys
import wave
from pathlib import Path

import numpy as np

from tank_backend.audio.input.smart_turn import SmartTurnAnalyzer

DEFAULT_FIXTURES = Path(__file__).resolve().parent / "smart_turn_ab"


def load_wav(path: Path) -> tuple[np.ndarray, int]:
    with wave.open(str(path)) as w:
        rate = w.getframerate()
        pcm = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16)
    return pcm.astype(np.float32) / 32768.0, rate


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--fixtures-dir", type=Path, default=DEFAULT_FIXTURES)
    parser.add_argument("--threshold", type=float, default=0.5)
    parser.add_argument(
        "--model-path", default=None,
        help="ONNX model path (default: SmartTurnAnalyzer's DEFAULT_MODEL_PATH, "
             "resolved relative to the CWD — the server runs from core/)",
    )
    parser.add_argument("--json", action="store_true", help="Machine-readable output")
    args = parser.parse_args()

    analyzer = SmartTurnAnalyzer(threshold=args.threshold, model_path=args.model_path)
    rows: list[dict[str, object]] = []
    for wav in sorted(args.fixtures_dir.glob("*/*/*.wav")):
        label = wav.parent.name  # complete | incomplete
        lang = wav.parent.parent.name  # zh | en
        pcm, rate = load_wav(wav)
        result = analyzer.predict(pcm, sample_rate=rate)
        rows.append({
            "lang": lang,
            "label": label,
            "file": wav.name,
            "predicted": "complete" if result.complete else "incomplete",
            "probability": round(result.probability, 4),
            "inference_ms": round(result.inference_ms, 1),
        })

    if args.json:
        print(json.dumps(rows, ensure_ascii=False, indent=2))
        return 0

    print(f"{'lang':4} {'label':10} {'pred':10} {'P(complete)':>11} {'ms':>6}  file")
    for r in rows:
        mark = "OK " if r["label"] == r["predicted"] else "!! "
        print(
            f"{mark}{r['lang']:2} {r['label']:10} {r['predicted']:10} "
            f"{r['probability']:11.4f} {r['inference_ms']:6.1f}  {r['file']}"
        )

    print("\nSummary (the harmful direction is incomplete→complete):")
    for lang in sorted({str(r["lang"]) for r in rows}):
        sub = [r for r in rows if r["lang"] == lang]
        inc = [r for r in sub if r["label"] == "incomplete"]
        comp = [r for r in sub if r["label"] == "complete"]
        misendpoint = [r for r in inc if r["predicted"] == "complete"]
        overhold = [r for r in comp if r["predicted"] == "incomplete"]
        print(
            f"  {lang}: 误断率(incomplete→complete) {len(misendpoint)}/{len(inc)}"
            f"   过度扣留(complete→incomplete) {len(overhold)}/{len(comp)}"
        )
        for r in misendpoint:
            print(f"    MIS-ENDPOINT: {r['file']} (P={r['probability']})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
