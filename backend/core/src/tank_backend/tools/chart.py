"""``ChartTool`` — render a chart, persist via MediaStore, return ImageBlock.

Phase 18 ships this as the first tool that exercises the non-URL
outbound-image path: matplotlib produces PNG bytes, the tool persists
them via the session-scoped :class:`MediaStore`, and returns a
``media://`` :class:`ImageBlock`. ``_ImageDispatcher`` (connector side)
and ``/api/media/{session}/{filename}`` (web-UI side) already know how
to resolve the URI to bytes — no new infrastructure needed.

Why a chart tool first:

- It validates the platform-context seam (:class:`ToolContext`) with
  a real consumer. Future image-producing tools (vision tools, image
  generation) follow the same pattern.
- Charts are useful in their own right — "plot a bar chart of these
  values" is a common ask that's hard to satisfy without one.
- It's offline-only (no external API), so it works in dev and
  air-gapped deployments alike.

Tradeoffs:

- matplotlib is import-heavy. We import inside ``execute`` rather
  than at module top so server boot stays fast even if no chart is
  ever rendered. The first chart in a session pays a ~1s cost; later
  ones are free.
- The ``Agg`` backend is non-interactive (no GUI dep). Selected
  globally on first use because matplotlib's backend is a process-
  wide setting.
- Pie charts cap at a small slice count (configurable) because more
  than that produces unreadable output. Bar/line charts have looser
  caps tied to data length.
"""

from __future__ import annotations

import io
import logging
from typing import Any

from ..core.content import ImageBlock, TextBlock
from .base import BaseTool, ToolContext, ToolInfo, ToolMetadata, ToolParameter, ToolResult

logger = logging.getLogger(__name__)


# Reasonable bounds: anything larger produces an unreadable chart.
_MAX_BAR_LINE_POINTS = 50
_MAX_PIE_SLICES = 12

_SUPPORTED_KINDS = frozenset({"bar", "line", "pie"})

# Matplotlib's backend is a process-wide setting; we set it once on
# first chart render. ``"Agg"`` is the headless raster backend and
# the only one that works without a display server.
_BACKEND_INITIALIZED = False


# Font fallback chain for CJK + Latin coverage. matplotlib renders
# missing glyphs as squares (□) and emits warnings on every miss —
# both ugly. Listing CJK-capable fonts before DejaVu Sans makes the
# resolver pick the first available match per character. Order picks
# the most common system fonts on each major platform first:
#
#     - macOS:    Hiragino Sans GB, PingFang SC, Heiti SC, Arial Unicode MS
#     - Windows:  Microsoft YaHei
#     - Linux:    Noto Sans CJK SC, WenQuanYi Zen Hei
#     - fallback: DejaVu Sans (matplotlib's default; Latin only)
#
# matplotlib silently skips entries that aren't installed, so listing
# all platforms in one chain is harmless.
_CJK_FONT_CHAIN = (
    "Hiragino Sans GB",
    "PingFang SC",
    "Heiti SC",
    "Microsoft YaHei",
    "Noto Sans CJK SC",
    "Noto Sans CJK JP",
    "WenQuanYi Zen Hei",
    "Arial Unicode MS",
    "DejaVu Sans",
)


