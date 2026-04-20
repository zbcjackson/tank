import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tank_backend.tools.web_fetch import WebFetchTool

MODULE = "tank_backend.tools.web_fetch"


@pytest.fixture
def tool():
    return WebFetchTool(timeout=10, max_content_length=500)


_SENTINEL = object()


def _make_crawl_result(
    success=True,
    url="https://example.com",
    markdown_text="# Hello\n\nSome content here.",
    metadata=_SENTINEL,
    links=_SENTINEL,
    status_code=200,
    error_message=None,
    redirected_url=None,
):
    result = MagicMock()
    result.success = success
    result.url = url
    result.status_code = status_code
    result.error_message = error_message
    result.redirected_url = redirected_url
    result.metadata = (
        {"title": "Test Page", "description": "A test page"} if metadata is _SENTINEL else metadata
    )
    result.links = {"internal": [], "external": []} if links is _SENTINEL else links
    result.markdown = markdown_text
    return result


def _mock_crawler(crawl_result=None):
    """Create a mock crawler with optional pre-configured arun result."""
    crawler = AsyncMock()
    crawler.start = AsyncMock()
    crawler.close = AsyncMock()
    if crawl_result is not None:
        crawler.arun = AsyncMock(return_value=crawl_result)
    return crawler


def _tool_with_crawler(tool, crawl_result=None, **arun_kwargs):
    """Inject a mock HTTP crawler into the tool, return the mock crawler."""
    mock = _mock_crawler(crawl_result)
    if arun_kwargs:
        mock.arun = AsyncMock(**arun_kwargs)
    tool._http_crawler = mock
    return mock


def _patch_detect_html(tool):
    """Patch _detect_content_type to return text/html."""
    return patch.object(
        tool, "_detect_content_type",
        return_value=("text/html", None),
    )


# --- get_info ---


def test_get_info():
    tool = WebFetchTool()
    info = tool.get_info()
    assert info.name == "web_fetch"
    param_names = [p.name for p in info.parameters]
    assert "url" in param_names
    assert "extract_links" in param_names
    assert "use_browser" in param_names

    url_param = next(p for p in info.parameters if p.name == "url")
    assert url_param.required is True

    browser_param = next(p for p in info.parameters if p.name == "use_browser")
    assert browser_param.required is False
    assert browser_param.default is False


# --- URL validation ---


async def test_invalid_url_no_scheme(tool):
    result = await tool.execute(url="not-a-url")
    assert result.error is True
    data = json.loads(result.content)
    assert "Invalid URL" in data["error"]
    assert "无法访问URL" in result.display


async def test_invalid_url_no_netloc(tool):
    result = await tool.execute(url="http://")
    assert result.error is True
    data = json.loads(result.content)
    assert "Invalid URL" in data["error"]


async def test_unsupported_scheme(tool):
    result = await tool.execute(url="ftp://example.com/file")
    assert result.error is True
    data = json.loads(result.content)
    assert "Only HTTP and HTTPS" in data["error"]
    assert "仅支持HTTP和HTTPS" in result.display


# --- Successful HTML fetch ---


async def test_successful_scrape(tool):
    crawl_result = _make_crawl_result(
        markdown_text="# Hello World\n\nThis is a test page with content.",
        metadata={"title": "Hello World", "description": "A test page"},
    )
    _tool_with_crawler(tool, crawl_result)

    with _patch_detect_html(tool):
        result = await tool.execute(url="https://example.com")

    assert result.error is False
    data = json.loads(result.content)
    assert data["status"] == "success"
    assert data["title"] == "Hello World"
    assert data["meta_description"] == "A test page"
    assert "# Hello World" in data["text_content"]
    assert "This is a test page" in data["text_content"]
    assert data["headings"] == [{"level": "h1", "text": "Hello World"}]
    assert "links" not in data


