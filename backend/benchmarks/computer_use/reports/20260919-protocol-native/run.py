"""Replay the same generated cases against DashScope's native multimodal API."""
import asyncio
import base64
import gzip
import hashlib
import json
import sys
from pathlib import Path

import httpx
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "scripts"))
from probe_grounding_matrix import make_case

from tank_backend.benchmarks.grounding_probe import (
    decode_location, location_request, qwen_native_request, score_location,
)
from tank_backend.config.app_config import AppConfig


async def main():
    load_dotenv(ROOT / "core/.env")
    profile = AppConfig.load(ROOT / "core/config.yaml").get_llm_profile("computer_use")
    endpoint = profile.base_url.split("/compatible-mode/")[0] + "/api/v1/services/aigc/multimodal-generation/generation"
    output = Path(__file__).parent
    report = {"endpoint": endpoint, "results": []}
    async with httpx.AsyncClient(timeout=90) as client:
        for model in ("qwen3.7-flash-2026-07-15", "qwen3.8-flash"):
            for seed in range(101, 105):
                case = make_case(seed, "point")
                request = qwen_native_request(location_request(
                    "qwen", model, case["png"], case["size"], case["target"], "point",
                    nullable_style="integer",
                ))
                digest = hashlib.sha256(case["png"]).hexdigest()
                for message in request["input"]["messages"]:
                    for part in message["content"]:
                        if "image" in part:
                            assert hashlib.sha256(base64.b64decode(part["image"].split(",")[1])).hexdigest() == digest
                name = f"{model}-{seed}"
                row = {"model": model, "seed": seed, "sha256": digest, "hit": False,
                       "schema_valid": False, "http_verified": True}
                response = await client.post(endpoint, json=request, headers={
                    "Authorization": f"Bearer {profile.api_key}",
                })
                (output / f"{name}.response.json.gz").write_bytes(gzip.compress(response.content))
                row["status"] = response.status_code
                data = response.json()
                row["request_id"] = data.get("request_id")
                row["usage"] = data.get("usage")
                try:
                    calls = data["output"]["choices"][0]["message"]["tool_calls"]
                    assert len(calls) == 1 and calls[0]["function"]["name"] == "click"
                    raw = calls[0]["function"]["arguments"]
                    row["arguments"] = raw
                    point = decode_location(raw, "point", case["size"], abstention_zero=True)
                    row["schema_valid"] = True
                    if point is not None:
                        row.update(score_location(point, case["bounds"], case["radius"]))
                except (KeyError, ValueError, AssertionError) as exc:
                    row["error"] = str(exc)
                for message in request["input"]["messages"]:
                    for part in message["content"]:
                        if "image" in part:
                            part["image"] = f"sha256:{digest}"
                (output / f"{name}.request.json").write_text(json.dumps(request, indent=2))
                report["results"].append(row)
                (output / "results.json").write_text(json.dumps(report, indent=2))
                print(json.dumps(row), flush=True)


asyncio.run(main())
