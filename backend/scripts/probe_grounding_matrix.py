"""Paid, synthetic-only grounding experiments; never capture or click the desktop.

Run from backend with --output (fresh directory), --models and --variants.
Raw provider JSON and sanitized HTTP request bodies are retained for attribution.
"""
from __future__ import annotations

import argparse
import asyncio
import base64
import gzip
import hashlib
import io
import json
import os
import random
import time
from pathlib import Path
from typing import Any

os.environ["LANGFUSE_TRACING_ENABLED"] = "false"

import httpx
from dotenv import load_dotenv
from openai import APIError, AsyncOpenAI
from PIL import Image
from probe_grounding_contract import scene

from tank_backend.benchmarks.grounding_probe import (
    location_request,
    score_location,
)
from tank_backend.config.app_config import AppConfig
from tank_backend.tools.computer_grounding import GroundingAdapter

ROOT = Path(__file__).resolve().parents[1]
MODELS = {
    "flash": ("qwen", "qwen3.7-flash-2026-07-15"),
    "plus": ("qwen", "qwen3.7-plus-2026-05-26"),
    "qwen38flash": ("qwen", "qwen3.8-flash"),
    "qwen38max": ("qwen", "qwen3.8-max-2026-09-02"),
    "deepseek": ("deepseek", "deepseek-flash"),
    "gptmini": ("openrouter", "openai/gpt-5.4-mini"),
    "gpt55": ("openrouter", "openai/gpt-5.5"),
}
VARIANTS = (
    "point", "bbox", "pixels", "strict-point", "strict-bbox", "marked", "shuffled",
    "history", "crop", "resized", "agent", "absent", "low-detail", "no-thinking",
    "anyof-point", "anyof-bbox", "full-tools",
)


