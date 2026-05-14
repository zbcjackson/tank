"""Unit tests for Phase 18: ChartTool.

Covers four concerns in one suite because ChartTool is the first
real consumer of every Phase 18 piece:

1. **Rendering** — bar/line/pie produce non-empty PNG bytes that
   parse as PNG (magic-bytes sniff) without spinning up an actual
   image library to verify content.

2. **MediaStore integration** — the tool persists via
   :meth:`MediaStore.put` with the right ``session_id``, returns an
   :class:`ImageBlock` whose ``source`` is the resulting ``media://``
   URI, and the bytes round-trip via :meth:`MediaStore.get`.

3. **Input validation** — bad ``kind``, empty data, bad point shape,
   negative pie values, oversized data all produce error
   ``ToolResult`` instances rather than crashing.

4. **ToolContext seam** — missing ``ctx`` or missing ``media_store``
   produces a clean error result instead of a silent crash.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from tank_backend.core.content import ImageBlock, TextBlock
from tank_backend.media.store import MediaStore
from tank_backend.tools.base import ToolContext
from tank_backend.tools.chart import ChartTool


@pytest.fixture()
def chart_ctx():
    """A real :class:`MediaStore` rooted in a temp directory paired
    with a :class:`ToolContext`. Each test gets a fresh tempdir so
    persisted PNGs from one test don't leak into another."""
    with tempfile.TemporaryDirectory() as tmp:
        store = MediaStore(Path(tmp))
        yield store, ToolContext(media_store=store, session_id="test-session")


# ---------------------------------------------------------------------------
# Rendering — happy path for each kind
# ---------------------------------------------------------------------------


def _is_png(data: bytes) -> bool:
    """Sniff PNG magic bytes — first 8 bytes are ``\\x89PNG\\r\\n\\x1a\\n``."""
    return data.startswith(b"\x89PNG\r\n\x1a\n")


class TestRendering:
    @pytest.mark.parametrize("kind", ["bar", "line", "pie"])
    async def test_kind_produces_png_imageblock(
        self, chart_ctx, kind: str,
    ) -> None:
        store, ctx = chart_ctx
        tool = ChartTool()

        result = await tool.execute(
            kind=kind,
            data=[
                {"label": "A", "value": 5},
                {"label": "B", "value": 12},
                {"label": "C", "value": 8},
            ],
            title=f"{kind} test",
            ctx=ctx,
        )

        assert not result.error
        # Two blocks: caption + image. The Phase 17 outbound observer
        # will use ``display`` as caption when it fires, so the
        # TextBlock is mostly for the LLM's view of the result.
        assert len(result.content) == 2
        text, image = result.content
        assert isinstance(text, TextBlock)
        assert isinstance(image, ImageBlock)
        assert image.source.startswith("media://test-session/")
        assert image.mime_type == "image/png"

        # Verify the persisted bytes are a real PNG by reading them
        # back through MediaStore.
        data, mime = await store.get(image.source, session_id="test-session")
        assert mime == "image/png"
        assert _is_png(data)

    async def test_title_becomes_display_caption(self, chart_ctx) -> None:
        """``display`` is what becomes the outbound caption (Phase 17
        ToolOutputObserver). Title is the natural caption when the
        user explicitly named the chart; it should win over the
        fallback summary."""
        _, ctx = chart_ctx
        result = await ChartTool().execute(
            kind="bar",
            data=[{"label": "x", "value": 1}],
            title="Revenue by quarter",
            ctx=ctx,
        )
        assert result.display == "Revenue by quarter"

    async def test_no_title_falls_back_to_kind_summary(
        self, chart_ctx,
    ) -> None:
        """When the LLM doesn't supply a title, we don't want a blank
        caption ('') because Phase 17's caption-or-None converter
        treats empty strings as no caption. Provide a useful summary
        so the user always sees *some* context above the image."""
        _, ctx = chart_ctx
        result = await ChartTool().execute(
            kind="line",
            data=[
                {"label": "A", "value": 1},
                {"label": "B", "value": 2},
            ],
            ctx=ctx,
        )
        assert "Line chart" in result.display
        assert "2 points" in result.display


# ---------------------------------------------------------------------------
# MediaStore integration — content-address dedup, session scoping
# ---------------------------------------------------------------------------


