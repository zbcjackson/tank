"""Frozen synthetic holdout execution; never read truth or execute model actions."""
from __future__ import annotations

import argparse
import asyncio
import base64
import gzip
import hashlib
import json
import os
from dataclasses import asdict
from pathlib import Path
import sys
import time
from typing import Any

import httpx
from openai import AsyncOpenAI

from tank_backend.benchmarks.grounding_probe import HoldoutBudget
from tank_backend.llm.profile import LLMProfile, create_llm_from_profile
from tank_backend.tools.computer_grounding import GroundingAdapter
from tank_backend.tools.computer_observation import Observation


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def save(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=2) + "\n")


def load_frozen(freeze: Path, root: Path) -> tuple[dict, dict, list, dict]:
    """Check immutable evidence before requests; no truth files are opened."""
    manifest = json.loads((freeze / "manifest.json").read_text())
    for path, expected in manifest["source_sha256"].items():
        if sha((root / path).read_bytes()) != expected:
            raise ValueError(f"Frozen source changed: {path}")
    for name in ("requests", "schedule"):
        if sha((freeze / f"{name}.json").read_bytes()) != manifest[f"{name}_sha256"]:
            raise ValueError(f"Frozen {name} changed")
    inputs_path = root / manifest["holdout_inputs"]
    if sha(inputs_path.read_bytes()) != manifest["holdout_inputs_sha256"]:
        raise ValueError("Frozen inputs changed")
    if sha((inputs_path.parent / "generation.json").read_bytes()) != manifest["generation_record_sha256"]:
        raise ValueError("Frozen generation record changed")
    inputs = {row["id"]: row for row in json.loads(inputs_path.read_text())}
    for row in inputs.values():
        if set(row) != {"id", "image", "image_sha256", "size", "target"}:
            raise ValueError("Unexpected request-side metadata")
        path = (inputs_path.parent / row["image"]).resolve()
        if not path.is_relative_to(inputs_path.parent / "images") or sha(path.read_bytes()) != row["image_sha256"]:
            raise ValueError("Frozen image changed")
    requests = {row["id"]: row for row in json.loads((freeze / "requests.json").read_text())}
    schedule = json.loads((freeze / "schedule.json").read_text())
    for step in schedule:
        body = requests[step["request_id"]]
        digest = sha(json.dumps(body["body"], sort_keys=True, separators=(",", ":")).encode())
        if digest != step["body_sha256"] or digest != body["body_sha256"]:
            raise ValueError("Request hash mismatch")
    return manifest, requests, schedule, inputs


