"""Tests for content-type routing, JSON/text/binary/PDF handlers, and cache."""

import json
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tank_backend.tools.web_fetch import ResponseCache, WebFetchTool

# --- ResponseCache ---


class TestResponseCache:
    def test_put_and_get(self):
        cache = ResponseCache(max_size=10, ttl_seconds=60)
        cache.put("https://example.com", '{"data": 1}', "application/json")

        entry = cache.get("https://example.com")
        assert entry is not None
        assert entry.content == '{"data": 1}'
        assert entry.content_type == "application/json"

    def test_cache_miss(self):
        cache = ResponseCache()
        assert cache.get("https://example.com/missing") is None

    def test_ttl_expiration(self):
        cache = ResponseCache(ttl_seconds=1)
        cache.put("https://example.com", "data", "text/plain")

        # Manually expire
        key = cache._normalize_url("https://example.com")
        cache._cache[key].timestamp = time.time() - 2

        assert cache.get("https://example.com") is None

    def test_lru_eviction(self):
        cache = ResponseCache(max_size=2, ttl_seconds=60)
        cache.put("https://a.com", "a", "text/plain")
        cache.put("https://b.com", "b", "text/plain")
        cache.put("https://c.com", "c", "text/plain")  # evicts a.com

        assert cache.get("https://a.com") is None
        assert cache.get("https://b.com") is not None
        assert cache.get("https://c.com") is not None

    def test_url_normalization_strips_fragment(self):
        cache = ResponseCache()
        cache.put("https://example.com/page#section", "data", "text/html")

        # Should match without fragment
        entry = cache.get("https://example.com/page")
        assert entry is not None
        assert entry.content == "data"

    def test_url_normalization_case_insensitive(self):
        cache = ResponseCache()
        cache.put("https://Example.COM/Page", "data", "text/html")

        entry = cache.get("https://example.com/page")
        assert entry is not None

    def test_update_existing_key(self):
        cache = ResponseCache(max_size=2)
        cache.put("https://example.com", "old", "text/plain")
        cache.put("https://example.com", "new", "text/html")

        entry = cache.get("https://example.com")
        assert entry.content == "new"
        assert entry.content_type == "text/html"
        # Should not have evicted anything
        assert len(cache._cache) == 1


# --- Content-type detection ---


@pytest.fixture
def tool():
    return WebFetchTool(timeout=10, max_content_length=5000)


async def test_detect_content_type_html(tool):
    mock_resp = MagicMock()
    mock_resp.headers = {
        "Content-Type": "text/html; charset=utf-8",
        "Content-Length": "500",
    }
    mock_resp.read = AsyncMock(return_value=b"<html></html>")
    mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
    mock_resp.__aexit__ = AsyncMock()

    mock_session = MagicMock()
    mock_session.get = MagicMock(return_value=mock_resp)
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock()

    with patch("aiohttp.ClientSession", return_value=mock_session):
        ct, content = await tool._detect_content_type("https://example.com")

    assert ct == "text/html"
    assert content == b"<html></html>"


async def test_detect_content_type_large_response_no_prefetch(tool):
    mock_resp = MagicMock()
    mock_resp.headers = {
        "Content-Type": "application/pdf",
        "Content-Length": "5000000",  # 5MB
    }
    mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
    mock_resp.__aexit__ = AsyncMock()

    mock_session = MagicMock()
    mock_session.get = MagicMock(return_value=mock_resp)
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock()

    with patch("aiohttp.ClientSession", return_value=mock_session):
        ct, content = await tool._detect_content_type("https://example.com/big.pdf")

    assert ct == "application/pdf"
    assert content is None  # Too large to prefetch


# --- JSON handler ---


async def test_handle_json_with_prefetched_content(tool):
    content = b'{"name": "test", "value": 42}'
    result = await tool._handle_json("https://api.example.com/data", content)

    assert result.error is False
    data = json.loads(result.content)
    assert data["content_type"] == "application/json"
    assert data["data"] == {"name": "test", "value": 42}
    assert data["status"] == "success"
    assert "Fetched JSON" in result.display


