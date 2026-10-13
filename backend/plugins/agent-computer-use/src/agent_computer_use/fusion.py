"""Deterministic AX+OCR snapshot fusion; OCR text is context, never a control."""

from __future__ import annotations

import re
from dataclasses import replace
from uuid import uuid4

from tank_backend.agents.subagent import SubAgentContext

from .contracts import Element, Snapshot
from .controller import ObservationSource

CONTAINMENT_MARGIN = 2.0
TEXT_OVERLAP = 0.6


def _tokens(text: str) -> set[str]:
    return set(re.findall(r"\w+", text.casefold()))


def _contained(
    inner: tuple[float, float, float, float], outer: tuple[float, float, float, float]
) -> bool:
    ix, iy, iw, ih = inner
    ox, oy, ow, oh = outer
    return (
        ix >= ox - CONTAINMENT_MARGIN
        and iy >= oy - CONTAINMENT_MARGIN
        and ix + iw <= ox + ow + CONTAINMENT_MARGIN
        and iy + ih <= oy + oh + CONTAINMENT_MARGIN
    )


def _duplicates(element: Element, tokens: set[str]) -> bool:
    ax_tokens = _tokens(element.label) | _tokens(element.value)
    if not ax_tokens or not tokens:
        return False
    return len(ax_tokens & tokens) / len(tokens) >= TEXT_OVERLAP


def fuse(ax: Snapshot, ocr: Snapshot) -> Snapshot:
    """Merge OCR text regions into the authoritative AX snapshot.

    OCR never contributes actions or facts. A region is dropped only when it is
    geometrically contained in an AX element whose label or value it duplicates;
    the same text elsewhere is separate information and survives. An unready
    OCR snapshot degrades to the AX observation alone. Both snapshots must
    already share one coordinate basis; fuse performs no conversion.
    """
    generation = max(ax.generation, ocr.generation) + 1
    if not ocr.ready:
        return replace(ax, observation_id=uuid4().hex, generation=generation)
    survivors = []
    for region in ocr.elements:
        tokens = _tokens(region.label) | _tokens(region.value)
        if not any(
            element.bounds is not None
            and region.bounds is not None
            and _contained(region.bounds, element.bounds)
            and _duplicates(element, tokens)
            for element in ax.elements
        ):
            survivors.append(region)
    return Snapshot(
        uuid4().hex,
        ax.scope,
        generation,
        (*ax.elements, *survivors),
        ax.facts,
        complete=ax.complete and ocr.complete,
        ready=ax.ready,
        window=ax.window,
    )


class FusedObservationSource:
    """Run the AX authority and an OCR supplement, then fuse deterministically."""

    def __init__(
        self, ax_source: ObservationSource, ocr_source: ObservationSource
    ) -> None:
        self.ax_source = ax_source
        self.ocr_source = ocr_source

    async def observe(self, scope: str, context: SubAgentContext) -> Snapshot:
        ax = await self.ax_source.observe(scope, context)
        ocr = await self.ocr_source.observe(scope, context)
        return fuse(ax, ocr)
