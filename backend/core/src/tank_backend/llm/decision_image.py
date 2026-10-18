"""Finite image decision request preparation, independent of SDK clients."""

from __future__ import annotations

import io
import json
from copy import deepcopy
from typing import cast

from PIL import Image
from typesafe_sdk import Choice, JSONContent

from .decision_profile import DecisionModelProfile
from .model_data import ModelDataScope, ModelImageAsset, ModelRequest

CARDINALITY = {
    "none": "No matching target is visible.",
    "one": "Exactly one matching target is visible.",
    "several": "Multiple matching targets are visible.",
}


def image_choice_questions(instructions: str, options: dict[str, object]) -> dict[str, object]:
    if (
        not isinstance(instructions, str)
        or not isinstance(options, dict)
        or not 1 <= len(options) <= 255
        or any(not isinstance(k, str) or not k.strip() or len(k) > 128 for k in options)
    ):
        raise ValueError("invalid_decision_image")
    # Reject SDK Image objects before its serializer can add undeclared file parts.
    try:
        json.dumps([instructions, options], allow_nan=False)
        question = Choice(instructions=instructions, criteria=cast(dict[str, JSONContent], options))
    except (TypeError, ValueError, UnicodeError, RecursionError):
        raise ValueError("invalid_decision_image") from None
    return {"next_action": question.model_dump(exclude_none=True)}


def box_questions(target: str) -> dict[str, object]:
    if not isinstance(target, str) or not target.strip() or len(target) > 4096:
        raise ValueError("a bounded target is required")
    return {
        "cardinality": {
            "type": "choice",
            "criteria": CARDINALITY,
            "instructions": f"How many targets matching {target!r} are visible in `image`?",
        },
        "target": {"type": "box", "instructions": f"Locate {target!r} in `image`."},
    }


def image_request(
    profile: DecisionModelProfile,
    state: dict[str, object],
    image: ModelImageAsset,
    questions: dict[str, object],
) -> ModelRequest:
    if not profile.images:
        raise ValueError("decision_images_denied")
    if (
        profile.model not in {"jev-1.13.0", "jev-1.14.0"}
        or image.part != "asset-0"
        or not isinstance(state, dict)
        or not isinstance(image.data, bytes)
        or not 0 < len(image.data) <= 16 * 1024 * 1024
    ):
        raise ValueError("invalid_decision_image")
    if "image" in state:
        raise ValueError("reserved image state fields")
    with Image.open(io.BytesIO(image.data)) as decoded:
        if (
            decoded.format not in {"PNG", "JPEG"}
            or getattr(decoded, "n_frames", 1) != 1
            or decoded.getexif().get(274, 1) != 1
            or not (280 <= decoded.width <= 1568 and 280 <= decoded.height <= 1568)
            or image.media_type != ("image/png" if decoded.format == "PNG" else "image/jpeg")
        ):
            raise ValueError("invalid_decision_image")
        decoded.load()
    parameters = {
        "model": profile.model,
        "state": {**deepcopy(state), "image": image.reference},
        "questions": deepcopy(questions),
        "assets": {image.reference: {"type": "image", "part": image.part}},
    }
    try:
        json.dumps(parameters, allow_nan=False)
    except (TypeError, ValueError, UnicodeError, RecursionError):
        raise ValueError("invalid_decision_image") from None
    request = ModelRequest(
        profile.url,
        profile.model,
        parameters,
        images=(image,),
        headers=(("TypeSafe-Danger-Zone-Images", "true"),),
    )
    ModelDataScope(frozenset({"text", "image"}), 32 * 1024 * 1024).check(request)
    return request
