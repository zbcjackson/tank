"""Static coordinate probe on a fixed, already-reviewed controlled frame.

Never captures the screen and never performs desktop input: it only sends the
provided frame to the model and scores the returned point against measured
button rectangles. Reuses the production request builder, response parser and
scoring from ``tank_backend.benchmarks.grounding_probe``.

From backend:
  uv run python scripts/probe_real_frame_grounding.py \
    --frame /tmp/tank-m5-pumped-a-20260924-live/initial.png \
    --truth /tmp/tank-button-truth.json --output /tmp/probe-real-frame
"""
from __future__ import annotations

import argparse
import asyncio
import base64
import gzip
import hashlib
import json
import os
import time
from pathlib import Path
from typing import Any

os.environ["LANGFUSE_TRACING_ENABLED"] = "false"

import httpx
from dotenv import load_dotenv
from openai import APIError, AsyncOpenAI

from tank_backend.agents.definition import GroundingConfig
from tank_backend.benchmarks.grounding_probe import location_request, score_location
from tank_backend.config.app_config import AppConfig
from tank_backend.tools.computer_grounding import GroundingAdapter
from tank_backend.tools.computer_integrated import integrated_prompt
from tank_backend.tools.computer_use_common import crop_pixels_and_upscale

ROOT = Path(__file__).resolve().parents[1]
MODEL = "qwen3.7-flash-2026-07-15"
PROVIDER = "qwen"
WINDOW_CROP = (600, 100, 1274, 508)  # measured Calculator window in the frame
VARIANTS = (  # (name, protocol, cropped)
    ("full-point", "point", False),
    ("crop-point", "point", True),
    ("full-pixels", "pixels", False),
    ("crop-pixels", "pixels", True),
)
TARGETS = ("7", "8", "multiply", "equals")
TARGET_LABELS: dict[str, str] = {"7": "7", "8": "8", "multiply": "\u00d7", "equals": "="}


def button_label(target: str) -> str:
    """Ask for the glyph actually rendered on the button, not an internal name."""
    return TARGET_LABELS.get(target, target)


def build_image(frame: bytes, cropped: bool) -> tuple[bytes, tuple[int, int], tuple[int, int, int, int] | None]:
    if not cropped:
        return frame, _png_size(frame), None
    png = crop_pixels_and_upscale(frame, WINDOW_CROP)
    return png, _png_size(png), WINDOW_CROP


def _png_size(png: bytes) -> tuple[int, int]:
    import io

    from PIL import Image

    with Image.open(io.BytesIO(png)) as image:
        return image.size


def _system_message(prompt_mode: str, protocol: str, cropped: bool) -> str:
    if prompt_mode == "locator":
        return "Locate the requested UI element in the current image."
    # Reuse the production integrated contract text (the one the trials ran under).
    return integrated_prompt(GroundingConfig(
        mode="integrated", protocol=protocol, host_restore=cropped,
        nullable_style="integer", detail="auto", status_field=False,
    ))


def _coerce_numeric_strings(arguments: str) -> str | None:
    """Rewrite numeric strings the way the production legacy path reads them."""
    try:
        values = json.loads(arguments)
    except json.JSONDecodeError:
        return None
    if not isinstance(values, dict):
        return None
    for key in ("x", "y"):
        value = values.get(key)
        if isinstance(value, str):
            text = value.strip()
            if text.lstrip("-").isdigit():
                values[key] = int(text)
            else:
                return None
    box = values.get("bbox")
    if isinstance(box, list) and all(
            isinstance(v, str) and v.strip().lstrip("-").isdigit() for v in box):
        values["bbox"] = [int(v) for v in box]
    return json.dumps(values)