async def execute_holdout(
    freeze: Path, root: Path, output: Path, keys: dict[str, str],
    transport: httpx.AsyncBaseTransport | None = None,
    prices: dict[str, Any] | None = None,
) -> dict[str, Any]:
    manifest, requests, schedule, inputs = load_frozen(freeze, root)
    output.mkdir(exist_ok=False)
    if prices is not None:
        save(output / "prices.json", prices)
    candidates = {row["alias"]: row for row in manifest["candidates"]}
    data = (root / manifest["holdout_inputs"]).parent
    budget = HoldoutBudget(
        max_requests=manifest["holdout_caps"]["requests"], max_tokens=manifest["holdout_caps"]["total_token_stop"],
        reservation=manifest["next_call_reservation"], input_limit=manifest["input_token_reservation_per_call"],
    )
    rows: list[dict[str, Any]] = []
    started = time.monotonic()
    stop = None
    result: dict[str, Any] = {}
    save(output / "execution.json", {
        "freeze_manifest_sha256": sha((freeze / "manifest.json").read_bytes()),
        "driver_sha256": sha(Path(__file__).read_bytes()), "started_unix": time.time(),
        "mock_transport": transport is not None,
    })
    for step in schedule:
        if not budget.can_start():
            stop = budget.stop_reason or "request_or_token_budget"
            break
        remaining = manifest["batch_model_seconds_max"] - (time.monotonic() - started)
        if remaining <= 0:
            stop = "time_budget"
            break
        spec = candidates[step["candidate"]]
        entry = inputs[step["layout_id"]]
        png = (data / entry["image"]).read_bytes()
        observation, _ = Observation.capture(png, session_id="holdout", display_id=1)
        if observation.image_sha256 != entry["image_sha256"] or list(observation.image_size) != entry["size"]:
            raise ValueError("Bound image mismatch")
        row: dict[str, Any] = dict(step, http_attempts=0, schema_valid=False, usage=None)
        name = f"{step['attempt']:04d}"

        async def request_hook(request: httpx.Request) -> None:
            body = json.loads(request.content)
            content = body["messages"][1]["content"][1]["image_url"]
            raw = base64.b64decode(content["url"].split(",", 1)[1], validate=True)
            if raw != png:
                raise ValueError("Outbound image mismatch")
            content["url"] = "sha256:" + sha(raw)
            if body != requests[step["request_id"]]["body"]:
                raise ValueError("Actual SDK request differs from frozen body")
            if str(request.url) != spec["endpoint"] + "/chat/completions":
                raise ValueError("Endpoint mismatch")
            row["http_attempts"] += 1
            save(output / f"{name}.request.json", body)

        async def response_hook(response: httpx.Response) -> None:
            raw = await response.aread()
            (output / f"{name}.response.json.gz").write_bytes(gzip.compress(raw))
            row["http_status"] = response.status_code
            row["request_id_header"] = response.headers.get("x-request-id")

        profile = LLMProfile(
            name=spec["alias"], api_key=keys[spec["provider"]], model=spec["model"],
            base_url=spec["endpoint"], temperature=spec["temperature"],
            max_tokens=spec["max_tokens"], extra_body=spec["extra_body"],
        )
        llm = create_llm_from_profile(profile)
        await llm.client.close()
        cancelled = False
        call_start = time.monotonic()
        async with AsyncOpenAI(
            api_key=profile.api_key, base_url=profile.base_url, max_retries=0,
            timeout=manifest["http_timeout_seconds"], http_client=httpx.AsyncClient(
                transport=transport, event_hooks={"request": [request_hook], "response": [response_hook]},
            ),
        ) as client:
            llm.client = client
            adapter = GroundingAdapter(**spec["adapter"])
            try:
                async with asyncio.timeout(min(remaining, manifest["request_deadline_seconds"])):
                    response = await adapter.request(llm, observation, png, entry["target"])
                save(output / f"{name}.parsed-response.json", response.model_dump())
                row.update(
                    usage=response.usage.model_dump() if response.usage else None,
                    returned_model=response.model, returned_provider=(response.model_extra or {}).get("provider"),
                    finish_reasons=[c.finish_reason for c in response.choices],
                )
                try:
                    location = adapter.parse_response(response, observation.image_size)
                    row.update(schema_valid=True, point=location.point, box=location.box, status=location.status)
                except ValueError as exc:
                    row["parse_error"] = str(exc)
            except asyncio.CancelledError:
                cancelled = True
                row["error"] = "CancelledError"
            except Exception as exc:
                # Retain attempt/raw evidence, excluding exception text that may expose credentials.
                row["error"] = type(exc).__name__
        usage = row["usage"]
        stop = budget.record(usage["prompt_tokens"] if usage else None, usage["total_tokens"] if usage else None)
        row["seconds"] = round(time.monotonic() - call_start, 3)
        rows.append(row)
        result = {"results": rows, "budget": asdict(budget), "stop_reason": stop, "pending": len(schedule) - len(rows)}
        save(output / "results.json", result)
        print(json.dumps({"attempt": step["attempt"], "candidate": step["candidate"],
                          "known_tokens": budget.known_tokens, "stop": stop}), flush=True)
        if cancelled:
            raise asyncio.CancelledError
        if stop:
            break
    result.update(results=rows, budget=asdict(budget), stop_reason=stop, pending=len(schedule) - len(rows))
    save(output / "results.json", result)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--freeze", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--prices", type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    os.environ["LANGFUSE_TRACING_ENABLED"] = "false"
    manifest, _, _, _ = load_frozen(args.freeze, root)
    truth = (root / manifest["holdout_inputs"]).parent / "truth"

    def guard(event: str, values: tuple[Any, ...]) -> None:
        if event == "open" and isinstance(values[0], (str, bytes, os.PathLike)):
            if Path(os.fsdecode(values[0])).resolve().is_relative_to(truth):
                raise RuntimeError("Execution must not read scoring truth")

    sys.addaudithook(guard)
    prices = None
    if args.live:
        if args.prices is None:
            parser.error("--live requires a reviewed --prices manifest")
        prices = json.loads(args.prices.read_text())
        if prices["freeze_manifest_sha256"] != sha((args.freeze / "manifest.json").read_bytes()):
            raise ValueError("Prices belong to another freeze")
        from dotenv import load_dotenv
        from tank_backend.config.app_config import AppConfig

        load_dotenv(root / "backend/core/.env")
        qwen = AppConfig.load(root / "backend/core/config.yaml").get_llm_profile("computer_use")
        keys = {"qwen": qwen.api_key, "openrouter": os.environ.get("OPENROUTER_API_KEY", "")}
        if not all(keys.values()):
            raise ValueError("Missing credentials")
        transport = None
    else:
        keys = {"qwen": "offline-placeholder", "openrouter": "offline-placeholder"}

        def fake(request: httpx.Request) -> httpx.Response:
            body = json.loads(request.content)
            props = body["tools"][0]["function"]["parameters"]["properties"]
            arguments = {key: False if key == "found" else 0 for key in props}
            return httpx.Response(200, json={"id": "offline", "object": "chat.completion", "created": 1,
                "model": body["model"], "choices": [{"index": 0, "finish_reason": "tool_calls", "message": {
                    "role": "assistant", "tool_calls": [{"id": "one", "type": "function", "function": {
                        "name": "click", "arguments": json.dumps(arguments)}}]}}],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2}})

        transport = httpx.MockTransport(fake)
    asyncio.run(execute_holdout(args.freeze, root, args.output, keys, transport, prices))


if __name__ == "__main__":
    main()
