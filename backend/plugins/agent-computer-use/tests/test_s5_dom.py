"""S5 DOM paired pilot harness tests: H vs J on the current host, one ledger."""

import asyncio
import json
from pathlib import Path

import pytest

from .test_dom import chromium_required  # noqa: F401 — fixture registration


def _bootstrap(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).parents[3]))
    from benchmarks.computer_use import s5_dom

    return s5_dom


def test_freeze_pins_schedule_budget_and_arms(monkeypatch, tmp_path):
    s5 = _bootstrap(monkeypatch)
    frozen = s5.prepare(tmp_path / "pilot")
    assert frozen["revision"] == "s5-dom-1"
    assert len(frozen["schedule"]) == 48
    assert {entry["arm"] for entry in frozen["schedule"]} == {"H", "J"}
    # Arms differ only in the selector; the Advisor is shared.
    assert frozen["arm_configs"]["H"] == {"selector": "llm", "advisor": "llm"}
    assert frozen["arm_configs"]["J"] == {"selector": "jev-fallback", "advisor": "llm"}
    # 3 repeats x sum(2*(max_decisions+4) + max_decisions) over the 8 cases.
    assert frozen["request_limit"] == 273
    assert frozen["nano_usd_limit"] == 300_000_000
    assert frozen["decision_rule"]["interpretation"].startswith("descriptive")
    assert any(path.endswith("advisor.py") for path in frozen["source_sha256"])
    assert any(path.endswith("s3_strategy.py") for path in frozen["source_sha256"])
    assert s5.load_freeze(tmp_path / "pilot", frozen["sha256"]) == frozen
    with pytest.raises(ValueError, match="recipe changed"):
        s5.load_freeze(tmp_path / "pilot", "wrong")


def test_conclusion_uses_predeclared_policy_gates(monkeypatch):
    s5 = _bootstrap(monkeypatch)
    base = {
        "finished": 24,
        "accepted": 24,
        "unexpected_actions": 0,
        "jev_calls": 20,
        "selector_f_calls": 5,
        "elapsed_ms": 100,
        "nano_usd": 100,
    }
    assert s5.conclusion(
        {
            "H": {**base, "jev_calls": 0, "selector_f_calls": 20},
            "J": {**base, "elapsed_ms": 90},
        },
        True,
    ) == ("limited_policy_gain_not_adoption")
    assert s5.conclusion(
        {
            "H": {**base, "elapsed_ms": 100, "nano_usd": 50},
            "J": {**base, "elapsed_ms": 100, "nano_usd": 40, "selector_f_calls": 2},
        },
        True,
    ) == ("limited_policy_gain_not_adoption")
    equal = {"H": base, "J": {**base, "selector_f_calls": 20}}
    assert s5.conclusion(equal, True) == "no_net_gain_demonstrated_keep_disabled"
    assert s5.conclusion(equal, False) == "incomplete_no_policy_conclusion"
    quality = {"H": {**base, "accepted": 23}, "J": base}
    assert s5.conclusion(quality, True) == "quality_gate_failed_keep_disabled"


def _install_responder(monkeypatch, force_fallback=False):
    """One fake transport serving Jev, F-selector and Advisor request shapes."""
    import httpx

    calls = []

    async def respond(request):
        payload = json.loads(request.content)
        calls.append(payload)
        native = "questions" in payload
        q = payload if native else json.loads(payload["messages"][1]["content"])
        if native or "questions" in q:
            question = q["questions"]["next_action"]
            criteria = question["criteria"]
            objective = q["state"]["goal"]["objective"]
            target = next(
                (
                    label
                    for word, label in [
                        ("显示名称", "保存"),
                        ("紧凑", "紧凑视图"),
                        ("外观", "界面与显示"),
                        ("草稿", "保存进度"),
                        ("优惠", "取消营销订阅"),
                        ("收据", "查看支付凭证"),
                    ]
                    if word in objective
                ),
                None,
            )
            if target == "取消营销订阅" and any(
                f["key"] == "status:优惠邮件" and f["value"] == "off"
                for f in q["state"]["snapshot"]["facts"]
            ):
                target = "应用"
            if target is None or (native and force_fallback):
                choice = "none"
            else:
                ref = next(
                    e["ref"]
                    for e in q["state"]["snapshot"]["elements"]
                    if e["label"] == target
                )
                choice = next(
                    k
                    for k, v in criteria.items()
                    if isinstance(v, dict) and v["target_ref"] == ref
                )
            if native:
                return httpx.Response(
                    200,
                    json={
                        "model": "jev-1.13.0",
                        "answers": {
                            "next_action": {
                                "type": "choice",
                                "choice": choice,
                                "confidence": 1,
                                "probabilities": {
                                    k: int(k == choice) for k in criteria
                                },
                            }
                        },
                        "usage": {"input_tokens": 12, "output_tokens": 0},
                    },
                )
            assert payload["enable_thinking"] is False
            return httpx.Response(
                200,
                json={
                    "id": "f",
                    "object": "chat.completion",
                    "created": 1,
                    "model": "qwen3.7-flash-2026-07-15",
                    "choices": [
                        {
                            "index": 0,
                            "finish_reason": "stop",
                            "message": {
                                "role": "assistant",
                                "content": json.dumps({"choice": choice}),
                            },
                        }
                    ],
                    "usage": {
                        "prompt_tokens": 10,
                        "completion_tokens": 2,
                        "total_tokens": 12,
                    },
                },
            )
        # Advisor request: reason/state/actions without a choice question.
        target = next(
            (
                label
                for word, label in [
                    ("显示名称", "保存"),
                    ("紧凑", "紧凑视图"),
                    ("外观", "界面与显示"),
                    ("草稿", "保存进度"),
                    ("收据", "查看支付凭证"),
                ]
                if word in q["state"]["goal"]["objective"]
            ),
            None,
        )
        assert target is not None and q["actions"]
        choice = next(k for k, v in q["actions"].items() if v["label"] == target)
        return httpx.Response(
            200,
            json={
                "id": "advice",
                "object": "chat.completion",
                "created": 1,
                "model": "qwen3.7-flash-2026-07-15",
                "choices": [
                    {
                        "index": 0,
                        "finish_reason": "stop",
                        "message": {
                            "role": "assistant",
                            "content": json.dumps(
                                {"kind": "candidate", "candidate_id": choice}
                            ),
                        },
                    }
                ],
                "usage": {
                    "prompt_tokens": 10,
                    "completion_tokens": 3,
                    "total_tokens": 13,
                },
            },
        )

    class HTTP(httpx.AsyncBaseTransport):
        async def handle_async_request(self, request):
            return await respond(request)

    monkeypatch.setattr(httpx, "AsyncHTTPTransport", HTTP)
    return calls