async def run_trial(
    client: AsyncOpenAI, output: Path, trial_id: str, target: str, variant: str,
    protocol: str, frame: bytes, truth: dict[str, dict[str, int]], max_tokens: int,
    prompt_mode: str,
) -> dict[str, Any]:
    png, size, crop = build_image(frame, cropped=variant.startswith("crop"))
    digest = hashlib.sha256(png).hexdigest()
    (output / f"frame-{digest}.png").write_bytes(png)
    box = truth[target]
    bounds = (box["x"], box["y"], box["x"] + box["w"] - 1, box["y"] + box["h"] - 1)
    kwargs = location_request(
        PROVIDER, MODEL, png, size, button_label(target), protocol,
        strict=False, detail="auto",
        thinking=False, max_tokens=max_tokens,
        system=_system_message(prompt_mode, protocol, crop is not None),
    )
    row: dict[str, Any] = {
        "id": trial_id, "variant": variant, "protocol": protocol, "target": target,
        "image_size": list(size), "crop": list(crop) if crop else None,
        "frame_sha256": digest, "bounds": list(bounds), "hit": False, "schema_valid": False,
        "prompt_mode": prompt_mode,
    }

    async def capture_request(request: httpx.Request) -> None:
        body = json.loads(request.content)
        for message in body["messages"]:
            if not isinstance(message.get("content"), list):
                continue
            for part in message["content"]:
                if part.get("type") == "image_url":
                    raw = base64.b64decode(part["image_url"]["url"].split(",", 1)[1])
                    if hashlib.sha256(raw).hexdigest() != digest:
                        raise ValueError("HTTP image differs from the bound trial")
                    part["image_url"]["url"] = f"sha256:{digest}"
        (output / f"{trial_id}.request.json").write_text(json.dumps(body, indent=2))

    async def capture_response(response: httpx.Response) -> None:
        raw = await response.aread()
        (output / f"{trial_id}.response.json.gz").write_bytes(gzip.compress(raw))
        row["http_status"] = response.status_code

    client._client.event_hooks["request"] = [capture_request]
    client._client.event_hooks["response"] = [capture_response]
    started = time.monotonic()
    try:
        async with asyncio.timeout(90):
            result = await client.chat.completions.create(**kwargs)
        row["usage"] = result.usage.model_dump() if result.usage else None
        calls = result.choices[0].message.tool_calls or []
        if len(calls) != 1:
            raise ValueError(f"Expected one tool call, got {len(calls)}")
        row["arguments"] = calls[0].function.arguments
        adapter = GroundingAdapter(protocol, "integer")
        try:
            location = adapter.parse_response(result, size)
            row["strict_ok"] = True
        except ValueError as strict_error:
            # Measure how often a correct answer is discarded for its JSON type.
            row["strict_ok"] = False
            row["strict_error"] = f"{type(strict_error).__name__}: {strict_error}"[:120]
            coerced = _coerce_numeric_strings(calls[0].function.arguments)
            if coerced is None:
                raise
            calls[0].function.arguments = coerced
            row["coerced"] = coerced
            location = adapter.parse_response(result, size)
        point = location.point
        row["schema_valid"] = True
        row["abstained"] = point is None
        if point is not None:
            if crop is not None:
                ox, oy, _, _ = crop
                point = (ox + point[0] * (crop[2] - crop[0]) / size[0],
                         oy + point[1] * (crop[3] - crop[1]) / size[1])
            row["point"] = [round(point[0], 1), round(point[1], 1)]
            row.update(score_location(point, bounds, 12))
            row["expected_center"] = [box["cx"], box["cy"]]
    except (APIError, ValueError, TimeoutError, IndexError) as exc:
        row["error"] = type(exc).__name__ + ": " + str(exc)[:300]
    row["seconds"] = round(time.monotonic() - started, 2)
    return row