class TestMediaStoreIntegration:
    async def test_two_renders_same_data_dedupe_via_content_hash(
        self, chart_ctx,
    ) -> None:
        """``MediaStore.put`` is content-addressed (SHA-256 filename),
        so two renders with identical inputs produce the same
        ``media://`` URI. That's a free win for the chart tool: a user
        re-asking 'plot the same thing' doesn't fill the disk."""
        _, ctx = chart_ctx
        tool = ChartTool()
        data = [{"label": "A", "value": 1}, {"label": "B", "value": 2}]

        first = await tool.execute(kind="bar", data=data, ctx=ctx)
        second = await tool.execute(kind="bar", data=data, ctx=ctx)

        assert first.content[1].source == second.content[1].source

    async def test_different_sessions_get_separate_uris(
        self,
    ) -> None:
        """Even with identical content, two sessions get separate
        ``media://session/...`` paths because the URI prefix carries
        the session id. This is the security boundary backing the
        ``CrossSessionAccessError`` MediaStore raises on mismatched
        session reads — a chart rendered in session A is invisible to
        session B."""
        with tempfile.TemporaryDirectory() as tmp:
            store = MediaStore(Path(tmp))
            tool = ChartTool()
            data = [{"label": "A", "value": 1}]

            ctx_a = ToolContext(media_store=store, session_id="alice")
            ctx_b = ToolContext(media_store=store, session_id="bob")

            res_a = await tool.execute(kind="bar", data=data, ctx=ctx_a)
            res_b = await tool.execute(kind="bar", data=data, ctx=ctx_b)

            assert res_a.content[1].source.startswith("media://alice/")
            assert res_b.content[1].source.startswith("media://bob/")
            # Filenames (post-prefix) match because content is identical.
            file_a = res_a.content[1].source.rsplit("/", 1)[1]
            file_b = res_b.content[1].source.rsplit("/", 1)[1]
            assert file_a == file_b


# ---------------------------------------------------------------------------
# Input validation — every error path produces a clean ToolResult
# ---------------------------------------------------------------------------


class TestValidation:
    async def test_unknown_kind_returns_error(self, chart_ctx) -> None:
        _, ctx = chart_ctx
        result = await ChartTool().execute(
            kind="scatter", data=[{"label": "x", "value": 1}], ctx=ctx,
        )
        assert result.error is True
        assert "scatter" in result.content
        # ``display`` doesn't include implementation noise — it's what
        # the UI will show.
        assert "scatter" in result.display.lower() or "kind" in result.display.lower()

    async def test_empty_data_returns_error(self, chart_ctx) -> None:
        _, ctx = chart_ctx
        result = await ChartTool().execute(kind="bar", data=[], ctx=ctx)
        assert result.error is True

    async def test_data_not_a_list_returns_error(self, chart_ctx) -> None:
        """LLMs occasionally emit ``data`` as a dict ("with key=value")
        instead of an array. Handle that with a clear error rather
        than crashing on ``len(...)``."""
        _, ctx = chart_ctx
        result = await ChartTool().execute(
            kind="bar", data={"label": "x", "value": 1}, ctx=ctx,
        )
        assert result.error is True

    async def test_point_missing_label_returns_error(
        self, chart_ctx,
    ) -> None:
        _, ctx = chart_ctx
        result = await ChartTool().execute(
            kind="bar",
            data=[{"value": 1}],  # missing label
            ctx=ctx,
        )
        assert result.error is True
        assert "label" in result.content.lower()

    async def test_point_with_non_numeric_value_returns_error(
        self, chart_ctx,
    ) -> None:
        _, ctx = chart_ctx
        result = await ChartTool().execute(
            kind="bar",
            data=[{"label": "x", "value": "not a number"}],
            ctx=ctx,
        )
        assert result.error is True
        assert "numeric" in result.content.lower()

    async def test_string_numbers_coerced(self, chart_ctx) -> None:
        """LLMs sometimes emit numbers as strings (\"42\"). Coerce
        when possible so a perfectly valid request doesn't fail just
        because the JSON came through quoted."""
        _, ctx = chart_ctx
        result = await ChartTool().execute(
            kind="bar",
            data=[
                {"label": "A", "value": "10"},
                {"label": "B", "value": "20"},
            ],
            ctx=ctx,
        )
        assert not result.error

    async def test_pie_with_negative_value_returns_error(
        self, chart_ctx,
    ) -> None:
        """Pie slices represent part-of-whole; negatives don't make
        sense. Bar/line accept them."""
        _, ctx = chart_ctx
        result = await ChartTool().execute(
            kind="pie",
            data=[
                {"label": "A", "value": 5},
                {"label": "B", "value": -3},
            ],
            ctx=ctx,
        )
        assert result.error is True
        assert "non-negative" in result.content.lower()

    async def test_too_many_pie_slices_returns_error(
        self, chart_ctx,
    ) -> None:
        """Past ~12 slices the chart is unreadable; reject rather than
        produce nonsense the user can't make sense of."""
        _, ctx = chart_ctx
        result = await ChartTool().execute(
            kind="pie",
            data=[{"label": f"item-{i}", "value": i + 1} for i in range(20)],
            ctx=ctx,
        )
        assert result.error is True
        assert "12" in result.content or "too many" in result.content.lower()

    async def test_too_many_bar_points_returns_error(
        self, chart_ctx,
    ) -> None:
        _, ctx = chart_ctx
        result = await ChartTool().execute(
            kind="bar",
            data=[{"label": str(i), "value": i} for i in range(60)],
            ctx=ctx,
        )
        assert result.error is True


