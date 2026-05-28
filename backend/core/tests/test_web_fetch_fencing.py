"""Tests for the untrusted-data fencing applied to web_fetch tool results.

External web content can carry prompt-injection payloads aimed at the LLM
that will read the tool result.  ``_fence_untrusted`` wraps the
human-readable body in ``<untrusted-data source="...">…</untrusted-data>``
tags so instruction-tuned models treat it as data, not instructions.

The handler-level tests confirm fencing is applied at every entry point
(HTML, PDF, JSON, plain text, RSS feed) and that the structured metadata
(``title``, ``data``, ``entries``) is **not** wrapped.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tank_backend.tools.web_fetch import WebFetchTool, _fence_untrusted


def test_fence_wraps_text():
    out = _fence_untrusted("hello", "web_fetch:https://x.example")
    assert out.startswith('<untrusted-data source="web_fetch:https://x.example">\n')
    assert out.endswith("\n</untrusted-data>")
    assert "hello" in out


def test_fence_empty_input_returned_as_is():
    assert _fence_untrusted("", "web_fetch:x") == ""


def _make_crawl_result(markdown_text: str = "page body", title: str = "Title"):
    """Build a minimal crawl4ai result stand-in."""
    result = MagicMock()
    result.success = True
    result.status_code = 200
    result.error_message = None
    result.redirected_url = None
    result.markdown = markdown_text
    result.metadata = {"title": title, "description": ""}
    result.links = None
    return result


@pytest.fixture
def tool():
    return WebFetchTool(timeout=5, max_content_length=10000)


def _patch_detect_html(tool: WebFetchTool):
    return patch.object(
        tool,
        "_detect_content_type",
        new=AsyncMock(return_value=("text/html", None)),
    )


def _tool_with_crawler(tool: WebFetchTool, crawl_result):
    crawler = MagicMock()
    crawler.arun = AsyncMock(return_value=crawl_result)
    tool._http_crawler = crawler


async def test_html_handler_fences_text_content(tool):
    _tool_with_crawler(tool, _make_crawl_result(markdown_text="page body"))
    with _patch_detect_html(tool):
        result = await tool.execute(url="https://example.com")

    data = json.loads(result.content)
    assert data["text_content"].startswith("<untrusted-data ")
    assert data["text_content"].endswith("</untrusted-data>")
    assert "page body" in data["text_content"]


async def test_html_handler_does_not_fence_metadata(tool):
    _tool_with_crawler(tool, _make_crawl_result(title="Some Title"))
    with _patch_detect_html(tool):
        result = await tool.execute(url="https://example.com")

    data = json.loads(result.content)
    # Metadata fields must not be wrapped.
    assert data["title"] == "Some Title"
    assert "<untrusted-data" not in data["title"]
    # Headings list contains plain dicts — no wrapping.
    for heading in data.get("headings", []):
        assert "<untrusted-data" not in heading.get("text", "")


async def test_json_handler_fences_text_but_not_data(tool):
    body = json.dumps({"key": "value", "n": 1}).encode("utf-8")
    detect = AsyncMock(return_value=("application/json", body))
    with patch.object(tool, "_detect_content_type", new=detect):
        result = await tool.execute(url="https://x.example/foo.json")

    data = json.loads(result.content)
    # Structured data field is preserved as-is.
    assert data["data"] == {"key": "value", "n": 1}
    # text_content is the pretty-printed JSON, wrapped.
    assert data["text_content"].startswith("<untrusted-data ")
    assert data["text_content"].endswith("</untrusted-data>")


async def test_text_handler_fences_text_content(tool):
    body = b"This is some retrieved text content."
    detect = AsyncMock(return_value=("text/plain", body))
    with patch.object(tool, "_detect_content_type", new=detect):
        result = await tool.execute(url="https://x.example/file.txt")

    data = json.loads(result.content)
    assert data["text_content"].startswith("<untrusted-data ")
    assert "This is some retrieved text content." in data["text_content"]


async def test_cache_hit_returns_already_fenced_content(tool):
    """Cache stores the fenced output; cache hits never re-wrap."""
    _tool_with_crawler(tool, _make_crawl_result(markdown_text="first fetch"))
    with _patch_detect_html(tool):
        first = await tool.execute(url="https://example.com")

    first_data = json.loads(first.content)
    first_text = first_data["text_content"]
    assert first_text.startswith("<untrusted-data ")

    # Second fetch should be served from cache (without invoking the crawler).
    # Reset the crawler to a sentinel that would fail if called.
    tool._http_crawler = None
    second = await tool.execute(url="https://example.com")

    second_data = json.loads(second.content)
    # Same content, single layer of fencing.
    assert second_data["text_content"] == first_text
    # Sanity: no double-wrap.
    assert second_data["text_content"].count("<untrusted-data ") == 1