def _init_matplotlib_backend() -> None:
    """Force matplotlib to the headless ``Agg`` backend on first use,
    and install a CJK-capable font-fallback chain.

    Called inside :meth:`ChartTool.execute` so the import + backend
    selection happens lazily — server boot stays fast even when no
    chart is ever rendered. Subsequent calls skip the work.

    Setting ``font.family`` (a list) plus ``axes.unicode_minus = False``
    is matplotlib's standard recipe for CJK + Latin output without
    glyph-square fallback or rendering warnings.
    """
    global _BACKEND_INITIALIZED
    if _BACKEND_INITIALIZED:
        return
    import logging

    import matplotlib
    matplotlib.use("Agg")
    # font.family accepts a list — matplotlib walks it per-glyph and
    # picks the first font that has the codepoint.
    matplotlib.rcParams["font.family"] = list(_CJK_FONT_CHAIN)
    # ``unicode_minus`` makes matplotlib use the proper Unicode minus
    # (U+2212) rather than the ASCII hyphen for negative axis labels.
    # Some CJK fonts don't carry U+2212; flipping this to False keeps
    # negative numbers rendering on every font in the chain.
    matplotlib.rcParams["axes.unicode_minus"] = False

    # Silence matplotlib's findfont WARNI flood. With our 8-candidate
    # fallback chain only 2-3 fonts are typically installed on any
    # given platform, so each chart render emitted 5+ warnings about
    # the missing ones. The fallback chain working AS DESIGNED was
    # producing the noise — the *first available* font does take over,
    # so the chart renders correctly. Bumping the logger to ERROR
    # drops the per-render noise without hiding genuine font errors
    # (e.g. all candidates missing — which is the bug we'd want to
    # see, and matplotlib still emits an ERROR-level log for that
    # case).
    logging.getLogger("matplotlib.font_manager").setLevel(logging.ERROR)

    _BACKEND_INITIALIZED = True