# ---------------------------------------------------------------------------
# ToolContext seam — graceful degradation when context is missing
# ---------------------------------------------------------------------------


class TestContextSeam:
    async def test_missing_ctx_returns_error(self) -> None:
        """When the chart tool runs outside a ToolManager that knows
        about ToolContext (e.g. a future direct CLI invocation), the
        tool returns a clear error rather than crashing on
        ``ctx.media_store``."""
        result = await ChartTool().execute(
            kind="bar", data=[{"label": "x", "value": 1}],
            # ctx omitted entirely
        )
        assert result.error is True
        assert "MediaStore" in result.content

    async def test_ctx_with_no_media_store_returns_error(self) -> None:
        result = await ChartTool().execute(
            kind="bar", data=[{"label": "x", "value": 1}],
            ctx=ToolContext(media_store=None, session_id="x"),
        )
        assert result.error is True
        assert "MediaStore" in result.content

    async def test_ctx_with_no_session_id_returns_error(
        self, chart_ctx,
    ) -> None:
        store, _ = chart_ctx
        result = await ChartTool().execute(
            kind="bar", data=[{"label": "x", "value": 1}],
            ctx=ToolContext(media_store=store, session_id=None),
        )
        assert result.error is True
        assert "session" in result.content.lower()


# ---------------------------------------------------------------------------
# Schema — LLM never sees ``ctx``
# ---------------------------------------------------------------------------


class TestSchema:
    def test_ctx_is_not_in_openai_schema(self) -> None:
        """The reserved ``ctx`` kwarg must NOT appear in the tool's
        OpenAI parameter schema — the LLM should never see it. This
        regression-guards the Phase 18 seam contract."""
        info = ChartTool().get_info()
        param_names = {p.name for p in info.parameters}
        assert "ctx" not in param_names
        # Sanity: actual user-facing params are present.
        assert "kind" in param_names
        assert "data" in param_names

    def test_raw_schema_data_array_has_items(self) -> None:
        """Regression: Azure/OpenAI rejected the chart tool because
        the auto-generated schema produced ``"data": {"type": "array"}``
        without an ``items`` key. The error was

            Invalid schema for function 'render_chart': In context=
            ('properties', 'data'), array schema missing items.

        ChartTool now overrides ``get_raw_schema`` with a precise
        inner-object shape; this test pins it so a future refactor
        doesn't accidentally drop ``items`` again. Without this fix,
        the *whole tools list* gets rejected on every LLM call —
        meaning it doesn't just break charts, it breaks every other
        tool the user can call too."""
        schema = ChartTool().get_raw_schema()

        # Top-level shape: object with required kind+data.
        assert schema["type"] == "object"
        assert set(schema["required"]) == {"kind", "data"}

        # The ``data`` array must declare what its elements look like.
        data_schema = schema["properties"]["data"]
        assert data_schema["type"] == "array"
        assert "items" in data_schema, (
            "data is an array; OpenAI/Azure validators reject array "
            "schemas without an ``items`` declaration"
        )

        # Inner element shape lets the LLM produce well-formed points
        # the first time, instead of guessing and getting validated
        # by the tool's own _extract_points fallback.
        item_schema = data_schema["items"]
        assert item_schema["type"] == "object"
        item_props = item_schema["properties"]
        assert item_props["label"]["type"] == "string"
        assert item_props["value"]["type"] == "number"
        assert set(item_schema["required"]) == {"label", "value"}

    def test_kind_param_is_constrained_enum(self) -> None:
        """``kind`` is enum-constrained to bar/line/pie so the LLM can
        only emit values the tool actually handles. Saves a round-trip
        on misspellings ('barchart', 'scatter')."""
        schema = ChartTool().get_raw_schema()
        assert set(schema["properties"]["kind"]["enum"]) == {"bar", "line", "pie"}