async def test_handle_json_fetches_when_no_prefetch(tool):
    mock_resp = MagicMock()
    mock_resp.read = AsyncMock(return_value=b'[1, 2, 3]')
    mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
    mock_resp.__aexit__ = AsyncMock()

    mock_session = MagicMock()
    mock_session.get = MagicMock(return_value=mock_resp)
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock()

    with patch("aiohttp.ClientSession", return_value=mock_session):
        result = await tool._handle_json("https://api.example.com/data", None)

    assert result.error is False
    data = json.loads(result.content)
    assert data["data"] == [1, 2, 3]


async def test_handle_json_invalid(tool):
    result = await tool._handle_json("https://example.com/bad", b"not json {{{")

    assert result.error is True
    data = json.loads(result.content)
    assert "Invalid JSON" in data["error"]


# --- Text handler ---


async def test_handle_text_with_prefetched_content(tool):
    content = b"Hello, this is plain text content."
    result = await tool._handle_text("https://example.com/file.txt", content)

    assert result.error is False
    data = json.loads(result.content)
    assert data["content_type"] == "text/plain"
    assert data["text_content"] == "Hello, this is plain text content."
    assert data["status"] == "success"
    assert "Fetched text" in result.display


async def test_handle_text_truncation(tool):
    content = b"x" * 10000
    result = await tool._handle_text("https://example.com/big.txt", content)

    data = json.loads(result.content)
    assert data["text_content"].endswith("... [Content truncated]")


async def test_handle_text_utf8_errors(tool):
    content = b"Hello \xff\xfe world"
    result = await tool._handle_text("https://example.com/file.txt", content)

    assert result.error is False
    data = json.loads(result.content)
    # Should replace invalid bytes, not crash
    assert "Hello" in data["text_content"]
    assert "world" in data["text_content"]


# --- Binary handler ---


async def test_handle_binary_image(tool):
    mock_resp = MagicMock()
    mock_resp.headers = {"Content-Length": "12345"}
    mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
    mock_resp.__aexit__ = AsyncMock()

    mock_session = MagicMock()
    mock_session.head = MagicMock(return_value=mock_resp)
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock()

    with patch("aiohttp.ClientSession", return_value=mock_session):
        result = await tool._handle_binary("https://example.com/photo.jpg", "image/jpeg")

    assert result.error is False
    data = json.loads(result.content)
    assert data["content_type"] == "image/jpeg"
    assert data["size"] == "12345"
    assert "Binary content" in data["note"]
    assert "image/jpeg" in result.display


# --- Content-type routing in execute() ---


async def test_route_json(tool):
    """JSON content-type routes to JSON handler."""
    json_bytes = b'{"key": "value"}'

    with patch.object(
        tool, "_detect_content_type",
        return_value=("application/json", json_bytes),
    ):
        result = await tool.execute(url="https://api.example.com/data.json")

    assert result.error is False
    data = json.loads(result.content)
    assert data["content_type"] == "application/json"
    assert data["data"] == {"key": "value"}


async def test_route_plain_text(tool):
    """Plain text content-type routes to text handler."""
    text_bytes = b"Just some plain text."

    with patch.object(
        tool, "_detect_content_type",
        return_value=("text/plain", text_bytes),
    ):
        result = await tool.execute(url="https://example.com/file.txt")

    assert result.error is False
    data = json.loads(result.content)
    assert data["content_type"] == "text/plain"
    assert data["text_content"] == "Just some plain text."


async def test_route_csv(tool):
    """CSV content-type routes to text handler."""
    csv_bytes = b"name,age\nAlice,30\nBob,25"

    with patch.object(
        tool, "_detect_content_type",
        return_value=("text/csv", csv_bytes),
    ):
        result = await tool.execute(url="https://example.com/data.csv")

    assert result.error is False
    data = json.loads(result.content)
    assert "Alice,30" in data["text_content"]