def summarise(rows: list[dict[str, Any]]) -> dict[str, Any]:
    summary: dict[str, Any] = {}
    for name, *_ in VARIANTS:
        subset = [r for r in rows if r["variant"] == name and r.get("point")]
        if not subset:
            continue
        hits = sum(1 for r in subset if r["hit"])
        lenient = sum(1 for r in subset if r.get("strict_ok") is False)
        summary[name] = {
            "n": len(subset), "hits": hits, "strict_type_violations": lenient,
            "mean_abs_dx": round(sum(abs(r["dx"]) for r in subset) / len(subset), 1),
            "mean_abs_dy": round(sum(abs(r["dy"]) for r in subset) / len(subset), 1),
            "mean_distance": round(sum(r["distance"] for r in subset) / len(subset), 1),
            "max_distance": round(max(r["distance"] for r in subset), 1),
        }
    return summary


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--frame", type=Path, required=True)
    parser.add_argument("--truth", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--targets", nargs="+", choices=TARGETS, default=list(TARGETS))
    parser.add_argument("--variants", nargs="+", default=[name for name, *_ in VARIANTS])
    parser.add_argument("--repeats", type=int, default=2)
    parser.add_argument("--prompt-mode", choices=["locator", "integrated"], default="integrated",
                        help="integrated reuses the production contract text the trials ran under")
    parser.add_argument("--max-tokens", type=int, default=2000)
    parser.add_argument("--dry-run", action="store_true",
                        help="write request bodies without sending anything")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    frame = args.frame.read_bytes()
    truth = json.loads(args.truth.read_text())
    jobs = [(variant, target, repeat)
            for variant, protocol, _ in VARIANTS if variant in args.variants
            for target in args.targets for repeat in range(args.repeats)]

    load_dotenv(ROOT / "core/.env")
    profile = AppConfig.load(ROOT / "core/config.yaml").get_llm_profile("computer_use")
    options = {key: (str(value) if isinstance(value, Path) else value)
               for key, value in vars(args).items()}
    report: dict[str, Any] = {"options": options, "frame": str(args.frame),
                              "model": MODEL, "results": []}
    if args.dry_run:
        for variant, target, repeat in jobs:
            protocol = next(p for name, p, _ in VARIANTS if name == variant)
            png, size, crop = build_image(frame, cropped=variant.startswith("crop"))
            kwargs = location_request(PROVIDER, MODEL, png, size, button_label(target),
                                      protocol, detail="auto", thinking=False,
                                      max_tokens=args.max_tokens,
                                      system=_system_message(args.prompt_mode, protocol,
                                                             variant.startswith("crop")))
            body = {k: v for k, v in kwargs.items() if k != "messages"}
            images = [len(base64.b64decode(p["image_url"]["url"].split(",", 1)[1]))
                      for m in kwargs["messages"] if isinstance(m.get("content"), list)
                      for p in m["content"] if p.get("type") == "image_url"]
            report["results"].append({"variant": variant, "target": target, "repeat": repeat,
                                      "image_size": list(size), "crop": crop,
                                      "image_bytes": images, "request": body})
        (args.output / "dry-run.json").write_text(json.dumps(report, indent=2, default=str))
        print(f"dry run: {len(jobs)} requests, nothing sent; see {args.output}/dry-run.json")
        return

    if not profile.api_key:
        raise SystemExit("missing provider credential")
    async with AsyncOpenAI(api_key=profile.api_key, base_url=profile.base_url,
                           max_retries=0, timeout=85) as client:
        for variant, target, repeat in jobs:
            protocol = next(p for name, p, _ in VARIANTS if name == variant)
            trial_id = f"{variant}-{target}-{repeat}"
            row = await run_trial(client, args.output, trial_id, target, variant, protocol,
                                  frame, truth, args.max_tokens, args.prompt_mode)
            report["results"].append(row)
            report["summary"] = summarise(report["results"])
            (args.output / "results.json").write_text(json.dumps(report, indent=2, default=str))
            print(json.dumps({k: row.get(k) for k in
                              ("id", "strict_ok", "hit", "dx", "dy", "distance",
                               "error", "seconds")}), flush=True)
    print(json.dumps(report["summary"], indent=2))


if __name__ == "__main__":
    asyncio.run(main())
