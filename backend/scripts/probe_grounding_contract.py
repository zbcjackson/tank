"""Probe coordinate hypotheses using generated images only; no desktop input.

From backend: uv run python scripts/probe_grounding_contract.py --output /tmp/probe-new
"""
from __future__ import annotations

import argparse
import asyncio
import base64
import hashlib
import io
import json
import os
import time
from dataclasses import replace
from pathlib import Path
from typing import Any

os.environ["LANGFUSE_TRACING_ENABLED"] = "false"

from dotenv import load_dotenv
from PIL import Image, ImageDraw, ImageFont

from tank_backend.benchmarks.grounding_probe import response_point, score_point, text_response_point
from tank_backend.config.app_config import AppConfig
from tank_backend.core.content import ContentBlocks, ImageBlock, TextBlock
from tank_backend.llm.llm import _build_follow_up_user_message
from tank_backend.llm.profile import create_llm_from_profile
from tank_backend.tools.computer_use_common import COORDINATE_NOTE
from tank_backend.tools.computer_use_macos import ClickTool

ROOT = Path(__file__).resolve().parents[1]


def probe_messages(
    prompt: str, target: str, size: tuple[int, int], blocks: ContentBlocks,
    style: str, plain_json: bool,
) -> list[Any]:
    question = (f"Locate the Calculator button labeled {target}. Call click once "
                "at its center, using full-screen normalized coordinates. "
                "Do not call any other tool.")
    if style != "agent":
        prompt = "Locate the requested UI element in the image."
    if style == "formula":
        w, h = size
        question += (f" The full image is {w} pixels wide and {h} pixels high. "
                     f"Return x = 1000 * pixel_x / {w}, y = 1000 * pixel_y / {h}. "
                     "The origin is the top-left of the full image; both axes span 0 to 1000.")
    if plain_json:
        question = question.replace("Call click once at its center", "Return its center as JSON {\"x\": ..., \"y\": ...}")
        question = question.replace("Do not call any other tool.", "Return only JSON, without markdown.")
    if style == "bbox":
        question = (f"Locate the Calculator button labeled {target}. Return its bounding box "
                    'as JSON [{"bbox_2d": [x1, y1, x2, y2], "label": "' + target + '"}]. '
                    "Use full-screen normalized coordinates on both axes from 0 to 1000, "
                    "origin at the top-left. Return only JSON, without markdown.")
    return [{"role": "system", "content": prompt},
            {"role": "user", "content": question},
            _build_follow_up_user_message("probe", "screenshot", blocks)]


