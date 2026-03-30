from unittest.mock import AsyncMock, MagicMock

import pytest

from tank_backend.tools.web_scraper import WebScraperTool

MODULE = "tank_backend.tools.web_scraper"


@pytest.fixture
def tool():
    return WebScraperTool(timeout=10, max_content_length=500)


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


# --- get_info ---


def test_get_info():
    tool = WebScraperTool()
    info = tool.get_info()
    assert info.name == "web_scraper"
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
    assert "error" in result
    assert "Invalid URL" in result["error"]
    assert "无法访问URL" in result["message"]


async def test_invalid_url_no_netloc(tool):
    result = await tool.execute(url="http://")
    assert "error" in result
    assert "Invalid URL" in result["error"]


async def test_unsupported_scheme(tool):
    result = await tool.execute(url="ftp://example.com/file")
    assert "error" in result
    assert "Only HTTP and HTTPS" in result["error"]
    assert "仅支持HTTP和HTTPS" in result["message"]


# --- Successful scrape ---


async def test_successful_scrape(tool):
    crawl_result = _make_crawl_result(
        markdown_text="# Hello World\n\nThis is a test page with content.",
        metadata={"title": "Hello World", "description": "A test page"},
    )
    _tool_with_crawler(tool, crawl_result)

    result = await tool.execute(url="https://example.com")

    assert result["status"] == "success"
    assert result["title"] == "Hello World"
    assert result["meta_description"] == "A test page"
    assert "# Hello World" in result["text_content"]
    assert "This is a test page" in result["text_content"]
    assert result["headings"] == [{"level": "h1", "text": "Hello World"}]
    assert "links" not in result


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

    result = await tool.execute(url="https://example.com", extract_links=True)

    assert result["status"] == "success"
    assert len(result["links"]) == 3
    assert result["links"][0] == {"url": "https://example.com/about", "text": "About"}
    assert "found 3 links" in result["message"]


async def test_links_limited_to_20(tool):
    many_links = [
        {"href": f"https://example.com/page{i}", "text": f"Page {i}"} for i in range(30)
    ]
    crawl_result = _make_crawl_result(links={"internal": many_links, "external": []})
    _tool_with_crawler(tool, crawl_result)

    result = await tool.execute(url="https://example.com", extract_links=True)

    assert len(result["links"]) == 20


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

    result = await tool.execute(url="https://example.com", extract_links=True)

    assert len(result["links"]) == 1
    assert result["links"][0]["text"] == "Valid"


# --- Content truncation ---


async def test_content_truncation(tool):
    long_markdown = "# Title\n\n" + "x" * 1000
    crawl_result = _make_crawl_result(markdown_text=long_markdown)
    _tool_with_crawler(tool, crawl_result)

    result = await tool.execute(url="https://example.com")

    assert result["text_content"].endswith("... [Content truncated]")
    assert len(result["text_content"]) <= tool.max_content_length + 30


# --- Headings extraction ---


async def test_headings_from_markdown(tool):
    md = "# Title\n## Section 1\n### Sub\n## Section 2\ntext\n#### Deep"
    crawl_result = _make_crawl_result(markdown_text=md)
    _tool_with_crawler(tool, crawl_result)

    result = await tool.execute(url="https://example.com")

    headings = result["headings"]
    assert len(headings) == 5
    assert headings[0] == {"level": "h1", "text": "Title"}
    assert headings[1] == {"level": "h2", "text": "Section 1"}
    assert headings[2] == {"level": "h3", "text": "Sub"}


async def test_headings_limited_to_10(tool):
    md = "\n".join(f"## Heading {i}" for i in range(15))
    crawl_result = _make_crawl_result(markdown_text=md)
    _tool_with_crawler(tool, crawl_result)

    result = await tool.execute(url="https://example.com")

    assert len(result["headings"]) == 10


# --- Empty / None markdown ---


async def test_empty_markdown(tool):
    crawl_result = _make_crawl_result()
    crawl_result.markdown = None
    _tool_with_crawler(tool, crawl_result)

    result = await tool.execute(url="https://example.com")

    assert result["status"] == "success"
    assert result["text_content"] == ""
    assert result["headings"] == []