# ---------------------------------------------------------------------------
# CJK glyph regression — Phase 18 follow-up
# ---------------------------------------------------------------------------


class TestCJKRendering:
    """Regression for the squares-instead-of-Chinese-characters bug.

    Live test: when the LLM emitted Chinese labels (e.g. ``第一季度``),
    matplotlib's default ``DejaVu Sans`` lacked the glyphs and rendered
    squares plus warning lines. The fix configured a font-fallback
    chain in ``_init_matplotlib_backend`` covering common CJK fonts
    on macOS / Windows / Linux. These tests pin both the configuration
    and the rendering outcome so a future refactor doesn't lose the
    fix.
    """

    def test_font_chain_lists_cjk_capable_fonts_first(self) -> None:
        """The chain must start with CJK-capable fonts; ``DejaVu Sans``
        is the last-resort fallback."""
        from tank_backend.tools.chart import _CJK_FONT_CHAIN

        # Last entry is the matplotlib default — anything before it
        # is a CJK-capable font we want preferred.
        assert _CJK_FONT_CHAIN[-1] == "DejaVu Sans"
        # At minimum we list one font from each of the major
        # platforms — defensive against future imports that strip
        # one and re-trigger the bug on that platform.
        assert "PingFang SC" in _CJK_FONT_CHAIN          # macOS
        assert "Microsoft YaHei" in _CJK_FONT_CHAIN      # Windows
        assert "Noto Sans CJK SC" in _CJK_FONT_CHAIN     # Linux

    def test_chinese_labels_render_without_glyph_warnings(self) -> None:
        """End-to-end: matplotlib's font configuration is set up so
        Chinese labels resolve through the CJK chain rather than
        falling back to glyph-square placeholders.

        ``warnings.catch_warnings`` doesn't capture matplotlib's
        ``findfont`` / glyph-missing warnings (those go to stderr via
        the ``matplotlib`` logger, not the warnings module). The
        observable signal is that ``font.family`` is set to the CJK
        chain at render time and ``axes.unicode_minus`` is disabled —
        without those, glyph squares are guaranteed.
        """
        import matplotlib

        from tank_backend.tools.chart import _init_matplotlib_backend
        _init_matplotlib_backend()

        family = matplotlib.rcParams["font.family"]
        assert "PingFang SC" in family
        assert "DejaVu Sans" in family  # last-resort fallback
        # PingFang SC ranks before DejaVu Sans so the per-glyph
        # resolver picks it for CJK characters.
        assert family.index("PingFang SC") < family.index("DejaVu Sans")
        assert matplotlib.rcParams["axes.unicode_minus"] is False

    async def test_cjk_chart_round_trips_through_mediastore(
        self, chart_ctx,
    ) -> None:
        """The full path: render Chinese-labelled chart, persist via
        MediaStore, fetch the bytes back. Confirms the font fix
        doesn't break the persistence path."""
        store, ctx = chart_ctx

        result = await ChartTool().execute(
            kind="bar",
            data=[
                {"label": "第一季度", "value": 12},
                {"label": "第二季度", "value": 18},
            ],
            title="销售数据",
            ctx=ctx,
        )
        assert not result.error

        image_block = result.content[1]
        data, mime = await store.get(image_block.source, session_id=ctx.session_id)
        assert mime == "image/png"
        # PNG header sniff — we don't assert on byte count because
        # font + label content vary by platform.
        assert data.startswith(b"\x89PNG\r\n\x1a\n")
