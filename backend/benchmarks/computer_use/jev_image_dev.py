"""Prepare a new synthetic development set. No model executor or desktop access."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
from importlib.metadata import version
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw

from tank_backend.llm.decision_image import box_questions, image_request
from tank_backend.llm.decision_profile import DecisionModelProfile
from tank_backend.llm.model_data import ModelImageAsset

ROOT = Path(__file__).resolve().parents[2]
FAMILIES = (
    "structured",
    "missing-structure",
    "roundtrip",
    "recovery",
    "workflow",
    "absent",
    "ambiguous",
    "missing-input",
    "stale-frame",
)


def digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(
            value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode()
    ).hexdigest()


def sources() -> dict[str, str]:
    paths = [Path(__file__), ROOT / "core/pyproject.toml", ROOT / "uv.lock"]
    paths += [
        ROOT / "core/src/tank_backend/llm" / name
        for name in (
            "decision_model.py",
            "task_decision_model.py",
            "decision_image.py",
            "decision_profile.py",
            "model_call.py",
            "model_data.py",
        )
    ]
    paths += [ROOT / "plugins/agent-computer-use/src/agent_computer_use/jev_image.py"]
    paths += [ROOT / "core/src/tank_backend" / name for name in (
        "tools/computer_observation.py", "agents/subagent.py", "agents/task_runtime.py",
        "agents/runner.py")]
    paths += [ROOT / "plugins/agent-computer-use/src/agent_computer_use" / name for name in (
        "visual_selector.py", "channels/native.py", "channels/dom.py")]
    return {
        str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in paths
    }


def _scene(
    family: str, layout: str, number: int, target_label: str = "Save"
) -> tuple[bytes, list[dict[str, object]], dict[str, object]]:
    image = Image.new("RGB", (640, 360), "#f4f6f9")
    draw = ImageDraw.Draw(image)
    draw.text((20, 20), f"Controlled development fixture - step {number}", fill="black")
    rects = (
        ((60, 120, 240, 190), (350, 120, 530, 190))
        if layout == "toolbar"
        else ((220, 80, 400, 150), (220, 230, 400, 300))
    )
    if family == "recovery" and number == 2:
        rects = tuple((x1 + 20, y1 + 10, x2 + 20, y2 + 10) for x1, y1, x2, y2 in rects)
    target_slot = 0 if layout == "toolbar" else 1
    controls, target_boxes, expected = [], [], "none"
    for index, rect in enumerate(rects):
        target = index == target_slot and family != "absent" or family == "ambiguous"
        label = target_label if target else "Cancel"
        color = "#228b44" if target else "#a63838"
        draw.rounded_rectangle(rect, radius=8, fill=color)
        draw.text((rect[0] + 18, rect[1] + 24), label, fill="white")
        alias = f"c{index + 1}"
        if target:
            expected = alias
            # Independent clickable interior, excluding border and rounded corners.
            target_boxes.append(
                (rect[0] + 10, rect[1] + 10, rect[2] - 10, rect[3] - 10)
            )
        controls.append(
            {
                "id": alias,
                "role": "textbox" if target_label == "Name" and target else "button",
                "label": label if family in {"structured", "workflow"} else "",
                "bounds": rect,
            }
        )
    stream = io.BytesIO()
    image.save(stream, "PNG")
    if family == "ambiguous":
        expected = "ambiguous"
    return (
        stream.getvalue(),
        controls,
        {
            "expected_choice": expected,
            "expected_cardinality": (
                "none"
                if not target_boxes
                else "one"
                if len(target_boxes) == 1
                else "several"
            ),
            "clickable_regions": target_boxes,
        },
    )


def requests(stage: dict[str, Any], png: bytes) -> dict[str, object]:
    """Preview only: consume public fields/image bytes, never scoring labels."""
    if (
        stage["admission"] != "ready"
        or not stage.get("frame_valid", True)
        or any(
            item.get("value") is None and item.get("source") == "user"
            for item in stage.get("inputs", [])
        )
    ):
        return {}
    state = {"task": stage["instruction"], "snapshot": stage["snapshot"]}
    options = stage["options"]
    reference = "tank-image-" + hashlib.sha256(png).hexdigest()[:32]
    asset = ModelImageAsset(reference, "asset-0", "image/png", png)
    profile = DecisionModelProfile(
        "https://api.typesafe.ai/v1/systemone",
        "jev-1.14.0",
        "TYPESAFE_API_KEY",
        images=True,
    )
    questions: dict[str, object] = {
        "next_action": {
            "type": "choice",
            "instructions": stage["instruction"],
            "criteria": options,
        }
    }
    choice = image_request(profile, state, asset, questions)
    box = image_request(profile, state, asset, box_questions(stage["target"]))
    return {
        "text13": {"model": "jev-1.13.0", "state": state, "questions": questions},
        "text14": {"model": "jev-1.14.0", "state": state, "questions": questions},
        "image14": choice.parameters,
        "box14": box.parameters,
        "file_parts": [
            {
                "reference": reference,
                "part": asset.part,
                "media_type": asset.media_type,
                "size": len(png),
                "sha256": hashlib.sha256(png).hexdigest(),
            }
        ],
        "headers": dict(choice.headers),
        "compression": False,
    }


def prepare(output: Path) -> dict[str, Any]:
    output.mkdir(parents=True, exist_ok=False)
    (output / "images").mkdir()
    public, labels = [], {}
    for family in FAMILIES:
        for language in ("en", "zh"):
            for layout in ("toolbar", "table"):
                case_id = f"dev-{len(public) + 1:03}"
                kinds = (
                    ("structured", "missing-structure", "structured")
                    if family == "roundtrip"
                    else (
                        (family,) * 3
                        if family in {"recovery", "workflow"}
                        else (family,)
                    )
                )
                stages = []
                for number, kind in enumerate(kinds, 1):
                    stage_id = f"{case_id}-{number}"
                    target_label = (
                        ("Settings", "Name", "Save")[number - 1]
                        if family == "workflow"
                        else "Save"
                    )
                    png, controls, label = _scene(kind, layout, number, target_label)
                    if kind == "missing-structure":
                        label["expected_choice"] = "none"
                    image = f"images/{stage_id}.png"
                    (output / image).write_bytes(png)
                    labels[stage_id] = label
                    instruction = (
                        "Choose the green Save button; abstain if absent or non-unique."
                        if language == "en"
                        else "选择绿色的保存按钮；目标不存在或不唯一时弃权。"
                    )
                    if family == "workflow":
                        instruction = (
                            f"Open Settings, enter the supplied Name Ada, then Save. "
                            f"Current step: choose the green {target_label} control."
                            if language == "en"
                            else f"打开设置，将姓名设为用户提供的 Ada 后保存。当前选择绿色 {target_label} 控件。"
                        )
                    elif family == "missing-input":
                        instruction = (
                            "Enter the user's required Name before saving; the Name is missing."
                            if language == "en"
                            else "保存前输入用户姓名；用户尚未提供姓名，请询问。"
                        )
                    candidates = controls if kind != "missing-structure" else []
                    options: dict[str, object] = {
                        str(item["id"]): {
                            "description": "Offered control",
                            "bounds": item["bounds"],
                        }
                        for item in candidates
                    }
                    options.update(
                        {
                            "none": "No suitable offered action",
                            "ambiguous": "Non-unique target",
                        }
                    )
                    stages.append(
                        {
                            "id": stage_id,
                            "image": image,
                            "instruction": instruction,
                            "target": f"the green {target_label} control",
                            "options": options,
                            "inputs": [{"key": "name", "source": "user", "value": None}]
                            if family == "missing-input"
                            else [],
                            "frame_valid": family != "stale-frame",
                            "prior_dispatch_status": "not_sent"
                            if family == "recovery" and number == 2
                            else None,
                            "admission": "needs_input"
                            if family == "missing-input"
                            else ("stale" if family == "stale-frame" else "ready"),
                            "snapshot": {
                                "elements": candidates,
                                "scope": "synthetic-window",
                                "step": number,
                            },
                        }
                    )
                public.append(
                    {
                        "id": case_id,
                        "family": family,
                        "language": language,
                        "cluster": layout,
                        "stages": stages,
                    }
                )
    (output / "public.json").write_text(
        json.dumps(public, ensure_ascii=False, indent=2) + "\n"
    )
    (output / "labels.json").write_text(
        json.dumps(labels, ensure_ascii=False, indent=2) + "\n"
    )
    frozen = {
        "purpose": "development-only",
        "source_sha256": sources(),
        "versions": {name: version(name) for name in ("typesafe-sdk", "pillow")},
        "files": {
            str(path.relative_to(output)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted(output.rglob("*"))
            if path.is_file()
        },
        "case_count": len(public),
        "stage_count": len(labels),
        "confirmation": "not prepared; reserve independent applications/templates/layout families",
        "routing_strategies": {
            arm: "future controlled comparison" for arm in ("V", "JT", "JM", "JF")
        },
        "calibration": "not calibrated; no automatic image/Box dispatch",
        "prices": "not frozen",
    }
    frozen["sha256"] = digest(frozen)
    (output / "freeze.json").write_text(
        json.dumps(frozen, ensure_ascii=False, indent=2) + "\n"
    )
    return frozen


def load_freeze(output: Path, approved: str) -> dict[str, Any]:
    frozen = json.loads((output / "freeze.json").read_text())
    body = {key: value for key, value in frozen.items() if key != "sha256"}
    files = {
        str(path.relative_to(output)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(output.rglob("*"))
        if path.is_file() and path != output / "freeze.json"
    }
    if (
        frozen["sha256"] != approved
        or digest(body) != approved
        or frozen["source_sha256"] != sources()
        or files != frozen["files"]
        or frozen["versions"]
        != {name: version(name) for name in ("typesafe-sdk", "pillow")}
    ):
        raise ValueError("development freeze changed")
    return frozen


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    result = prepare(args.output)
    print(
        json.dumps(
            {key: result[key] for key in ("sha256", "case_count", "stage_count")},
            indent=2,
        )
    )
