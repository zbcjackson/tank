"""Static grounding matrix on fixed frames: units x framing x models x targets.

Never captures the screen and never performs desktop input. It only sends the
provided frames to the models and scores the returned points against measured
target rectangles. Reuses the production request builder, parser and scoring.

Single frame (as before):
  uv run python scripts/probe_real_frame_grounding.py \
    --frame /tmp/frame.png --truth /tmp/truth.json --output /tmp/out

Matrix (what the M5 interface comparison uses):
  uv run python scripts/probe_real_frame_grounding.py --spec /tmp/spec.json \
    --models flash max --output /tmp/out
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
MODELS: dict[str, tuple[str, str]] = {
    "flash": ("qwen", "qwen3.7-flash-2026-07-15"),
    "plus": ("qwen", "qwen3.7-plus-2026-05-26"),
    "max": ("qwen", "qwen3.8-max-2026-09-02"),
    "gptmini": ("openrouter", "openai/gpt-5.4-mini"),
    "gpt55": ("openrouter", "openai/gpt-5.5"),
}
VARIANTS = (  # (name, protocol, cropped)
    ("full-point", "point", False),
    ("crop-point", "point", True),
    ("full-pixels", "pixels", False),
    ("crop-pixels", "pixels", True),
)
TARGET_LABELS: dict[str, str] = {"7": "7", "8": "8", "multiply": "\u00d7", "equals": "="}


def button_label(target: str) -> str:
    return TARGET_LABELS.get(target, target)


def _png_size(png: bytes) -> tuple[int, int]:
    import io

    from PIL import Image

    with Image.open(io.BytesIO(png)) as image:
        return image.size


def build_image(frame: bytes, crop: tuple[int, int, int, int] | None,
                cropped: bool) -> tuple[bytes, tuple[int, int], tuple[int, int, int, int] | None]:
    if not cropped:
        return frame, _png_size(frame), None
    if crop is None:
        raise ValueError("crop variant requires a crop rectangle")
    png = crop_pixels_and_upscale(frame, crop)
    return png, _png_size(png), crop


def _system_message(prompt_mode: str, protocol: str, cropped: bool) -> str:
    if prompt_mode == "locator":
        return "Locate the requested UI element in the current image."
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
            if text.lstrip("+-").isdigit():
                values[key] = int(text)
            else:
                return None
    box = values.get("bbox")
    if isinstance(box, list) and all(
            isinstance(v, str) and v.strip().lstrip("+-").isdigit() for v in box):
        values["bbox"] = [int(v) for v in box]
    return json.dumps(values)


async def run_trial(
    client: AsyncOpenAI, provider: str, model: str, output: Path, trial_id: str,
    frame_name: str, target: str, variant: str, protocol: str, frame: bytes,
    crop: tuple[int, int, int, int] | None, truth: dict[str, dict[str, int]],
    max_tokens: int, prompt_mode: str,
) -> dict[str, Any]:
    png, size, crop = build_image(frame, crop, cropped=variant.startswith("crop"))
    digest = hashlib.sha256(png).hexdigest()
    (output / f"frame-{digest}.png").write_bytes(png)
    box = truth[target]
    bounds = (box["x"], box["y"], box["x"] + box["w"] - 1, box["y"] + box["h"] - 1)
    kwargs = location_request(
        provider, model, png, size, button_label(target), protocol, strict=False,
        detail="auto", thinking=False, max_tokens=max_tokens,
        system=_system_message(prompt_mode, protocol, crop is not None),
    )
    row: dict[str, Any] = {
        "id": trial_id, "model": model, "provider": provider, "frame": frame_name,
        "variant": variant, "protocol": protocol, "target": target,
        "image_size": list(size), "crop": list(crop) if crop else None,
        "frame_sha256": digest, "bounds": list(bounds), "target_size": [box["w"], box["h"]],
        "hit": False, "schema_valid": False, "prompt_mode": prompt_mode,
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
            radius = max(3, min(box["w"], box["h"]) // 4)
            row.update(score_location(point, bounds, radius))
            row["expected_center"] = [box["cx"], box["cy"]]
    except (APIError, ValueError, TimeoutError, IndexError) as exc:
        row["error"] = type(exc).__name__ + ": " + str(exc)[:300]
    row["seconds"] = round(time.monotonic() - started, 2)
    return row


def _stats(subset: list[dict[str, Any]]) -> dict[str, Any]:
    placed = [r for r in subset if r.get("point")]
    if not placed:
        return {"n": len(subset), "placed": 0}
    return {
        "n": len(subset), "placed": len(placed),
        "hits": sum(1 for r in placed if r["hit"]),
        "strict_type_violations": sum(1 for r in subset if r.get("strict_ok") is False),
        "mean_abs_dx": round(sum(abs(r["dx"]) for r in placed) / len(placed), 1),
        "mean_abs_dy": round(sum(abs(r["dy"]) for r in placed) / len(placed), 1),
        "mean_distance": round(sum(r["distance"] for r in placed) / len(placed), 1),
        "max_distance": round(max(r["distance"] for r in placed), 1),
    }


def summarise(rows: list[dict[str, Any]]) -> dict[str, Any]:
    summary: dict[str, Any] = {}
    for row in rows:
        for key in (f"{row['frame']}/{row['variant']}",
                    f"{row['frame']}/{row['variant']}/{row['model']}"):
            summary.setdefault(key, [])
    for key in list(summary):
        parts = key.split("/")
        subset = [r for r in rows
                  if r["frame"] == parts[0] and r["variant"] == parts[1]
                  and (len(parts) == 2 or r["model"] == parts[2])]
        summary[key] = _stats(subset)
    return summary


def load_spec(args: argparse.Namespace) -> dict[str, Any]:
    if args.spec is not None:
        spec = json.loads(args.spec.read_text())
    else:
        if args.frame is None or args.truth is None:
            raise SystemExit("provide --spec or --frame with --truth")
        spec = {"frames": [{"name": "frame", "png": str(args.frame),
                            "truth": str(args.truth), "crop": args.crop,
                            "targets": args.targets}]}
    for frame in spec["frames"]:
        frame.setdefault("crop", None)
    return spec


def provider_client_kwargs(provider: str, profile: Any) -> tuple[str, str]:
    if provider == "qwen":
        return profile.base_url, profile.api_key
    if provider == "openrouter":
        return "https://openrouter.ai/api/v1", os.environ.get("OPENROUTER_API_KEY", "")
    raise SystemExit(f"unknown provider {provider}")


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--spec", type=Path)
    parser.add_argument("--frame", type=Path)
    parser.add_argument("--truth", type=Path)
    parser.add_argument("--crop", help="l,t,r,b for the crop variants of --frame")
    parser.add_argument("--targets", nargs="+")
    parser.add_argument("--models", nargs="+", choices=sorted(MODELS), default=["flash"])
    parser.add_argument("--variants", nargs="+", default=[name for name, *_ in VARIANTS])
    parser.add_argument("--repeats", type=int, default=1)
    parser.add_argument("--prompt-mode", choices=["locator", "integrated"], default="integrated")
    parser.add_argument("--max-tokens", type=int, default=2000)
    parser.add_argument("--model-total-cap", type=int, default=0,
                        help="stop a model after this many requests (0 = no cap)")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    if args.crop:
        args.crop = tuple(int(v) for v in args.crop.split(","))
    args.output.mkdir(parents=True, exist_ok=False)
    spec = load_spec(args)
    frames = {}
    for frame in spec["frames"]:
        frames[frame["name"]] = {
            "png": Path(frame["png"]).read_bytes(),
            "truth": json.loads(Path(frame["truth"]).read_text()),
            "crop": tuple(frame["crop"]) if frame["crop"] else None,
            "targets": frame["targets"],
        }
    load_dotenv(ROOT / "core/.env")
    profile = AppConfig.load(ROOT / "core/config.yaml").get_llm_profile("computer_use")
    options = {key: (str(value) if isinstance(value, Path) else value)
               for key, value in vars(args).items()}
    report: dict[str, Any] = {"options": options, "spec": spec, "results": []}

    jobs = [
        (alias, frame_name, variant, target, repeat)
        for alias in args.models
        for frame_name, frame in frames.items()
        for variant, protocol, _ in VARIANTS if variant in args.variants
        for target in frame["targets"]
        for repeat in range(args.repeats)
    ]
    if args.dry_run:
        for alias, frame_name, variant, target, _ in jobs:
            protocol = next(p for name, p, _ in VARIANTS if name == variant)
            frame = frames[frame_name]
            png, size, crop = build_image(frame["png"], frame["crop"],
                                         variant.startswith("crop"))
            report["results"].append({"model": MODELS[alias][1], "frame": frame_name,
                                      "variant": variant, "target": target,
                                      "image_size": list(size), "crop": crop,
                                      "image_bytes": len(png)})
        (args.output / "dry-run.json").write_text(json.dumps(report, indent=2, default=str))
        print(f"dry run: {len(jobs)} requests, nothing sent; see {args.output}/dry-run.json")
        return

    for alias in args.models:
        provider, model = MODELS[alias]
        endpoint, key = provider_client_kwargs(provider, profile)
        if not key:
            report["results"].append({"model": model, "error": "missing credential"})
            continue
        sent = 0
        async with AsyncOpenAI(api_key=key, base_url=endpoint, max_retries=0,
                               timeout=85) as client:
            for job in [j for j in jobs if j[0] == alias]:
                _, frame_name, variant, target, repeat = job
                if args.model_total_cap and sent >= args.model_total_cap:
                    break
                protocol = next(p for name, p, _ in VARIANTS if name == variant)
                frame = frames[frame_name]
                trial_id = f"{alias}-{frame_name}-{variant}-{target}-{repeat}"
                row = await run_trial(client, provider, model, args.output, trial_id,
                                      frame_name, target, variant, protocol, frame["png"],
                                      frame["crop"], frame["truth"], args.max_tokens,
                                      args.prompt_mode)
                sent += 1
                report["results"].append(row)
                report["summary"] = summarise(report["results"])
                (args.output / "results.json").write_text(json.dumps(report, indent=2, default=str))
                print(json.dumps({k: row.get(k) for k in (
                    "id", "strict_ok", "hit", "distance", "error", "seconds")}), flush=True)
                if row.get("http_status") in {401, 402, 403, 404}:
                    break
    print(json.dumps(report["summary"], indent=2))


if __name__ == "__main__":
    asyncio.run(main())