def scene(size: tuple[int, int], position: tuple[float, float]):
    image = Image.new("RGB", size, "#25272c")
    draw = ImageDraw.Draw(image)
    font_path = "/System/Library/Fonts/Supplemental/Arial.ttf"
    small = ImageFont.truetype(font_path, 13)
    for row in range(size[1] // 18):
        draw.text((3, row * 18), f"Synthetic calibration log {row:03d} generated background only",
                  font=small, fill="#cccccc")
    width = min(672, int(size[0] * .7))
    scale = width / 672
    height = round(407 * scale)
    left = round((size[0] - width) * position[0])
    top = round((size[1] - height) * position[1])
    draw.rounded_rectangle((left, top, left + width, top + height),
                           radius=round(22 * scale), fill="#302d31")
    font = ImageFont.truetype(font_path, round(24 * scale))
    draw.text((left + width - 52, top + 65 * scale), "35", font=font, fill="white")
    labels = [
        ["(", ")", "mc", "m+", "m-", "mr", "DEL", "AC", "%", "/"],
        ["2nd", "x2", "x3", "xy", "ex", "10x", "7", "8", "9", "x"],
        ["1/x", "sqrt", "cbrt", "root", "ln", "log", "4", "5", "6", "-"],
        ["x!", "sin", "cos", "tan", "e", "EE", "1", "2", "3", "+"],
        ["Rand", "sinh", "cosh", "tanh", "pi", "Rad", "+/-", "0", ".", "="],
    ]
    targets = {}
    for row, labels_row in enumerate(labels):
        for col, label in enumerate(labels_row):
            x = left + round((39 + 66 * col) * scale)
            y = top + round((156 + 54 * row) * scale)
            rx, ry = round(30 * scale), round(24 * scale)
            draw.rounded_rectangle((x-rx, y-ry, x+rx, y+ry), radius=round(22*scale),
                                   fill="#ee9900" if col == 9 else "#555257")
            draw.text((x, y), label, font=font, fill="white", anchor="mm")
            if label in ("AC", "7"):
                targets[label] = (x, y)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue(), targets


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--model", help="Override only the probe model; keep the configured provider")
    parser.add_argument("--repeats", type=int, default=2)
    parser.add_argument("--point-only", action="store_true",
                        help="Diagnostic control: advertise x/y only, without bbox/oneOf")
    parser.add_argument("--prompt-style", choices=["agent", "minimal", "formula", "bbox"], default="agent",
                        help="bbox uses native bbox_2d text output, without tools")
    parser.add_argument("--thinking", choices=["default", "on", "off"], default="default")
    parser.add_argument("--high-resolution", action="store_true")
    parser.add_argument("--plain-json", action="store_true")
    parser.add_argument("--case-set", choices=["all", "hard", "holdout"], default="all")
    args = parser.parse_args()
    if args.prompt_style == "bbox":
        args.plain_json = True
    args.output.mkdir(parents=True)
    load_dotenv(ROOT / "core/.env")
    profile = AppConfig.load(ROOT / "core/config.yaml").get_llm_profile("computer_use")
    if args.model:
        profile = replace(profile, model=args.model)
    llm = create_llm_from_profile(profile)
    llm.client.max_retries = 0
    llm.extra_body = dict(llm.extra_body)
    if args.thinking != "default":
        llm.extra_body["enable_thinking"] = args.thinking == "on"
    if args.high_resolution:
        llm.extra_body["vl_high_resolution_images"] = True
    prompt = (ROOT / "agents/computer_use.md").read_text().split("---", 2)[2].strip()
    tool = ClickTool()
    schema = {"type": "function", "function": {"name": "click",
              "description": tool.get_info().description, "parameters": tool.get_raw_schema()}}
    if args.point_only:
        schema["function"]["parameters"] = {
            "type": "object", "properties": {
                "x": {"type": "integer", "minimum": 0, "maximum": 1000},
                "y": {"type": "integer", "minimum": 0, "maximum": 1000},
            }, "required": ["x", "y"], "additionalProperties": False,
        }
    report = {"model": profile.model, "prompt": prompt, "schema": schema,
              "coordinate_note": COORDINATE_NOTE, "options": vars(args) | {"output": str(args.output)},
              "results": []}
    sizes = [(1920, 1080), (1280, 720), (1080, 1920), (1000, 1000)]
    positions = [(.1, .15), (.85, .8)]
    if args.case_set == "hard":
        sizes = sizes[:3]
    elif args.case_set == "holdout":
        sizes = [(1600, 900), (900, 1600)]
        positions = [(.3, .35), (.65, .6)]
    try:
        for size in sizes:
            for placement, position in enumerate(positions):
                if args.case_set == "hard" and placement == 0 and size != (1920, 1080):
                    continue
                png, targets = scene(size, position)
                name = f"{size[0]}x{size[1]}-{placement}.png"
                (args.output / name).write_bytes(png)
                digest = hashlib.sha256(png).hexdigest()
                blocks: ContentBlocks = [TextBlock(text=COORDINATE_NOTE), ImageBlock(
                    source="data:image/png;base64," + base64.b64encode(png).decode(),
                    mime_type="image/png")]
                for repeat in range(args.repeats):
                    for target, center in targets.items():
                        if args.case_set == "hard" and target != "7":
                            continue
                        messages = probe_messages(prompt, target, size, blocks, args.prompt_style, args.plain_json)
                        requests = []
                        async def on_request(request):
                            body = json.loads(request.content)
                            urls = [p["image_url"]["url"] for m in body["messages"]
                                    if isinstance(m.get("content"), list) for p in m["content"]
                                    if p.get("type") == "image_url"]
                            hashes = [hashlib.sha256(base64.b64decode(u.split(",", 1)[1])).hexdigest()
                                      for u in urls]
                            assert hashes == [digest]
                            requests.append({"sha256": hashes, "model": body["model"],
                                             "temperature": body.get("temperature"),
                                             "enable_thinking": body.get("enable_thinking"),
                                             "vl_high_resolution_images": body.get("vl_high_resolution_images"),
                                             "tools_present": "tools" in body})
                        llm.client._client.event_hooks["request"] = [on_request]
                        response_files = []
                        async def on_response(response):
                            # Buffer only this synthetic probe's response so the raw provider
                            # SSE can be replayed independently of the SDK/LLM accumulator.
                            path = args.output / f"{name}-{target}-{repeat}-{len(response_files)}.sse"
                            path.write_bytes(await response.aread())
                            response_files.append({"file": path.name, "status": response.status_code})
                        llm.client._client.event_hooks["response"] = [on_response]
                        row = {"image": name, "size": size, "target": target, "center": center,
                               "repeat": repeat, "sha256": digest, "question": messages[1]["content"],
                               "calls": [], "requests": requests, "responses": response_files,
                               "text": "", "thought_chars": 0}
                        started = time.monotonic()
                        try:
                            async with asyncio.timeout(60):
                                async for kind, content, meta in llm.chat_stream(
                                    messages, tools=None if args.plain_json else [schema], max_tokens=4000,
                                ):
                                    if kind.name == "TEXT":
                                        row["text"] += content
                                    if kind.name == "THOUGHT":
                                        row["thought_chars"] += len(content)
                                    if kind.name == "MESSAGE":
                                        for call in meta.get("message", {}).get("tool_calls", []):
                                            fn = call["function"]
                                            observed = {"name": fn["name"], "raw": fn["arguments"]}
                                            try:
                                                arguments = json.loads(fn["arguments"])
                                                point = response_point(arguments) if isinstance(arguments, dict) else None
                                            except json.JSONDecodeError:
                                                point = None
                                            if fn["name"] == "click" and point is not None:
                                                observed["point"] = point
                                                observed["errors"] = score_point(point, size, center)
                                            row["calls"].append(observed)
                                    if kind.name == "USAGE":
                                        row["usage"] = meta
                            if args.plain_json:
                                observed = {"name": "json", "raw": row["text"]}
                                point = text_response_point(row["text"], native_bbox=args.prompt_style == "bbox")
                                if point is not None:
                                    observed["point"] = point
                                    observed["errors"] = score_point(point, size, center)
                                row["calls"].append(observed)
                        except Exception as exc:
                            row["error"] = type(exc).__name__ + ": " + str(exc)[:200]
                        row["seconds"] = round(time.monotonic() - started, 2)
                        report["results"].append(row)
                        (args.output / "results.json").write_text(json.dumps(report, indent=2))
                        print(json.dumps(row), flush=True)
    finally:
        await llm.client.close()


if __name__ == "__main__":
    asyncio.run(main())