async def test_route_javascript(tool):
    """JavaScript content-type routes to text handler."""
    js_bytes = b"function hello() { return 'world'; }"

    with patch.object(
        tool, "_detect_content_type",
        return_value=("application/javascript", js_bytes),
    ):
        result = await tool.execute(url="https://example.com/app.js")

    assert result.error is False
    data = json.loads(result.content)
    assert "function hello" in data["text_content"]


async def test_route_css(tool):
    """CSS content-type routes to text handler."""
    css_bytes = b"body { color: red; }"

    with patch.object(
        tool, "_detect_content_type",
        return_value=("text/css", css_bytes),
    ):
        result = await tool.execute(url="https://example.com/style.css")

    assert result.error is False
    data = json.loads(result.content)
    assert "body { color: red; }" in data["text_content"]


async def test_route_image_binary(tool):
    """Image content-type routes to binary handler."""
    mock_resp = MagicMock()
    mock_resp.headers = {"Content-Length": "99999"}
    mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
    mock_resp.__aexit__ = AsyncMock()

    mock_session = MagicMock()
    mock_session.head = MagicMock(return_value=mock_resp)
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock()

    with patch.object(
        tool, "_detect_content_type",
        return_value=("image/png", None),
    ), patch("aiohttp.ClientSession", return_value=mock_session):
        result = await tool.execute(url="https://example.com/logo.png")

    assert result.error is False
    data = json.loads(result.content)
    assert data["content_type"] == "image/png"
    assert data["size"] == "99999"


async def test_route_unknown_binary(tool):
    """Unknown content-type routes to binary handler."""
    mock_resp = MagicMock()
    mock_resp.headers = {"Content-Length": "1024"}
    mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
    mock_resp.__aexit__ = AsyncMock()

    mock_session = MagicMock()
    mock_session.head = MagicMock(return_value=mock_resp)
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock()

    with patch.object(
        tool, "_detect_content_type",
        return_value=("application/octet-stream", None),
    ), patch("aiohttp.ClientSession", return_value=mock_session):
        result = await tool.execute(url="https://example.com/file.bin")

    assert result.error is False
    data = json.loads(result.content)
    assert data["content_type"] == "application/octet-stream"


# --- Cache integration ---


async def test_cache_hit_skips_fetch(tool):
    """Second call to same URL returns cached result."""
    json_bytes = b'{"cached": true}'

    with patch.object(
        tool, "_detect_content_type",
        return_value=("application/json", json_bytes),
    ):
        result1 = await tool.execute(url="https://api.example.com/data")

    # Second call — should hit cache, no _detect_content_type call
    with patch.object(
        tool, "_detect_content_type",
        side_effect=AssertionError("should not be called"),
    ):
        result2 = await tool.execute(url="https://api.example.com/data")

    assert result1.content == result2.content
    assert "cache" in result2.display.lower()


async def test_cache_miss_after_different_url(tool):
    """Different URLs don't share cache entries."""
    with patch.object(
        tool, "_detect_content_type",
        return_value=("text/plain", b"first"),
    ):
        await tool.execute(url="https://example.com/a")

    with patch.object(
        tool, "_detect_content_type",
        return_value=("text/plain", b"second"),
    ):
        result = await tool.execute(url="https://example.com/b")

    data = json.loads(result.content)
    assert data["text_content"] == "second"


async def test_error_results_not_cached(tool):
    """Error results should not be cached."""
    with patch.object(
        tool, "_detect_content_type",
        side_effect=TimeoutError("timed out"),
    ):
        result1 = await tool.execute(url="https://example.com/slow")

    assert result1.error is True

    # Second call should still try to fetch (not cached)
    with patch.object(
        tool, "_detect_content_type",
        return_value=("text/plain", b"success"),
    ):
        result2 = await tool.execute(url="https://example.com/slow")

    assert result2.error is False