def make_case(seed: int, variant: str) -> dict[str, Any]:
    """Generate paired counterfactuals with identical underlying geometry."""
    rng = random.Random(seed)
    size = [(1680, 1050), (1440, 900), (1050, 1680), (1536, 1024)][seed % 4]
    position = (rng.uniform(.1, .9), rng.uniform(.1, .9))
    target = "7" if seed % 2 == 0 else "AC"
    png, targets = scene(size, position, shuffle_seed=seed if variant == "shuffled" else None,
                         marked=target if variant == "marked" else None)
    center = targets[target]
    width = min(672, int(size[0] * .7))
    scale = width / 672
    height = round(407 * scale)
    left = round((size[0] - width) * position[0])
    top = round((size[1] - height) * position[1])
    rx, ry = round(30 * scale), round(24 * scale)
    crop = None
    original = png
    image = Image.open(io.BytesIO(png))
    if variant == "crop":
        image = image.crop((left, top, left + width, top + height)).resize((width * 2, height * 2))
        crop = (left, top, width, height)
    elif variant == "resized":
        image = image.resize((size[0] * 2 // 3, size[1] * 2 // 3))
        crop = (0, 0, *size)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    previous = None
    if variant == "history":
        previous, _ = scene(size, (1 - position[0], 1 - position[1]))
    return {
        "png": buffer.getvalue(), "original": original, "size": image.size,
        "source_size": size, "previous": previous, "target": target,
        "center": center, "crop": crop,
        "bounds": (center[0]-rx, center[1]-ry, center[0]+rx, center[1]+ry),
        "radius": round(22 * scale),
    }


async def run_trial(
    client: AsyncOpenAI, provider: str, model: str, seed: int, variant: str,
    output: Path, trial_id: str, agent_prompt: str,
    schema_style: str = "integer", *, max_tokens: int = 4000, thinking: bool | None = None,
) -> dict[str, Any]:
    thinking = variant != "no-thinking" if thinking is None else thinking
    case = make_case(seed, variant)
    images = []
    for key in ("previous", "png", "original"):
        data = case[key]
        if data is None:
            continue
        digest = hashlib.sha256(data).hexdigest()
        (output / f"{digest}.png").write_bytes(data)
        if key != "original":
            images.append(digest)
    protocol = variant.removeprefix("strict-").removeprefix("anyof-") if variant in {
        "bbox", "pixels", "strict-point", "strict-bbox", "anyof-point", "anyof-bbox",
    } else "point"
    schema_style = "anyof" if variant.startswith("anyof-") else schema_style
    kwargs = location_request(
        provider, model, case["png"], case["size"],
        "MISSING_BUTTON" if variant == "absent" else case["target"], protocol,
        strict=variant.startswith("strict-"), previous=case["previous"],
        nullable_style=schema_style,
        marked=variant == "marked", detail="low" if variant == "low-detail" else "auto",
        thinking=thinking, max_tokens=max_tokens,
        system=agent_prompt if variant in {"agent", "full-tools"} else
        "Locate the requested UI element in the current image.",
    )
    if variant == "full-tools":
        from tank_backend.tools.groups import ComputerUseToolGroup
        from tank_backend.tools.manager import ToolManager

        # Reuse production schema conversion without initializing/executing unrelated tools.
        manager = ToolManager.__new__(ToolManager)
        manager.tools = {tool.get_info().name: tool for tool in ComputerUseToolGroup().create_tools()}
        kwargs["tools"] += [tool for tool in manager.get_openai_tools()
                            if tool["function"]["name"] != "click"]
    row = {key: value for key, value in case.items() if key not in {"png", "previous", "original"}}
    row.update(id=trial_id, model=model, provider=provider, endpoint=str(client.base_url),
               seed=seed, variant=variant, protocol=protocol, images=images, schema_style=schema_style,
               thinking=thinking, max_tokens=max_tokens, schema_valid=False, hit=False)

    async def capture_request(request: httpx.Request) -> None:
        body = json.loads(request.content)
        actual = []
        for message in body["messages"]:
            if not isinstance(message.get("content"), list):
                continue
            for part in message["content"]:
                if part.get("type") != "image_url":
                    continue
                data = base64.b64decode(part["image_url"]["url"].split(",", 1)[1])
                digest = hashlib.sha256(data).hexdigest()
                actual.append(digest)
                part["image_url"]["url"] = f"sha256:{digest}"
        if actual != images or body["model"] != model:
            raise ValueError("HTTP image order/model differs from the bound trial")
        row["http_verified"] = True
        (output / f"{trial_id}.request.json").write_text(json.dumps(body, indent=2))

    async def capture_response(response: httpx.Response) -> None:
        raw = await response.aread()
        (output / f"{trial_id}.response.json.gz").write_bytes(gzip.compress(raw))
        row["http_status"] = response.status_code
        row["request_id"] = response.headers.get("x-request-id")

    client._client.event_hooks["request"] = [capture_request]
    client._client.event_hooks["response"] = [capture_response]
    start = time.monotonic()
    try:
        async with asyncio.timeout(90):
            result = await client.chat.completions.create(**kwargs)
        row["returned_model"] = result.model
        row["returned_provider"] = (result.model_extra or {}).get("provider")
        row["usage"] = result.usage.model_dump() if result.usage else None
        choice = result.choices[0]
        row["finish_reason"] = choice.finish_reason
        calls = choice.message.tool_calls or []
        if len(calls) != 1 or calls[0].type != "function" or calls[0].function.name != "click":
            raise ValueError("Expected exactly one click function call")
        raw = calls[0].function.arguments
        row["arguments"] = raw
        location = GroundingAdapter(protocol, schema_style).parse_response(result, case["size"])
        point = location.point
        if point is not None and case["crop"] is not None:
            ox, oy, width, height = case["crop"]
            point = (ox + point[0] * width / case["size"][0],
                     oy + point[1] * height / case["size"][1])
        row["schema_valid"] = True
        row["abstained"] = point is None
        if point is not None:
            row["point"] = point
            row.update(score_location(point, case["bounds"], case["radius"]))
            if variant == "absent":
                row["hit"] = False
        row["correct_abstention"] = variant == "absent" and point is None
    except (APIError, ValueError, TimeoutError, IndexError) as exc:
        row["error"] = type(exc).__name__ + ": " + str(exc)[:400]
    row["seconds"] = round(time.monotonic() - start, 2)
    return row


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--models", nargs="+", choices=MODELS, default=list(MODELS))
    parser.add_argument("--variants", nargs="+", choices=VARIANTS, default=["point"])
    parser.add_argument("--cases", type=int, default=4)
    parser.add_argument("--seed", type=int, default=101)
    parser.add_argument("--repeats", type=int, default=1)
    parser.add_argument("--max-tokens", type=int, default=4000,
                        help="Output budget, including reasoning where counted by the provider")
    parser.add_argument("--thinking", choices=["on", "off"],
                        help="Override thinking for every variant; default follows the variant")
    parser.add_argument("--schema-style", choices=["integer", "type-array", "anyof"],
                        default="integer")
    args = parser.parse_args()
    if args.max_tokens <= 0:
        parser.error("--max-tokens must be positive")
    args.output.mkdir(parents=True)
    load_dotenv(ROOT / "core/.env")
    profile = AppConfig.load(ROOT / "core/config.yaml").get_llm_profile("computer_use")
    endpoints = {
        "qwen": (profile.base_url, profile.api_key),
        "deepseek": ("https://api.deepseek.com", os.environ.get("DEEPSEEK_API_KEY", "")),
        "openrouter": ("https://openrouter.ai/api/v1", os.environ.get("OPENROUTER_API_KEY", "")),
    }
    prompt = (ROOT / "agents/computer_use.md").read_text().split("---", 2)[2].strip()
    report: dict[str, Any] = {"options": vars(args) | {"output": str(args.output)}, "results": []}
    semaphore = asyncio.Semaphore(2)

    async def run_model(alias: str) -> None:
        provider, model = MODELS[alias]
        endpoint, key = endpoints[provider]
        if not key:
            report["results"].append({"model": model, "error": "missing credential"})
            return
        async with AsyncOpenAI(api_key=key, base_url=endpoint, max_retries=0, timeout=85) as client:
            jobs = [(seed, variant, repeat) for seed in range(args.seed, args.seed + args.cases)
                    for variant in args.variants for repeat in range(args.repeats)]
            random.Random(47).shuffle(jobs)
            for seed, variant, repeat in jobs:
                # Strict DeepSeek is explicitly a beta-endpoint experiment.
                client.base_url = endpoint + ("/beta" if provider == "deepseek"
                                              and variant.startswith("strict-") else "")
                trial_id = f"{alias}-{seed}-{variant}-{repeat}"
                async with semaphore:
                    row = await run_trial(client, provider, model, seed, variant,
                                          args.output, trial_id, prompt, args.schema_style,
                                          max_tokens=args.max_tokens,
                                          thinking=None if args.thinking is None else args.thinking == "on")
                report["results"].append(row)
                (args.output / "results.json").write_text(json.dumps(report, indent=2))
                print(json.dumps({key: row[key] for key in (
                    "id", "schema_valid", "hit", "distance", "error", "seconds",
                ) if key in row}), flush=True)
                if row.get("http_status") in {401, 402, 403, 404}:
                    break

    await asyncio.gather(*(run_model(alias) for alias in args.models))
    (args.output / "results.json").write_text(json.dumps(report, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