async def test_successful_scrape_with_links(tool):
    crawl_result = _make_crawl_result(
        links={
            "internal": [
                {"href": "https://example.com/about", "text": "About"},
                {"href": "https://example.com/contact", "text": "Contact"},
            ],
            "external": [
                {"href": "https://other.com", "text": "Other Site"},
            ],
        }
    )
    _tool_with_crawler(tool, crawl_result)

    with _patch_detect_html(tool):
        result = await tool.execute(url="https://example.com", extract_links=True)

    assert result.error is False
    data = json.loads(result.content)
    assert data["status"] == "success"
    assert len(data["links"]) == 3
    assert data["links"][0] == {"url": "https://example.com/about", "text": "About"}


async def test_links_limited_to_20(tool):
    many_links = [
        {"href": f"https://example.com/page{i}", "text": f"Page {i}"} for i in range(30)
    ]
    crawl_result = _make_crawl_result(links={"internal": many_links, "external": []})
    _tool_with_crawler(tool, crawl_result)

    with _patch_detect_html(tool):
        result = await tool.execute(url="https://example.com", extract_links=True)

    data = json.loads(result.content)
    assert len(data["links"]) == 20


async def test_links_skip_empty_text(tool):
    crawl_result = _make_crawl_result(
        links={
            "internal": [
                {"href": "https://example.com/a", "text": ""},
                {"href": "https://example.com/b", "text": "Valid"},
            ],
            "external": [],
        }
    )
    _tool_with_crawler(tool, crawl_result)

    with _patch_detect_html(tool):
        result = await tool.execute(url="https://example.com", extract_links=True)

    data = json.loads(result.content)
    assert len(data["links"]) == 1
    assert data["links"][0]["text"] == "Valid"


# --- Content truncation ---


async def test_content_truncation(tool):
    long_markdown = "# Title\n\n" + "x" * 1000
    crawl_result = _make_crawl_result(markdown_text=long_markdown)
    _tool_with_crawler(tool, crawl_result)

    with _patch_detect_html(tool):
        result = await tool.execute(url="https://example.com")

    data = json.loads(result.content)
    assert data["text_content"].endswith("... [Content truncated]")
    assert len(data["text_content"]) <= tool.max_content_length + 30


# --- Headings extraction ---


async def test_headings_from_markdown(tool):
    md = "# Title\n## Section 1\n### Sub\n## Section 2\ntext\n#### Deep"
    crawl_result = _make_crawl_result(markdown_text=md)
    _tool_with_crawler(tool, crawl_result)

    with _patch_detect_html(tool):
        result = await tool.execute(url="https://example.com")

    data = json.loads(result.content)
    headings = data["headings"]
    assert len(headings) == 5
    assert headings[0] == {"level": "h1", "text": "Title"}
    assert headings[1] == {"level": "h2", "text": "Section 1"}
    assert headings[2] == {"level": "h3", "text": "Sub"}


async def test_headings_limited_to_10(tool):
    md = "\n".join(f"## Heading {i}" for i in range(15))
    crawl_result = _make_crawl_result(markdown_text=md)
    _tool_with_crawler(tool, crawl_result)

    with _patch_detect_html(tool):
        result = await tool.execute(url="https://example.com")

    data = json.loads(result.content)
    assert len(data["headings"]) == 10


# --- Empty / None markdown ---


async def test_empty_markdown(tool):
    crawl_result = _make_crawl_result()
    crawl_result.markdown = None
    _tool_with_crawler(tool, crawl_result)

    with _patch_detect_html(tool):
        result = await tool.execute(url="https://example.com")

    assert result.error is False
    data = json.loads(result.content)
    assert data["status"] == "success"
    assert data["text_content"] == ""
    assert data["headings"] == []


# --- Redirected URL ---


async def test_redirected_url(tool):
    crawl_result = _make_crawl_result(redirected_url="https://example.com/final")
    _tool_with_crawler(tool, crawl_result)

    with _patch_detect_html(tool):
        result = await tool.execute(url="https://example.com/old")

    data = json.loads(result.content)
    assert data["url"] == "https://example.com/final"


# --- Error handling: CrawlResult failures ---


