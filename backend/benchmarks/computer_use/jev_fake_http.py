"""Explicit fake HTTP for both official SDKs; answers use public goal/actions only."""

from __future__ import annotations

import base64
import hashlib
import io
import json
import re
import socket
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any
from unittest.mock import patch

import httpx
import httpx2
from PIL import Image


def choose(packet: dict[str, Any]) -> str:
    offered = {
        key: value
        for key, value in packet["questions"]["next_action"]["criteria"].items()
        if isinstance(value, dict)
    }
    identity = packet["state"]["goal"]["outcomes"][0]["conditions"][0]["key"]
    target = identity.removeprefix("status:Editor seen:").rsplit("/", 1)[-1]
    predicates = (
        lambda v: v["label"] == "Retry",
        lambda v: v["operation"] == "fill",
        lambda v: (
            v["label"] == "Allow updating this column. [name=chk_title]"
            and v["current_value"] == "false"
        ),
        lambda v: v["role"] == "button" and v["label"] in ("Save", "Update"),
        lambda v: (
            v["label"] == "Edit"
            and (
                any(
                    kind == "row" and name.split()[0] == target
                    for kind, name in v["ancestors"]
                )
                or any(
                    re.search(
                        r"/bookmarks/" + re.escape(target) + r"/edit(?:\?|$)",
                        f["value"],
                    )
                    for f in v["effect"]
                )
            )
        ),
    )
    return next(
        (
            key
            for predicate in predicates
            for key, value in offered.items()
            if predicate(value)
        ),
        "none",
    )


def reply(payload: dict[str, Any]) -> dict[str, Any]:
    from benchmarks.computer_use.jev_vision_route import JEV, PEER

    visual = "messages" in payload
    packet = (
        json.loads(payload["messages"][1]["content"][0]["text"]) if visual else payload
    )
    selected = choose(packet)
    if visual:
        return {
            "id": "fixture",
            "object": "chat.completion",
            "created": 1,
            "model": PEER["model"],
            "choices": [
                {
                    "index": 0,
                    "finish_reason": "stop",
                    "message": {
                        "role": "assistant",
                        "content": json.dumps({"choice": selected}),
                    },
                }
            ],
            "usage": {"prompt_tokens": 7, "completion_tokens": 3, "total_tokens": 10},
        }
    return {
        "model": JEV["model"],
        "answers": {
            "next_action": {
                "type": "choice",
                "choice": selected,
                "confidence": 1,
                "probabilities": {
                    key: float(key == selected)
                    for key in packet["questions"]["next_action"]["criteria"]
                },
            }
        },
        "usage": {"input_tokens": 7, "output_tokens": 3},
    }


def _private(value: object) -> bool:
    if isinstance(value, dict):
        return bool({"oracle", "private_acceptance", "seed"} & value.keys()) or any(
            _private(v) for v in value.values()
        )
    return isinstance(value, list) and any(_private(v) for v in value)


@contextmanager
def offline_http(
    answer: Callable[[dict[str, Any]], dict[str, Any]], journal: Path
) -> Iterator[dict[str, Any]]:
    summary: dict[str, Any] = {
        "requests": [],
        "blocked_external": [],
        "active_trial": None,
    }
    original_init, original_connect = httpx.AsyncClient.__init__, socket.socket.connect
    original_resolve = socket.getaddrinfo
    with journal.open("x") as stream:

        def respond(content: bytes) -> dict[str, Any]:
            payload = json.loads(content)
            visual = "messages" in payload
            packet = (
                json.loads(payload["messages"][1]["content"][0]["text"])
                if visual
                else payload
            )
            if _private(packet):
                raise AssertionError("private oracle in SDK wire payload")
            images = []
            if visual:
                for message in payload["messages"]:
                    if isinstance(message.get("content"), list):
                        for part in message["content"]:
                            if part["type"] == "image_url":
                                png = base64.b64decode(
                                    part["image_url"]["url"].split(",", 1)[1],
                                    validate=True,
                                )
                                with Image.open(io.BytesIO(png)) as image:
                                    if image.format != "PNG" or image.size != (
                                        1280,
                                        720,
                                    ):
                                        raise AssertionError("unexpected bound image")
                                    image.verify()
                                images.append(hashlib.sha256(png).hexdigest())
                if len(images) != 1:
                    raise AssertionError("one bound PNG required")
            entry = {
                "trial_id": summary["active_trial"],
                "provider": "peer" if visual else "jev",
                "goal_id": packet["state"]["goal"]["goal_id"],
                "images": images,
                "request_sha256": hashlib.sha256(
                    json.dumps(
                        payload,
                        ensure_ascii=False,
                        sort_keys=True,
                        separators=(",", ":"),
                        allow_nan=False,
                    ).encode()
                ).hexdigest(),
                "usage": None,
            }
            summary["requests"].append(entry)
            try:
                response = answer(payload)
                entry["usage"] = response.get("usage")
                return response
            finally:
                stream.write(json.dumps(entry) + "\n")
                stream.flush()

        class Client(httpx2.AsyncClient):
            def __init__(self, *args, **kwargs):
                kwargs["transport"] = httpx2.MockTransport(
                    lambda request: httpx2.Response(200, json=respond(request.content))
                )
                super().__init__(*args, **kwargs)

        def initialize(client, *args, **kwargs):
            kwargs["transport"] = httpx.MockTransport(
                lambda request: httpx.Response(200, json=respond(request.content))
            )
            original_init(client, *args, **kwargs)

        def loopback_only(sock, address):
            if isinstance(address, tuple) and address[0] not in (
                "127.0.0.1",
                "::1",
                "localhost",
            ):
                summary["blocked_external"].append(str(address))
                raise AssertionError(
                    "external Python socket denied in fake qualification"
                )
            return original_connect(sock, address)

        def resolve(host, *args, **kwargs):
            if host not in (
                "127.0.0.1",
                "::1",
                "localhost",
                b"127.0.0.1",
                b"::1",
                b"localhost",
            ):
                summary["blocked_external"].append(str(host))
                raise AssertionError("external Python DNS denied in fake qualification")
            return original_resolve(host, *args, **kwargs)

        with (
            patch.object(httpx.AsyncClient, "__init__", initialize),
            patch.object(httpx2, "AsyncClient", Client),
            patch.object(socket.socket, "connect", loopback_only),
            patch.object(socket, "getaddrinfo", resolve),
        ):
            yield summary
