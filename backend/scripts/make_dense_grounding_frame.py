"""Generate a small-target grounding frame: a dense toolbar of 24x24 controls.

The real controlled frame measures 60x48 buttons on a 1920x1080 screen, which is
the easy end of dense UIs. This frame renders 24x24 controls with the same
labels, so the static matrix can separate "the model does not know where the
container is" from "the model cannot resolve a small target".

From backend:
  uv run python scripts/make_dense_grounding_frame.py --output /tmp/dense-frame
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from PIL import Image, ImageDraw

SIZE = (1920, 1080)
BUTTON = 24
PITCH = 32
ROW_Y = 540
LABELS = ["0", "1", "2", "3", "4", "5", "6", "7", "8", "9", "+", "-"]
BACKGROUND = (32, 32, 32)
FACE = (74, 72, 73)
GLYPH = (233, 233, 233)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    image = Image.new("RGB", SIZE, BACKGROUND)
    draw = ImageDraw.Draw(image)
    total = len(LABELS) * PITCH - (PITCH - BUTTON)
    left = (SIZE[0] - total) // 2
    truth: dict[str, dict[str, int]] = {}
    for index, label in enumerate(LABELS):
        x = left + index * PITCH
        draw.rounded_rectangle((x, ROW_Y, x + BUTTON - 1, ROW_Y + BUTTON - 1),
                               radius=4, fill=FACE)
        box = draw.textbbox((0, 0), label)
        draw.text((x + (BUTTON - (box[2] - box[0])) / 2 - box[0],
                   ROW_Y + (BUTTON - (box[3] - box[1])) / 2 - box[1]),
                  label, fill=GLYPH)
        truth[label] = {"x": x, "y": ROW_Y, "w": BUTTON, "h": BUTTON,
                        "cx": x + BUTTON // 2, "cy": ROW_Y + BUTTON // 2}
    png = args.output / "dense.png"
    image.save(png, format="PNG")
    (args.output / "dense-truth.json").write_text(json.dumps(truth, indent=2) + "\n")
    print(json.dumps({"png": str(png), "button": BUTTON, "pitch": PITCH,
                      "toolbar_crop": [left, ROW_Y, left + total, ROW_Y + BUTTON],
                      "targets": ["4", "7", "-"]}, indent=2))


if __name__ == "__main__":
    main()