async def test_crawl_failure_http_error(tool):
    crawl_result = _make_crawl_result(success=False, status_code=404, error_message="Not Found")
    _tool_with_crawler(tool, crawl_result)

    with _patch_detect_html(tool):
        result = await tool.execute(url="https://example.com/missing")

    assert result.error is True
    data = json.loads(result.content)
    assert "HTTP 404" in data["error"]
    assert "HTTP错误 404" in result.display


async def test_crawl_failure_timeout(tool):
    crawl_result = _make_crawl_result(
        success=False, status_code=None, error_message="Connection timeout"
    )
    _tool_with_crawler(tool, crawl_result)

    with _patch_detect_html(tool):
        result = await tool.execute(url="https://example.com")

    data = json.loads(result.content)
    assert data["error"] == "Request timeout"
    assert "超时" in result.display


async def test_crawl_failure_connection(tool):
    crawl_result = _make_crawl_result(
        success=False, status_code=None, error_message="DNS resolution failed"
    )
    _tool_with_crawler(tool, crawl_result)

    with _patch_detect_html(tool):
        result = await tool.execute(url="https://example.com")

    data = json.loads(result.content)
    assert data["error"] == "Connection error"
    assert "无法连接" in result.display


async def test_crawl_failure_generic(tool):
    crawl_result = _make_crawl_result(
        success=False, status_code=None, error_message="Something unexpected"
    )
    _tool_with_crawler(tool, crawl_result)

    with _patch_detect_html(tool):
        result = await tool.execute(url="https://example.com")

    assert result.error is True
    data = json.loads(result.content)
    assert "Something unexpected" in data["error"]


# --- Error handling: exceptions ---


async def test_timeout_exception(tool):
    _tool_with_crawler(tool, side_effect=TimeoutError("timed out"))

    with _patch_detect_html(tool):
        result = await tool.execute(url="https://example.com")

    data = json.loads(result.content)
    assert data["error"] == "Request timeout"
    assert "超时" in result.display


async def test_connection_exception(tool):
    _tool_with_crawler(tool, side_effect=ConnectionError("refused"))

    with _patch_detect_html(tool):
        result = await tool.execute(url="https://example.com")

    data = json.loads(result.content)
    assert data["error"] == "Connection error"


async def test_generic_exception(tool):
    _tool_with_crawler(tool, side_effect=Exception("something broke"))

    with _patch_detect_html(tool):
        result = await tool.execute(url="https://example.com")

    assert result.error is True
    data = json.loads(result.content)
    assert "something broke" in data["error"]


# --- Crawler reuse ---


async def test_crawler_reused_across_calls(tool):
    crawl_result = _make_crawl_result()
    mock = _tool_with_crawler(tool, crawl_result)

    with _patch_detect_html(tool):
        await tool.execute(url="https://example.com")
        await tool.execute(url="https://example.com/page2")

    # arun called twice on the same crawler instance
    assert mock.arun.call_count == 2


# --- use_browser ---


async def test_use_browser_uses_browser_crawler(tool):
    crawl_result = _make_crawl_result()
    browser_mock = _mock_crawler(crawl_result)
    http_mock = _mock_crawler(crawl_result)
    tool._http_crawler = http_mock
    tool._browser_crawler = browser_mock

    with _patch_detect_html(tool):
        result = await tool.execute(url="https://example.com", use_browser=True)

    data = json.loads(result.content)
    assert data["status"] == "success"
    browser_mock.arun.assert_awaited_once()
    http_mock.arun.assert_not_awaited()


async def test_http_mode_does_not_use_browser(tool):
    crawl_result = _make_crawl_result()
    browser_mock = _mock_crawler(crawl_result)
    http_mock = _mock_crawler(crawl_result)
    tool._http_crawler = http_mock
    tool._browser_crawler = browser_mock

    with _patch_detect_html(tool):
        result = await tool.execute(url="https://example.com", use_browser=False)

    data = json.loads(result.content)
    assert data["status"] == "success"
    http_mock.arun.assert_awaited_once()
    browser_mock.arun.assert_not_awaited()