@pytest.mark.parametrize("force_fallback", [False, True])
@pytest.mark.usefixtures("chromium_required")
async def test_s5_dom_pairs_governed_tasks_and_counts_selector_calls(
    monkeypatch, tmp_path, force_fallback
):
    s5 = _bootstrap(monkeypatch)
    _install_responder(monkeypatch, force_fallback)
    f = s5.prepare(tmp_path / "run")
    result = await s5.run_batch(
        tmp_path / "run", f["sha256"], {"jev": "fixture-j", "f": "fixture-f"}
    )
    assert result["completed"] and len(result["rows"]) == 48
    assert len(result["paired"]) == 24
    assert all(r["accepted"] and r["cleanup_confirmed"] for r in result["rows"])
    assert result["summary"]["H"]["selector_f_calls"] == 27
    assert result["summary"]["H"]["jev_calls"] == 0
    assert result["summary"]["J"]["jev_calls"] == 27
    assert result["summary"]["J"]["selector_f_calls"] == (27 if force_fallback else 6)
    assert result["summary"]["H"]["advisor_calls"] == 0
    assert result["conclusion"] in {
        "limited_policy_gain_not_adoption",
        "no_net_gain_demonstrated_keep_disabled",
        "incomplete_no_policy_conclusion",
    }
    with pytest.raises(FileExistsError):
        await s5.run_batch(tmp_path / "run", f["sha256"], {"jev": "j", "f": "f"})


@pytest.mark.parametrize("failure", ["unknown", "cancelled", "cleanup"])
@pytest.mark.usefixtures("chromium_required")
async def test_s5_dom_stops_operational_failures_with_full_denominator(
    monkeypatch, tmp_path, failure
):
    import httpx

    s5 = _bootstrap(monkeypatch)
    sent = []

    class HTTP(httpx.AsyncBaseTransport):
        async def handle_async_request(self, request):
            sent.append(request)
            if failure == "cancelled":
                raise asyncio.CancelledError
            return httpx.Response(503)

    monkeypatch.setattr(httpx, "AsyncHTTPTransport", HTTP)
    if failure == "cleanup":
        from agent_computer_use.channels import dom

        original_close = dom.ManagedChromiumChannel.aclose

        async def bad_close(self):
            await original_close(self)
            raise RuntimeError("reported close failure")

        monkeypatch.setattr(dom.ManagedChromiumChannel, "aclose", bad_close)
    f = s5.prepare(tmp_path / "run")
    if failure == "cancelled":
        with pytest.raises(asyncio.CancelledError):
            await s5.run_batch(tmp_path / "run", f["sha256"], {"jev": "j", "f": "f"})
        result = json.loads((tmp_path / "run/result.json").read_text())
    else:
        result = await s5.run_batch(
            tmp_path / "run", f["sha256"], {"jev": "j", "f": "f"}
        )
    assert not result["completed"] and len(result["rows"]) == 48
    assert result["conclusion"] == "incomplete_no_policy_conclusion"
    assert len((tmp_path / "run/rows.jsonl").read_text().splitlines()) == 48
    assert result["spend"]["stop_reason"]


async def test_s5_dom_freeze_rejects_drift_without_resources(monkeypatch, tmp_path):
    s5 = _bootstrap(monkeypatch)

    def forbidden(*args, **kwargs):
        raise AssertionError("unexpected resource creation")

    monkeypatch.setattr(asyncio, "start_server", forbidden)
    f = s5.prepare(tmp_path / "run")
    f["request_limit"] = 55
    f["sha256"] = s5.v1.digest({k: v for k, v in f.items() if k != "sha256"})
    (tmp_path / "run/freeze.json").write_text(json.dumps(f))
    with pytest.raises(ValueError, match="recipe changed"):
        await s5.run_batch(tmp_path / "run", f["sha256"], {"jev": "j", "f": "f"})
    assert not (tmp_path / "run/spend.jsonl").exists()
