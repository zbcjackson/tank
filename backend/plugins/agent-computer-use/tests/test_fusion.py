"""Fusion contract: OCR text is context, never a control; AX stays authoritative."""

import asyncio

from tank_backend.agents.subagent import (
    SubAgentAuthorization,
    SubAgentBudget,
    SubAgentContext,
)

from agent_computer_use.contracts import Element, Fact, Snapshot
from agent_computer_use.fusion import FusedObservationSource, fuse


def ax_snapshot(elements=(), facts=(), complete=True, generation=3):
    return Snapshot(
        "ax-obs",
        "app",
        generation,
        tuple(elements),
        tuple(facts),
        ready=True,
        complete=complete,
    )


def ocr_snapshot(elements=(), complete=True, ready=True, generation=2):
    return Snapshot(
        "ocr-obs",
        "app",
        generation,
        tuple(elements),
        (),
        ready=ready,
        complete=complete,
    )


def ocr_text(ref, text, bounds):
    return Element(
        ref,
        "text",
        text,
        (),
        kind="text_region",
        source="ocr",
        value=text,
        bounds=bounds,
    )


def ax_control(ref, label, bounds, value=""):
    return Element(
        ref, "button", label, ("click",), source="ax", value=value, bounds=bounds
    )


def test_contained_matching_text_is_deduplicated():
    ax = ax_snapshot(
        [ax_control("a1", "保存", (10, 10, 100, 40))],
        [Fact(key="ax:value:result", value="0")],
    )
    ocr = ocr_snapshot(
        [
            ocr_text("o1", "保存", (12, 12, 96, 36)),
            ocr_text("o2", "别的说明", (12, 12, 96, 36)),
        ]
    )
    fused = fuse(ax, ocr)
    labels = [(e.source, e.label) for e in fused.elements]
    assert labels == [("ax", "保存"), ("ocr", "别的说明")]
    assert fused.facts == ax.facts
    assert fused.complete and fused.ready


def test_same_text_elsewhere_is_kept_and_never_a_control():
    ax = ax_snapshot([ax_control("a1", "保存", (10, 10, 100, 40))])
    ocr = ocr_snapshot([ocr_text("o1", "保存", (200, 300, 60, 20))])
    fused = fuse(ax, ocr)
    assert [e.ref for e in fused.elements] == ["a1", "o1"]
    survivor = fused.elements[1]
    assert survivor.actions == () and survivor.kind == "text_region"
    assert fused.facts == ()


def test_ax_missing_bounds_disables_containment_dedup():
    ax = ax_snapshot([ax_control("a1", "保存", None)])
    ocr = ocr_snapshot([ocr_text("o1", "保存", (12, 12, 96, 36))])
    fused = fuse(ax, ocr)
    assert [e.ref for e in fused.elements] == ["a1", "o1"]


def test_completeness_and_readiness_propagate():
    assert fuse(ax_snapshot(complete=False), ocr_snapshot()).complete is False
    assert fuse(ax_snapshot(), ocr_snapshot(complete=False)).complete is False
    degraded = fuse(ax_snapshot(), ocr_snapshot(ready=False))
    assert degraded.ready and degraded.complete
    assert list(degraded.elements) == []


def test_fused_snapshot_mints_fresh_identity_and_bumps_generation():
    ax = ax_snapshot(generation=7)
    ocr = ocr_snapshot(generation=4)
    fused = fuse(ax, ocr)
    assert fused.observation_id not in {"ax-obs", "ocr-obs"}
    assert fused.generation == 8
    assert fused.scope == ax.scope and fused.window == ax.window


def test_unready_ocr_degrades_to_ax_elements_only():
    ax = ax_snapshot(
        [ax_control("a1", "保存", (10, 10, 100, 40))],
        [Fact(key="ax:value:result", value="0")],
    )
    ocr = ocr_snapshot([ocr_text("o1", "任意", (0, 0, 5, 5))], ready=False)
    fused = fuse(ax, ocr)
    assert [e.ref for e in fused.elements] == ["a1"]
    assert fused.facts == ax.facts
    assert fused.complete


class FakeAX:
    def __init__(self, snapshot):
        self.snapshot = snapshot
        self.calls = 0

    async def observe(self, scope, context):
        self.calls += 1
        return self.snapshot


class FakeOCR:
    def __init__(self, snapshot):
        self.snapshot = snapshot
        self.calls = 0

    async def observe(self, scope, context):
        self.calls += 1
        return self.snapshot


async def test_fused_source_runs_both_and_fuses():
    ax = ax_snapshot([ax_control("a1", "保存", (10, 10, 100, 40))])
    ocr = ocr_snapshot(
        [
            ocr_text("o1", "保存", (12, 12, 96, 36)),
            ocr_text("o2", "发票号码 123", (12, 60, 96, 20)),
        ]
    )
    ax_source, ocr_source = FakeAX(ax), FakeOCR(ocr)
    fused_source = FusedObservationSource(ax_source, ocr_source)
    context = SubAgentContext(
        SubAgentAuthorization(frozenset({"desktop"})), SubAgentBudget(), asyncio.Event()
    )
    fused = await fused_source.observe("app", context)
    assert ax_source.calls == 1 and ocr_source.calls == 1
    assert [e.ref for e in fused.elements] == ["a1", "o2"]
    assert fused.observation_id not in {"ax-obs", "ocr-obs"}
