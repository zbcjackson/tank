#!/usr/bin/env python3
"""Sync LiteLLM's model capability table into Tank's bundled registry.

Pulls ``model_prices_and_context_window.json`` from LiteLLM, filters to
fields Tank actually uses, and writes ``models.yaml`` that ships inside
the package. Run on-demand (monthly is plenty) or wire into CI.

The output is intentionally narrow — we keep only what maps to our
:class:`ModelCapabilities`, plus a few forward-looking fields (cost,
caching) that we'll light up later. Adding a field here is cheap; each
row stays a handful of lines.

Usage::

    uv run python backend/scripts/sync_litellm_models.py
    # or with a custom target path
    uv run python backend/scripts/sync_litellm_models.py --out path/to.yaml
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

UPSTREAM_URL = (
    "https://raw.githubusercontent.com/BerriAI/litellm/main/"
    "model_prices_and_context_window.json"
)

# We only care about rows that can act as a chat LLM.  LiteLLM also
# ships embedding/rerank/speech-to-text etc — filter them out.
_KEEP_MODES = {"chat", "completion", "responses"}

# Map LiteLLM's ``supports_*`` booleans to our modality vocabulary.
# Presence of a ``True`` here means the model accepts this modality as
# INPUT. Output modality is always text for chat-mode rows.
_MODALITY_FLAGS: list[tuple[str, str]] = [
    ("supports_vision", "image"),
    ("supports_image_input", "image"),
    ("supports_pdf_input", "file"),
    ("supports_audio_input", "audio"),
    ("supports_video_input", "video"),
]

# Fields we carry forward. Everything else in LiteLLM is dropped at
# bundle time — we can add fields by editing this list and re-running.
_COST_FIELDS = (
    "input_cost_per_token",
    "output_cost_per_token",
    "cache_read_input_token_cost",
    "cache_creation_input_token_cost",
)

logger = logging.getLogger("sync_litellm")


def fetch_upstream(url: str = UPSTREAM_URL) -> dict[str, Any]:
    """Download the raw LiteLLM capability table as a dict."""
    logger.info("Fetching %s", url)
    with urllib.request.urlopen(url, timeout=30) as resp:
        raw = resp.read()
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise RuntimeError(f"Unexpected payload shape: {type(data)}")
    return data


def _extract_modalities(entry: dict[str, Any]) -> list[str]:
    """Return the INPUT modalities for a row, lexical order.

    Three signals, any of which counts — LiteLLM is inconsistent:
      1. Explicit ``supported_modalities`` list (newer rows)
      2. ``supports_multimodal: true`` (older rows, conservative)
      3. Per-capability flags (``supports_vision`` etc)

    We always seed with "text"; a chat model that rejects text isn't
    a useful chat model.
    """
    mods: set[str] = {"text"}

    explicit = entry.get("supported_modalities")
    if isinstance(explicit, list):
        for m in explicit:
            if isinstance(m, str) and m in {"text", "image", "audio", "video"}:
                mods.add(m)

    for flag, modality in _MODALITY_FLAGS:
        if entry.get(flag) is True:
            mods.add(modality)

    return sorted(mods)


def transform_entry(
    model_id: str,
    entry: dict[str, Any],
) -> dict[str, Any] | None:
    """Project a LiteLLM row into Tank's schema.

    Returns ``None`` when the row isn't chat-capable (embeddings, TTS,
    image-gen, etc) — those are dropped from the bundle entirely.
    """
    mode = entry.get("mode")
    if mode not in _KEEP_MODES:
        return None

    out: dict[str, Any] = {
        "id": model_id,
        "provider": entry.get("litellm_provider", ""),
        "modalities": _extract_modalities(entry),
    }

    if (max_in := entry.get("max_input_tokens")) is not None:
        out["max_input_tokens"] = int(max_in)
    if (max_out := entry.get("max_output_tokens")) is not None:
        out["max_output_tokens"] = int(max_out)

    # Deprecation date — downstream can warn when pointing at a sunset model.
    if (dep := entry.get("deprecation_date")):
        out["deprecation_date"] = str(dep)

    # Optional capability flags we'll surface later (tool UX, UI badges).
    for flag in (
        "supports_function_calling",
        "supports_prompt_caching",
        "supports_reasoning",
    ):
        if entry.get(flag) is True:
            out.setdefault("flags", []).append(flag[len("supports_"):])

    # Cost — kept for future session-cost displays.
    costs: dict[str, Any] = {}
    for key in _COST_FIELDS:
        val = entry.get(key)
        if isinstance(val, (int, float)):
            costs[key] = val
    if costs:
        out["costs"] = costs

    return out


def build_bundle(
    raw: dict[str, Any],
) -> dict[str, Any]:
    """Project every row; skip the ``sample_spec`` docstring-row."""
    rows: list[dict[str, Any]] = []
    for model_id, entry in raw.items():
        if model_id == "sample_spec":
            continue
        if not isinstance(entry, dict):
            continue
        transformed = transform_entry(model_id, entry)
        if transformed is not None:
            rows.append(transformed)

    rows.sort(key=lambda r: r["id"])
    return {
        "$schema": "tank-model-registry-v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": "litellm/model_prices_and_context_window.json",
        "source_url": UPSTREAM_URL,
        "count": len(rows),
        "models": rows,
    }


def default_output_path() -> Path:
    """Location inside the package so installs pick it up automatically."""
    # scripts/sync_litellm_models.py → backend/scripts/ → up one, across to core/
    here = Path(__file__).resolve().parent
    return here.parent / "core/src/tank_backend/llm/data/models.yaml"


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description=__doc__ or "")
    parser.add_argument("--url", default=UPSTREAM_URL, help="Upstream LiteLLM JSON URL.")
    parser.add_argument(
        "--out",
        type=Path,
        default=default_output_path(),
        help="Destination YAML path.",
    )
    args = parser.parse_args(argv)

    try:
        raw = fetch_upstream(args.url)
    except Exception as exc:
        logger.error("Fetch failed: %s", exc)
        return 2

    bundle = build_bundle(raw)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", encoding="utf-8") as f:
        # sort_keys=False keeps our top-level order (schema, date, etc).
        yaml.safe_dump(bundle, f, sort_keys=False, allow_unicode=True)
    logger.info("Wrote %d models to %s", bundle["count"], args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