# --- Metadata fallback ---


async def test_metadata_og_description_fallback(tool):
    crawl_result = _make_crawl_result(
        metadata={"title": "Page", "og:description": "OG desc"},
    )
    _tool_with_crawler(tool, crawl_result)

    with _patch_detect_html(tool):
        result = await tool.execute(url="https://example.com")

    data = json.loads(result.content)
    assert data["meta_description"] == "OG desc"


async def test_missing_metadata(tool):
    crawl_result = _make_crawl_result(metadata=None)
    _tool_with_crawler(tool, crawl_result)

    with _patch_detect_html(tool):
        result = await tool.execute(url="https://example.com")

    data = json.loads(result.content)
    assert data["title"] == ""
    assert data["meta_description"] == ""


# --- close ---


async def test_close_cleans_up(tool):
    mock_http = _mock_crawler()
    mock_browser = _mock_crawler()
    tool._http_crawler = mock_http
    tool._browser_crawler = mock_browser

    await tool.close()

    mock_http.close.assert_awaited_once()
    mock_browser.close.assert_awaited_once()
    assert tool._http_crawler is None
    assert tool._browser_crawler is None


async def test_close_noop_when_no_crawlers(tool):
    await tool.close()  # Should not raise
    assert tool._http_crawler is None
    assert tool._browser_crawler is None


# --- Network policy ---


async def test_network_policy_deny_blocks_scrape():
    policy = MagicMock()
    policy.evaluate.return_value = MagicMock(level="deny", reason="Anonymous network")
    tool = WebFetchTool(network_policy=policy)

    result = await tool.execute(url="https://hidden.onion/page")

    assert result.error is True
    data = json.loads(result.content)
    assert "Network access denied" in data["error"]
    policy.evaluate.assert_called_once_with("hidden.onion")


async def test_network_policy_require_approval_denied():
    policy = MagicMock()
    policy.evaluate.return_value = MagicMock(
        level="require_approval", reason="Content sharing",
    )
    cb = AsyncMock(return_value=False)
    tool = WebFetchTool(network_policy=policy, approval_callback=cb)

    result = await tool.execute(url="https://pastebin.com/raw/abc")

    assert result.error is True
    data = json.loads(result.content)
    assert "Approval denied" in data["error"]
    cb.assert_awaited_once_with(
        "web_fetch", "pastebin.com", "connect", "Content sharing",
    )


async def test_network_policy_require_approval_granted():
    policy = MagicMock()
    policy.evaluate.return_value = MagicMock(
        level="require_approval", reason="Content sharing",
    )
    cb = AsyncMock(return_value=True)
    crawl_result = _make_crawl_result(url="https://pastebin.com/raw/abc")
    tool = WebFetchTool(network_policy=policy, approval_callback=cb)
    _tool_with_crawler(tool, crawl_result)

    with _patch_detect_html(tool):
        result = await tool.execute(url="https://pastebin.com/raw/abc")

    assert result.error is False
    data = json.loads(result.content)
    assert data["status"] == "success"
    cb.assert_awaited_once()


async def test_network_policy_require_approval_no_callback_denies():
    policy = MagicMock()
    policy.evaluate.return_value = MagicMock(
        level="require_approval", reason="Content sharing",
    )
    tool = WebFetchTool(network_policy=policy)  # no callback

    result = await tool.execute(url="https://pastebin.com/raw/abc")

    assert result.error is True
    data = json.loads(result.content)
    assert "Approval denied" in data["error"]


async def test_network_policy_allow_proceeds():
    policy = MagicMock()
    policy.evaluate.return_value = MagicMock(
        level="allow", reason="default policy",
    )
    crawl_result = _make_crawl_result()
    tool = WebFetchTool(network_policy=policy)
    _tool_with_crawler(tool, crawl_result)

    with _patch_detect_html(tool):
        result = await tool.execute(url="https://example.com")

    assert result.error is False
    data = json.loads(result.content)
    assert data["status"] == "success"