# --- Redirected URL ---


async def test_redirected_url(tool):
    crawl_result = _make_crawl_result(redirected_url="https://example.com/final")
    _tool_with_crawler(tool, crawl_result)

    result = await tool.execute(url="https://example.com/old")

    assert result["url"] == "https://example.com/final"


# --- Error handling: CrawlResult failures ---


async def test_crawl_failure_http_error(tool):
    crawl_result = _make_crawl_result(success=False, status_code=404, error_message="Not Found")
    _tool_with_crawler(tool, crawl_result)

    result = await tool.execute(url="https://example.com/missing")

    assert "error" in result
    assert "HTTP 404" in result["error"]
    assert "HTTP错误 404" in result["message"]


async def test_crawl_failure_timeout(tool):
    crawl_result = _make_crawl_result(
        success=False, status_code=None, error_message="Connection timeout"
    )
    _tool_with_crawler(tool, crawl_result)

    result = await tool.execute(url="https://example.com")

    assert result["error"] == "Request timeout"
    assert "超时" in result["message"]


async def test_crawl_failure_connection(tool):
    crawl_result = _make_crawl_result(
        success=False, status_code=None, error_message="DNS resolution failed"
    )
    _tool_with_crawler(tool, crawl_result)

    result = await tool.execute(url="https://example.com")

    assert result["error"] == "Connection error"
    assert "无法连接" in result["message"]


async def test_crawl_failure_generic(tool):
    crawl_result = _make_crawl_result(
        success=False, status_code=None, error_message="Something unexpected"
    )
    _tool_with_crawler(tool, crawl_result)

    result = await tool.execute(url="https://example.com")

    assert "error" in result
    assert "Something unexpected" in result["error"]


# --- Error handling: exceptions ---


async def test_timeout_exception(tool):
    _tool_with_crawler(tool, side_effect=TimeoutError("timed out"))

    result = await tool.execute(url="https://example.com")

    assert result["error"] == "Request timeout"
    assert "超时" in result["message"]


async def test_connection_exception(tool):
    _tool_with_crawler(tool, side_effect=ConnectionError("refused"))

    result = await tool.execute(url="https://example.com")

    assert result["error"] == "Connection error"


async def test_generic_exception(tool):
    _tool_with_crawler(tool, side_effect=Exception("something broke"))

    result = await tool.execute(url="https://example.com")

    assert "error" in result
    assert "something broke" in result["error"]


# --- Crawler reuse ---


async def test_crawler_reused_across_calls(tool):
    crawl_result = _make_crawl_result()
    mock = _tool_with_crawler(tool, crawl_result)

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

    result = await tool.execute(url="https://example.com", use_browser=True)

    assert result["status"] == "success"
    browser_mock.arun.assert_awaited_once()
    http_mock.arun.assert_not_awaited()


async def test_http_mode_does_not_use_browser(tool):
    crawl_result = _make_crawl_result()
    browser_mock = _mock_crawler(crawl_result)
    http_mock = _mock_crawler(crawl_result)
    tool._http_crawler = http_mock
    tool._browser_crawler = browser_mock

    result = await tool.execute(url="https://example.com", use_browser=False)

    assert result["status"] == "success"
    http_mock.arun.assert_awaited_once()
    browser_mock.arun.assert_not_awaited()


# --- Metadata fallback ---


async def test_metadata_og_description_fallback(tool):
    crawl_result = _make_crawl_result(
        metadata={"title": "Page", "og:description": "OG desc"},
    )
    _tool_with_crawler(tool, crawl_result)

    result = await tool.execute(url="https://example.com")

    assert result["meta_description"] == "OG desc"


async def test_missing_metadata(tool):
    crawl_result = _make_crawl_result(metadata=None)
    _tool_with_crawler(tool, crawl_result)

    result = await tool.execute(url="https://example.com")

    assert result["title"] == ""
    assert result["meta_description"] == ""


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
