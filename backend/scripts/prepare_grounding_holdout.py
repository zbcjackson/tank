"""Freeze 64 synthetic grounding layouts offline, with separately stored truth.

Run from backend: uv run --no-sync python scripts/prepare_grounding_holdout.py
--output benchmarks/computer_use/reports/<new-batch>/holdout
Never reads desktop pixels, credentials or model responses; never sends requests.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import random
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, __version__ as pillow_version

STRATA = ("dense", "sparse", "small", "typography", "scale", "occluded",
          "duplicate", "absent")
SIZES = ((1201, 801), (901, 1401), (1601, 1001), (1001, 1601))
LABELS = ("AC", "7", "8", "9", "4", "5", "6", "1", "2", "3", "0", "=")


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    output: Path = args.output
    output.mkdir(parents=True, exist_ok=False)
    (output / "images").mkdir()
    (output / "truth").mkdir()
    inputs = []
    truth = []
    for index in range(64):
        seed = 2026092000 + index
        rng = random.Random(seed)
        stratum = STRATA[index // 8]
        size = SIZES[index % len(SIZES)]
        image = Image.new("RGB", size, "#23272e")
        draw = ImageDraw.Draw(image)
        mask = Image.new("L", size)
        mask_draw = ImageDraw.Draw(mask)
        labels: list[str] = list(LABELS)
        rng.shuffle(labels)
        target = LABELS[index % len(LABELS)]
        expected = "found"
        if stratum == "absent":
            expected = "not_found"
            labels[labels.index(target)] = "DEL"
        elif stratum == "duplicate":
            expected = "ambiguous"
            labels[(labels.index(target) + 1) % len(labels)] = target
        factor = (0.75, 1, 1.5, 2)[index % 4] if stratum == "scale" else 1
        width, height = (32, 24) if stratum == "small" else (
            round(76 * factor), round(48 * factor))
        gap = 3 if stratum == "dense" else 24 if stratum == "sparse" else 12
        radius = min(10, height // 4)
        panel_width = 4 * (width + gap) + 28
        panel_height = 3 * (height + gap) + 70
        left = rng.randrange(12, size[0] - panel_width - 12)
        top = rng.randrange(12, size[1] - panel_height - 12)
        draw.rounded_rectangle((left, top, left + panel_width, top + panel_height),
                               radius=12, fill="#363941")
        font_size = 11 if stratum == "small" else (
            (13, 17, 23, 27)[index % 4] if stratum == "typography" else round(19 * factor))
        font = ImageFont.load_default(size=font_size)
        draw.text((left + 14, top + 14), "Synthetic keypad", font=font, fill="white")
        buttons = []
        center = None
        occlusion = None
        for slot, label in enumerate(labels):
            x = left + 14 + (slot % 4) * (width + gap)
            y = top + 54 + (slot // 4) * (height + gap)
            bounds = (x, y, x + width - 1, y + height - 1)
            point = (x + width // 2, y + height // 2)
            draw.rounded_rectangle(bounds, radius=radius, fill="#646a75")
            draw.text(point, label, font=font, fill="white", anchor="mm")
            buttons.append({"label": label, "bounds": bounds, "radius": radius})
            if label == target and expected == "found":
                center = point
                mask_draw.rounded_rectangle(bounds, radius=radius, fill=255)
                if stratum == "occluded":
                    occlusion = (x - 3, y - 3, x + width + 3, y + 6)
        if occlusion is not None:
            draw.rectangle(occlusion, fill="#a0a7b5")
            mask_draw.rectangle(occlusion, fill=0)
        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        png = buffer.getvalue()
        case_id = f"layout-{index:02d}"
        image_path = f"images/{case_id}.png"
        mask_path = f"truth/{case_id}-mask.png"
        (output / image_path).write_bytes(png)
        mask.save(output / mask_path)
        inputs.append({"id": case_id, "image": image_path,
                       "image_sha256": hashlib.sha256(png).hexdigest(),
                       "size": size, "target": target})
        truth.append({"id": case_id, "seed": seed, "stratum": stratum,
                      "expected": expected, "center": center, "mask": mask_path,
                      "font_size": font_size, "buttons": buttons, "occlusion": occlusion})
    write_json(output / "inputs.json", inputs)
    write_json(output / "truth/labels.json", truth)
    write_json(output / "generation.json", {
        "generator_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "pillow_version": pillow_version, "font": "Pillow bundled default scalable font",
        "seed_start": 2026092000, "layouts": 64, "model_requests": 0,
        "truth_policy": "Only inputs.json and its image may enter the model request. "
                        "Never send truth/, masks, seed, center or stratum. Freeze adapters "
                        "on historical/development data before evaluating these layouts.",
    })


if __name__ == "__main__":
    main()