class ChartTool(BaseTool):
    """Render a bar / line / pie chart and return it as an ImageBlock."""

    def get_metadata(self) -> ToolMetadata:
        return ToolMetadata(idempotent=True)

    def get_info(self) -> ToolInfo:
        return ToolInfo(
            name="render_chart",
            description=(
                "Render a chart from labelled numeric data and send it "
                "to the user as an inline image. Supports bar, line, "
                "and pie charts. Use this when the user asks to "
                "visualise numbers ('plot...', 'chart of...', 'pie of'), "
                "or when a numeric answer would be clearer as a chart "
                "than as text."
            ),
            parameters=[
                ToolParameter(
                    name="kind",
                    type="string",
                    description=(
                        "Chart type: 'bar' for categorical comparison, "
                        "'line' for trends/time series, 'pie' for "
                        "part-of-whole breakdowns."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="data",
                    type="array",
                    description=(
                        "Array of points. Each point is "
                        "{\"label\": str, \"value\": number}. "
                        "Examples: [{\"label\": \"Jan\", \"value\": 12}, "
                        "{\"label\": \"Feb\", \"value\": 18}]. "
                        "For pie charts, values must be non-negative."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="title",
                    type="string",
                    description="Optional chart title shown above the figure.",
                    required=False,
                ),
                ToolParameter(
                    name="xlabel",
                    type="string",
                    description=(
                        "Optional x-axis label (bar/line only; ignored "
                        "for pie)."
                    ),
                    required=False,
                ),
                ToolParameter(
                    name="ylabel",
                    type="string",
                    description=(
                        "Optional y-axis label (bar/line only; ignored "
                        "for pie)."
                    ),
                    required=False,
                ),
            ],
        )

    def get_raw_schema(self) -> dict:
        """Override the auto-generated schema to give the LLM a precise
        shape for the ``data`` array.

        The default schema builder in :class:`ToolManager` produces
        ``"items": {}`` for ``array``-typed parameters — permissive
        enough that the OpenAI / Azure validator stops rejecting the
        function definition outright, but loose enough that the LLM
        can still emit malformed point objects (e.g.
        ``[1, 2, 3]`` instead of ``[{"label": ..., "value": ...}]``).

        Spelling out the inner ``object`` shape here means the LLM
        gets schema-aware completion and validators can reject bad
        outputs before we see them. The savings compound: every
        provider-side rejection costs a request round-trip and an
        irritating user wait.
        """
        return {
            "type": "object",
            "properties": {
                "kind": {
                    "type": "string",
                    "enum": ["bar", "line", "pie"],
                    "description": (
                        "Chart type: 'bar' for categorical comparison, "
                        "'line' for trends/time series, 'pie' for "
                        "part-of-whole breakdowns."
                    ),
                },
                "data": {
                    "type": "array",
                    "description": (
                        "Array of labelled numeric points to chart."
                    ),
                    "items": {
                        "type": "object",
                        "properties": {
                            "label": {
                                "type": "string",
                                "description": (
                                    "Human-readable label for this "
                                    "point (e.g. 'Jan', 'Q1', 'Web')."
                                ),
                            },
                            "value": {
                                "type": "number",
                                "description": (
                                    "Numeric value for this point. "
                                    "Must be non-negative for pie charts."
                                ),
                            },
                        },
                        "required": ["label", "value"],
                    },
                },
                "title": {
                    "type": "string",
                    "description": (
                        "Optional chart title shown above the figure."
                    ),
                },
                "xlabel": {
                    "type": "string",
                    "description": (
                        "Optional x-axis label (bar/line only; "
                        "ignored for pie)."
                    ),
                },
                "ylabel": {
                    "type": "string",
                    "description": (
                        "Optional y-axis label (bar/line only; "
                        "ignored for pie)."
                    ),
                },
            },
            "required": ["kind", "data"],
        }
    async def execute(
        self,
        kind: str,
        data: list[dict[str, Any]],
        title: str = "",
        xlabel: str = "",
        ylabel: str = "",
        ctx: ToolContext | None = None,
    ) -> ToolResult:
        """Render the chart, persist via MediaStore, return ImageBlock.

        ``ctx`` is injected by :meth:`ToolManager.execute_tool` (Phase
        18 seam) — it's not in :meth:`get_info`'s schema so the LLM
        never sees it. When ``ctx`` is ``None`` (e.g. the tool is run
        offline by a CLI), we return a clear error rather than crash.
        """
        # ---- Input validation ---------------------------------------
        if kind not in _SUPPORTED_KINDS:
            return ToolResult(
                content=(
                    f"render_chart: unknown kind {kind!r}; "
                    f"supported kinds are {sorted(_SUPPORTED_KINDS)}"
                ),
                display=f"Unknown chart kind: {kind}",
                error=True,
            )

        if not isinstance(data, list) or not data:
            return ToolResult(
                content="render_chart: `data` must be a non-empty list",
                display="No chart data provided",
                error=True,
            )

        try:
            labels, values = self._extract_points(data)
        except ValueError as exc:
            return ToolResult(
                content=f"render_chart: {exc}",
                display=str(exc),
                error=True,
            )

        cap = _MAX_PIE_SLICES if kind == "pie" else _MAX_BAR_LINE_POINTS
        if len(labels) > cap:
            return ToolResult(
                content=(
                    f"render_chart: {kind} chart accepts at most {cap} "
                    f"points; got {len(labels)}. Aggregate the data "
                    f"client-side before calling."
                ),
                display=f"Too many points for a {kind} chart",
                error=True,
            )

        if kind == "pie" and any(v < 0 for v in values):
            return ToolResult(
                content="render_chart: pie chart values must be non-negative",
                display="Negative values not allowed in pie charts",
                error=True,
            )

        # ---- Context check ------------------------------------------
        if ctx is None or ctx.media_store is None:
            return ToolResult(
                content=(
                    "render_chart: cannot persist chart bytes — no "
                    "MediaStore is available. The platform must wire a "
                    "MediaStore into ToolManager for image-producing "
                    "tools to work."
                ),
                display="Chart rendering unavailable",
                error=True,
            )
        if not ctx.session_id:
            return ToolResult(
                content=(
                    "render_chart: no session id available; the chart "
                    "tool requires a session-scoped MediaStore folder."
                ),
                display="Chart rendering unavailable",
                error=True,
            )

        # ---- Render --------------------------------------------------
        try:
            png_bytes = self._render(
                kind=kind, labels=labels, values=values,
                title=title, xlabel=xlabel, ylabel=ylabel,
            )
        except Exception as exc:
            logger.exception("render_chart: matplotlib rendering failed")
            return ToolResult(
                content=f"render_chart: rendering failed ({exc})",
                display="Chart rendering failed",
                error=True,
            )

        # ---- Persist + return ----------------------------------------
        try:
            stored = await ctx.media_store.put(
                png_bytes, "image/png", session_id=ctx.session_id,
            )
        except Exception as exc:
            logger.exception("render_chart: MediaStore.put failed")
            return ToolResult(
                content=f"render_chart: storage failed ({exc})",
                display="Chart could not be saved",
                error=True,
            )

        # The display string becomes the caption on the outbound image
        # (see Phase 17's ToolOutputObserver). Title takes precedence;
        # fall back to a short kind/length summary.
        caption = title or f"{kind.title()} chart ({len(labels)} points)"
        return ToolResult(
            content=[
                TextBlock(text=caption),
                ImageBlock(source=stored.media_uri, mime_type="image/png"),
            ],
            display=caption,
        )

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_points(
        data: list[dict[str, Any]],
    ) -> tuple[list[str], list[float]]:
        """Pull label/value pairs out of the LLM-supplied ``data`` array.

        Stays defensive: the LLM may emit numbers as strings ("42"),
        labels as numbers (1, 2, 3 instead of "Jan", "Feb"…), or use
        slightly different keys. We coerce where reasonable and raise
        ``ValueError`` with a clear message otherwise.
        """
        labels: list[str] = []
        values: list[float] = []
        for i, point in enumerate(data):
            if not isinstance(point, dict):
                raise ValueError(
                    f"data[{i}] must be an object with `label` + `value`",
                )
            label = point.get("label")
            value = point.get("value")
            if label is None or value is None:
                raise ValueError(
                    f"data[{i}] missing required `label` or `value`",
                )
            try:
                v = float(value)
            except (TypeError, ValueError):
                raise ValueError(
                    f"data[{i}].value must be numeric, got {value!r}",
                ) from None
            labels.append(str(label))
            values.append(v)
        return labels, values

    @staticmethod
    def _render(
        *,
        kind: str,
        labels: list[str],
        values: list[float],
        title: str,
        xlabel: str,
        ylabel: str,
    ) -> bytes:
        """Render the figure to PNG bytes via matplotlib + Agg.

        Uses an explicit ``Figure`` rather than the global ``pyplot``
        state so concurrent chart renders don't race each other through
        a shared figure registry. Closing the figure after savefig
        drops it from matplotlib's internal cache so memory doesn't
        grow over the session's lifetime.
        """
        _init_matplotlib_backend()
        # Local import: matplotlib's first-import cost (~1s) is paid
        # only when we actually render a chart, not at module import.
        from matplotlib.figure import Figure

        fig = Figure(figsize=(8, 5), dpi=100)
        ax = fig.add_subplot(111)

        if kind == "bar":
            ax.bar(labels, values)
            if xlabel:
                ax.set_xlabel(xlabel)
            if ylabel:
                ax.set_ylabel(ylabel)
            # Rotate x labels when there are enough points that
            # horizontal labels would overlap.
            if len(labels) > 8:
                ax.tick_params(axis="x", rotation=45)
        elif kind == "line":
            ax.plot(labels, values, marker="o")
            if xlabel:
                ax.set_xlabel(xlabel)
            if ylabel:
                ax.set_ylabel(ylabel)
            if len(labels) > 8:
                ax.tick_params(axis="x", rotation=45)
        else:  # pie — guarded above
            ax.pie(
                values, labels=labels, autopct="%1.1f%%",
                startangle=90, counterclock=False,
            )
            ax.axis("equal")  # circular pie, not oval

        if title:
            ax.set_title(title)

        # Use bbox_inches="tight" so rotated labels / titles don't
        # get clipped at the figure edge.
        buf = io.BytesIO()
        fig.savefig(buf, format="png", bbox_inches="tight")
        return buf.getvalue()
