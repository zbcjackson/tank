"""Test RSS/Atom feed parsing in web_fetch."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tank_backend.tools.web_fetch import WebFetchTool


@pytest.fixture
def tool():
    return WebFetchTool(timeout=10, max_content_length=5000)


# Sample RSS 2.0 feed
RSS_FEED = b"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>Test Feed</title>
    <description>A test RSS feed</description>
    <item>
      <title>First Post</title>
      <link>https://example.com/post1</link>
      <description>This is the first post</description>
      <pubDate>Mon, 01 Jan 2024 12:00:00 GMT</pubDate>
    </item>
    <item>
      <title>Second Post</title>
      <link>https://example.com/post2</link>
      <description><![CDATA[<p>HTML content here</p>]]></description>
      <pubDate>Tue, 02 Jan 2024 12:00:00 GMT</pubDate>
    </item>
  </channel>
</rss>
"""

# Sample Atom feed
ATOM_FEED = b"""<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <title>Test Atom Feed</title>
  <subtitle>An Atom feed for testing</subtitle>
  <entry>
    <title>Atom Entry 1</title>
    <link rel="alternate" href="https://example.com/atom1"/>
    <summary>Summary of atom entry 1</summary>
    <published>2024-01-01T12:00:00Z</published>
  </entry>
  <entry>
    <title>Atom Entry 2</title>
    <link href="https://example.com/atom2"/>
    <content>Content of atom entry 2</content>
    <updated>2024-01-02T12:00:00Z</updated>
  </entry>
</feed>
"""


async def test_rss_feed_detection_and_parsing(tool):
    """RSS feed is detected by content-type and parsed correctly."""
    mock_resp = MagicMock()
    mock_resp.headers = {"Content-Type": "application/rss+xml; charset=UTF-8"}
    mock_resp.read = AsyncMock(return_value=RSS_FEED)

    mock_session = MagicMock()
    mock_session.get = MagicMock(return_value=mock_resp)
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock()

    mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
    mock_resp.__aexit__ = AsyncMock()

    # _detect_content_type returns xml, then _try_fetch_feed handles it
    with patch.object(
        tool, "_detect_content_type",
        return_value=("application/rss+xml", None),
    ), patch("aiohttp.ClientSession", return_value=mock_session):
        result = await tool.execute(url="https://example.com/feed")

    assert result.error is False
    data = json.loads(result.content)

    assert data["feed_type"] == "rss"
    assert data["title"] == "Test Feed"
    assert data["description"] == "A test RSS feed"
    assert len(data["entries"]) == 2

    assert data["entries"][0]["title"] == "First Post"
    assert data["entries"][0]["link"] == "https://example.com/post1"
    assert "first post" in data["entries"][0]["description"]

    assert "text_content" in data
    assert "# Test Feed" in data["text_content"]
    assert "### First Post" in data["text_content"]

    assert "Parsed RSS feed" in result.display
    assert "2 entries" in result.display


async def test_atom_feed_detection_and_parsing(tool):
    """Atom feed is detected and parsed correctly."""
    mock_resp = MagicMock()
    mock_resp.headers = {"Content-Type": "application/atom+xml"}
    mock_resp.read = AsyncMock(return_value=ATOM_FEED)

    mock_session = MagicMock()
    mock_session.get = MagicMock(return_value=mock_resp)
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock()

    mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
    mock_resp.__aexit__ = AsyncMock()

    with patch.object(
        tool, "_detect_content_type",
        return_value=("application/atom+xml", None),
    ), patch("aiohttp.ClientSession", return_value=mock_session):
        result = await tool.execute(url="https://example.com/atom")

    assert result.error is False
    data = json.loads(result.content)

    assert data["feed_type"] == "atom"
    assert data["title"] == "Test Atom Feed"
    assert len(data["entries"]) == 2

    assert data["entries"][0]["title"] == "Atom Entry 1"
    assert data["entries"][0]["link"] == "https://example.com/atom1"

    assert "Parsed ATOM feed" in result.display


async def test_html_page_not_detected_as_feed(tool):
    """HTML pages with text/html content-type go to HTML handler."""
    mock_crawler = MagicMock()
    mock_result = MagicMock()
    mock_result.success = True
    mock_result.markdown = "# HTML Page"
    mock_result.metadata = {"title": "HTML Page"}
    mock_result.links = {}
    mock_result.redirected_url = None
    mock_crawler.arun = AsyncMock(return_value=mock_result)
    tool._http_crawler = mock_crawler

    with patch.object(
        tool, "_detect_content_type",
        return_value=("text/html", None),
    ):
        result = await tool.execute(url="https://example.com/page")

    # Should have gone to HTML handler (crawl4ai)
    mock_crawler.arun.assert_awaited_once()
    assert result.error is False


async def test_feed_parsing_error_falls_back_to_html(tool):
    """Malformed XML falls back to HTML scraping."""
    # Mock crawl4ai fallback
    mock_crawler = MagicMock()
    mock_result = MagicMock()
    mock_result.success = True
    mock_result.markdown = "# Fallback"
    mock_result.metadata = {"title": "Fallback"}
    mock_result.links = {}
    mock_result.redirected_url = None
    mock_crawler.arun = AsyncMock(return_value=mock_result)
    tool._http_crawler = mock_crawler

    # _detect_content_type says XML, but _try_fetch_feed fails → fallback to HTML
    with patch.object(
        tool, "_detect_content_type",
        return_value=("application/rss+xml", None),
    ), patch.object(tool, "_try_fetch_feed", return_value=None):
        await tool.execute(url="https://example.com/bad-feed")

    # Should have fallen back to crawl4ai
    mock_crawler.arun.assert_awaited_once()


async def test_rss_html_tags_stripped_from_description(tool):
    """HTML tags in RSS descriptions are stripped."""
    mock_resp = MagicMock()
    mock_resp.headers = {"Content-Type": "application/rss+xml"}
    mock_resp.read = AsyncMock(return_value=RSS_FEED)

    mock_session = MagicMock()
    mock_session.get = MagicMock(return_value=mock_resp)
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock()

    mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
    mock_resp.__aexit__ = AsyncMock()

    with patch.object(
        tool, "_detect_content_type",
        return_value=("application/rss+xml", None),
    ), patch("aiohttp.ClientSession", return_value=mock_session):
        result = await tool.execute(url="https://example.com/feed")

    data = json.loads(result.content)
    # Second entry has CDATA with HTML tags
    assert "<p>" not in data["entries"][1]["description"]
    assert "HTML content here" in data["entries"][1]["description"]
