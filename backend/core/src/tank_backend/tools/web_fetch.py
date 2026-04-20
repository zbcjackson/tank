import json
import logging
import re
import time
import xml.etree.ElementTree as ET
from collections import OrderedDict
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse, urlunparse

from .base import BaseTool, ToolInfo, ToolParameter, ToolResult

logger = logging.getLogger(__name__)

_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+)$", re.MULTILINE)


@dataclass
class CacheEntry:
    content: str
    content_type: str
    timestamp: float


class ResponseCache:
    """LRU cache with TTL for web fetch responses."""

    def __init__(self, max_size: int = 50, ttl_seconds: float = 900):  # 15 min
        self._cache: OrderedDict[str, CacheEntry] = OrderedDict()
        self._max_size = max_size
        self._ttl = ttl_seconds

    def _normalize_url(self, url: str) -> str:
        """Normalize URL for cache key (lowercase, strip fragment)."""
        parsed = urlparse(url.lower())
        # Strip fragment (#anchor)
        return urlunparse(parsed._replace(fragment=""))

    def get(self, url: str) -> CacheEntry | None:
        """Get cached entry if exists and not expired."""
        key = self._normalize_url(url)
        entry = self._cache.get(key)

        if entry is None:
            return None

        # Check TTL
        if time.time() - entry.timestamp > self._ttl:
            del self._cache[key]
            return None

        # Move to end (LRU)
        self._cache.move_to_end(key)
        return entry

    def put(self, url: str, content: str, content_type: str) -> None:
        """Cache response with current timestamp."""
        key = self._normalize_url(url)

        # Evict oldest if at capacity
        if len(self._cache) >= self._max_size and key not in self._cache:
            self._cache.popitem(last=False)  # Remove oldest

        self._cache[key] = CacheEntry(
            content=content,
            content_type=content_type,
            timestamp=time.time(),
        )
        self._cache.move_to_end(key)


class WebFetchTool(BaseTool):
    def __init__(
        self,
        timeout: int = 15,
        max_content_length: int = 50000,
        network_policy: Any = None,
        approval_callback: Any = None,
    ):
        self.timeout = timeout
        self.max_content_length = max_content_length
        self._http_crawler: Any = None
        self._browser_crawler: Any = None
        self._network_policy = network_policy
        self._approval_callback = approval_callback
        self._cache = ResponseCache(max_size=50, ttl_seconds=900)

    def get_info(self) -> ToolInfo:
        return ToolInfo(
            name="web_fetch",
            description=(
                "Fetch and extract content from any web URL."
                " Handles HTML, PDF, RSS/Atom feeds, JSON, plain text, and more."
                " Returns clean markdown or structured data for LLM consumption."
                " Supports JavaScript-rendered pages via use_browser option."
            ),
            parameters=[
                ToolParameter(
                    name="url",
                    type="string",
                    description=(
                        "The URL to fetch and extract content from"
                        " (supports HTTP/HTTPS, any content type)"
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="extract_links",
                    type="boolean",
                    description="Whether to extract and return links from HTML pages",
                    required=False,
                    default=False,
                ),
                ToolParameter(
                    name="use_browser",
                    type="boolean",
                    description=(
                        "Set to true for JavaScript-heavy pages that need browser rendering."
                        " Slower but handles SPAs and dynamic content. Only applies to HTML."
                    ),
                    required=False,
                    default=False,
                ),
            ],
        )

    async def _get_http_crawler(self) -> Any:
        if self._http_crawler is None:
            from crawl4ai import AsyncWebCrawler, HTTPCrawlerConfig
            from crawl4ai.async_crawler_strategy import AsyncHTTPCrawlerStrategy

            http_config = HTTPCrawlerConfig(
                method="GET",
                headers={"User-Agent": _USER_AGENT},
                follow_redirects=True,
                verify_ssl=True,
            )
            strategy = AsyncHTTPCrawlerStrategy(browser_config=http_config)
            self._http_crawler = AsyncWebCrawler(crawler_strategy=strategy)
            await self._http_crawler.start()
        return self._http_crawler

    async def _get_browser_crawler(self) -> Any:
        if self._browser_crawler is None:
            try:
                from crawl4ai import AsyncWebCrawler, BrowserConfig

                browser_config = BrowserConfig(
                    headless=True,
                    text_mode=True,
                    user_agent=_USER_AGENT,
                )
                self._browser_crawler = AsyncWebCrawler(config=browser_config)
                await self._browser_crawler.start()
            except (ImportError, Exception) as e:
                raise RuntimeError(
                    f"Browser mode requires Playwright. Install with: playwright install chromium. "
                    f"Error: {e}"
                ) from e
        return self._browser_crawler

    def _extract_headings(self, markdown: str) -> list[dict[str, str]]:
        headings = []
        for match in _HEADING_RE.finditer(markdown):
            level = len(match.group(1))
            text = match.group(2).strip()
            if text:
                headings.append({"level": f"h{level}", "text": text})
            if len(headings) >= 10:
                break
        return headings

    def _extract_links(self, links_dict: dict[str, list[dict]]) -> list[dict[str, str]]:
        result = []
        for category in ("internal", "external"):
            for link in links_dict.get(category, []):
                href = link.get("href", "")
                text = link.get("text", "").strip()
                if href and text and href.startswith(("http://", "https://")):
                    result.append({"url": href, "text": text})
                if len(result) >= 20:
                    return result
        return result

    def _truncate(self, text: str) -> str:
        if len(text) > self.max_content_length:
            return text[: self.max_content_length] + "... [Content truncated]"
        return text

    async def _detect_content_type(self, url: str) -> tuple[str, bytes | None]:
        """
        Fetch URL and detect content type from headers.

        Returns:
            (content_type, content_bytes_or_none)

        For small responses (<1MB), returns full content.
        For large responses, returns None (caller must re-fetch).
        """
        import aiohttp

        async with (
            aiohttp.ClientSession() as session,
            session.get(
                url,
                headers={"User-Agent": _USER_AGENT},
                timeout=aiohttp.ClientTimeout(total=self.timeout),
            ) as resp,
        ):
            content_type = resp.headers.get("Content-Type", "").lower()
            # Strip charset: "text/html; charset=utf-8" → "text/html"
            content_type = content_type.split(";")[0].strip()

            # For small responses, read content now to avoid double-fetch
            content_length = resp.headers.get("Content-Length")
            if content_length and int(content_length) < 1_000_000:  # 1MB
                content = await resp.read()
                return content_type, content

            return content_type, None

    async def _try_fetch_feed(self, url: str) -> ToolResult | None:
        """Try to fetch and parse as RSS/Atom feed. Returns None if not a feed."""
        try:
            import aiohttp

            async with (
                aiohttp.ClientSession() as session,
                session.get(
                    url,
                    headers={"User-Agent": _USER_AGENT},
                    timeout=aiohttp.ClientTimeout(total=self.timeout),
                ) as resp,
            ):
                content_type = resp.headers.get("Content-Type", "").lower()

                # Check if it's a feed
                if not any(
                    ft in content_type for ft in ("rss", "xml", "atom")
                ):
                    return None

                raw_content = await resp.read()
                feed_data = self._parse_rss_feed(raw_content, url)

                # Format as markdown for LLM
                lines = [
                    f"# {feed_data['feed_title']}",
                    "",
                    feed_data["feed_description"],
                    "",
                    f"## Entries ({len(feed_data['entries'])} items)",
                    "",
                ]

                for entry in feed_data["entries"]:
                    lines.append(f"### {entry['title']}")
                    lines.append(f"Link: {entry['link']}")
                    if entry["published"]:
                        lines.append(f"Published: {entry['published']}")
                    if entry["description"]:
                        lines.append(f"\n{entry['description']}")
                    lines.append("")

                markdown_text = "\n".join(lines)

                feed_type = feed_data["feed_type"].upper()
                feed_title = feed_data["feed_title"]
                n_entries = len(feed_data["entries"])

                return ToolResult(
                    content=json.dumps(
                        {
                            "url": url,
                            "feed_type": feed_data["feed_type"],
                            "title": feed_title,
                            "description": feed_data["feed_description"],
                            "entries": feed_data["entries"],
                            "text_content": self._truncate(markdown_text),
                            "status": "success",
                        },
                        ensure_ascii=False,
                    ),
                    display=(
                        f"Parsed {feed_type} feed: "
                        f"{feed_title} ({n_entries} entries)"
                    ),
                )

        except Exception as e:
            logger.debug("Feed detection failed for %s: %s", url, e)
            return None  # Not a feed, fall back to HTML scraping

    def _parse_rss_feed(self, xml_content: bytes, url: str) -> dict[str, Any]:
        """Parse RSS/Atom feed and return structured data."""
        try:
            root = ET.fromstring(xml_content)

            # Detect feed type
            if root.tag == "rss":
                # RSS 2.0
                channel = root.find("channel")
                if channel is None:
                    raise ValueError("Invalid RSS feed: no channel element")

                feed_title = channel.findtext("title", "")
                feed_desc = channel.findtext("description", "")
                items = channel.findall("item")

                entries = []
                for item in items[:20]:  # Limit to 20 items
                    title = item.findtext("title", "")
                    link = item.findtext("link", "")
                    desc = item.findtext("description", "")
                    pub_date = item.findtext("pubDate", "")

                    # Strip HTML tags from description
                    if desc:
                        desc = re.sub(r"<[^>]+>", "", desc).strip()

                    entries.append({
                        "title": title,
                        "link": link,
                        "description": desc[:300] if desc else "",
                        "published": pub_date,
                    })

                return {
                    "feed_type": "rss",
                    "feed_title": feed_title,
                    "feed_description": feed_desc,
                    "entries": entries,
                }

            elif root.tag.endswith("}feed"):
                # Atom feed
                ns = {"atom": "http://www.w3.org/2005/Atom"}
                feed_title = root.findtext("atom:title", "", ns)
                feed_subtitle = root.findtext("atom:subtitle", "", ns)
                entries_elem = root.findall("atom:entry", ns)

                entries = []
                for entry in entries_elem[:20]:
                    title = entry.findtext("atom:title", "", ns)
                    link_elem = entry.find("atom:link[@rel='alternate']", ns)
                    if link_elem is None:
                        link_elem = entry.find("atom:link", ns)
                    link = link_elem.get("href", "") if link_elem is not None else ""

                    summary = entry.findtext("atom:summary", "", ns)
                    if not summary:
                        summary = entry.findtext("atom:content", "", ns)

                    if summary:
                        summary = re.sub(r"<[^>]+>", "", summary).strip()

                    published = entry.findtext("atom:published", "", ns)
                    if not published:
                        published = entry.findtext("atom:updated", "", ns)

                    entries.append({
                        "title": title,
                        "link": link,
                        "description": summary[:300] if summary else "",
                        "published": published,
                    })

                return {
                    "feed_type": "atom",
                    "feed_title": feed_title,
                    "feed_description": feed_subtitle,
                    "entries": entries,
                }

            else:
                raise ValueError(f"Unknown feed format: {root.tag}")

        except ET.ParseError as e:
            raise ValueError(f"XML parsing failed: {e}") from e

    async def _handle_html(
        self, url: str, extract_links: bool = False, use_browser: bool = False
    ) -> ToolResult:
        """Handle HTML content using crawl4ai."""
        from crawl4ai import CacheMode, CrawlerRunConfig

        crawler = await (
            self._get_browser_crawler() if use_browser else self._get_http_crawler()
        )

        run_config = CrawlerRunConfig(
            cache_mode=CacheMode.BYPASS,
            page_timeout=self.timeout * 1000,
            excluded_tags=["nav", "header", "footer", "aside"],
        )

        result = await crawler.arun(url=url, config=run_config)

        if not result.success:
            return self._map_error(url, result.status_code, result.error_message)

        # Extract markdown content
        markdown_text = ""
        if result.markdown is not None:
            markdown_text = str(result.markdown)

        # Extract metadata
        metadata = result.metadata or {}
        title = metadata.get("title", "")
        meta_desc = metadata.get("description", "") or metadata.get(
            "og:description", ""
        )

        text_content = self._truncate(markdown_text)

        response_dict = {
            "url": result.redirected_url or url,
            "content_type": "text/html",
            "title": title,
            "meta_description": meta_desc,
            "text_content": text_content,
            "headings": self._extract_headings(markdown_text),
            "status": "success",
        }

        if extract_links:
            links = self._extract_links(result.links or {})
            response_dict["links"] = links

        return ToolResult(
            content=json.dumps(response_dict, ensure_ascii=False),
            display=f"Fetched HTML: '{title or url}' ({len(text_content)} chars)",
        )

    async def _handle_pdf(self, url: str) -> ToolResult:
        """Extract text from PDF using crawl4ai PDFCrawlerStrategy."""
        from crawl4ai import AsyncWebCrawler, CacheMode, CrawlerRunConfig
        from crawl4ai.processors.pdf import (
            PDFContentScrapingStrategy,
            PDFCrawlerStrategy,
        )

        pdf_crawler_strategy = PDFCrawlerStrategy()
        pdf_scraping_strategy = PDFContentScrapingStrategy()

        crawler = AsyncWebCrawler(crawler_strategy=pdf_crawler_strategy)
        await crawler.start()

        try:
            run_config = CrawlerRunConfig(
                scraping_strategy=pdf_scraping_strategy,
                cache_mode=CacheMode.BYPASS,
                page_timeout=self.timeout * 1000,
            )

            result = await crawler.arun(url=url, config=run_config)

            if not result.success:
                return self._map_error(url, result.status_code, result.error_message)

            markdown_text = str(result.markdown) if result.markdown else ""
            metadata = result.metadata or {}

            return ToolResult(
                content=json.dumps(
                    {
                        "url": url,
                        "content_type": "application/pdf",
                        "title": metadata.get("title", ""),
                        "text_content": self._truncate(markdown_text),
                        "status": "success",
                    },
                    ensure_ascii=False,
                ),
                display=f"Extracted PDF: {metadata.get('title', url)} ({len(markdown_text)} chars)",
            )
        finally:
            await crawler.close()

    async def _handle_json(self, url: str, content: bytes | None = None) -> ToolResult:
        """Pretty-print JSON content."""
        if content is None:
            import aiohttp

            async with (
                aiohttp.ClientSession() as session,
                session.get(
                    url,
                    headers={"User-Agent": _USER_AGENT},
                    timeout=aiohttp.ClientTimeout(total=self.timeout),
                ) as resp,
            ):
                content = await resp.read()

        try:
            data = json.loads(content)
            pretty = json.dumps(data, indent=2, ensure_ascii=False)

            return ToolResult(
                content=json.dumps(
                    {
                        "url": url,
                        "content_type": "application/json",
                        "data": data,  # Full structured data for LLM
                        "text_content": self._truncate(pretty),
                        "status": "success",
                    },
                    ensure_ascii=False,
                ),
                display=f"Fetched JSON from {url} ({len(pretty)} chars)",
            )
        except json.JSONDecodeError as e:
            return ToolResult(
                content=json.dumps(
                    {
                        "url": url,
                        "error": f"Invalid JSON: {e}",
                    },
                    ensure_ascii=False,
                ),
                display=f"Failed to parse JSON from {url}",
                error=True,
            )

    async def _handle_text(self, url: str, content: bytes | None = None) -> ToolResult:
        """Handle plain text content."""
        if content is None:
            import aiohttp

            async with (
                aiohttp.ClientSession() as session,
                session.get(
                    url,
                    headers={"User-Agent": _USER_AGENT},
                    timeout=aiohttp.ClientTimeout(total=self.timeout),
                ) as resp,
            ):
                content = await resp.read()

        text = content.decode("utf-8", errors="replace")

        return ToolResult(
            content=json.dumps(
                {
                    "url": url,
                    "content_type": "text/plain",
                    "text_content": self._truncate(text),
                    "status": "success",
                },
                ensure_ascii=False,
            ),
            display=f"Fetched text from {url} ({len(text)} chars)",
        )

    async def _handle_binary(self, url: str, content_type: str) -> ToolResult:
        """Handle binary content (images, audio, video) — metadata only."""
        import aiohttp

        async with (
            aiohttp.ClientSession() as session,
            session.head(
                url,
                headers={"User-Agent": _USER_AGENT},
                timeout=aiohttp.ClientTimeout(total=self.timeout),
            ) as resp,
        ):
            content_length = resp.headers.get("Content-Length", "unknown")

        return ToolResult(
            content=json.dumps(
                {
                    "url": url,
                    "content_type": content_type,
                    "size": content_length,
                    "note": "Binary content not extracted. URL provided for reference.",
                    "status": "success",
                },
                ensure_ascii=False,
            ),
            display=f"Binary content ({content_type}, {content_length} bytes) at {url}",
        )

    async def execute(
        self, url: str, extract_links: bool = False, use_browser: bool = False
    ) -> ToolResult:
        logger.info(f"Web fetching URL: {url} (browser={use_browser})")

        # Validate URL
        try:
            parsed_url = urlparse(url)
            if not parsed_url.scheme or not parsed_url.netloc:
                return ToolResult(
                    content=json.dumps(
                        {"url": url, "error": "Invalid URL format"},
                        ensure_ascii=False,
                    ),
                    display=f"无法访问URL '{url}'，请检查URL格式是否正确。",
                    error=True,
                )

            if parsed_url.scheme not in ("http", "https"):
                return ToolResult(
                    content=json.dumps(
                        {"url": url, "error": "Only HTTP and HTTPS URLs are supported."},
                        ensure_ascii=False,
                    ),
                    display="仅支持HTTP和HTTPS协议的URL。",
                    error=True,
                )

        except Exception as e:
            return ToolResult(
                content=json.dumps(
                    {"url": url, "error": f"URL validation failed: {e}"},
                    ensure_ascii=False,
                ),
                display=f"URL格式验证失败: {e}",
                error=True,
            )

        # Network policy check
        host = parsed_url.netloc.lower()
        if self._network_policy is not None:
            decision = self._network_policy.evaluate(host)
            if decision.level == "deny":
                logger.warning("web_fetch denied by network policy: %s", host)
                return ToolResult(
                    content=json.dumps(
                        {"url": url, "error": f"Network access denied: {host} ({decision.reason})"},
                        ensure_ascii=False,
                    ),
                    display=f"Cannot fetch: network policy blocks {host}.",
                    error=True,
                )
            if decision.level == "require_approval":
                approved = await self._request_approval(
                    host, "connect", decision.reason,
                )
                if not approved:
                    return ToolResult(
                        content=json.dumps(
                            {"url": url, "error": f"Approval denied: {host} ({decision.reason})"},
                            ensure_ascii=False,
                        ),
                        display=f"User denied connecting to {host}.",
                        error=True,
                    )

        # Check cache first
        cached = self._cache.get(url)
        if cached is not None:
            logger.debug(f"Cache hit for {url}")
            # Return cached result
            return ToolResult(
                content=cached.content,
                display=f"Fetched from cache: {url}",
            )

        try:
            # Detect content type
            content_type, prefetched_content = await self._detect_content_type(url)

            # Route to appropriate handler
            if content_type in ("text/html", "application/xhtml+xml"):
                result = await self._handle_html(url, extract_links, use_browser)

            elif content_type == "application/pdf":
                result = await self._handle_pdf(url)

            elif content_type in (
                "application/rss+xml",
                "application/atom+xml",
                "text/xml",
                "application/xml",
            ):
                # Try feed parser first
                feed_result = await self._try_fetch_feed(url)
                if feed_result is not None:
                    result = feed_result
                else:
                    # Not a feed, treat as generic XML (fallback to crawl4ai)
                    result = await self._handle_html(url, extract_links, use_browser)

            elif content_type == "application/json":
                result = await self._handle_json(url, prefetched_content)

            elif content_type in (
                "text/plain",
                "text/csv",
                "text/css",
                "application/javascript",
                "text/javascript",
            ):
                result = await self._handle_text(url, prefetched_content)

            elif content_type.startswith(("image/", "audio/", "video/")):
                result = await self._handle_binary(url, content_type)

            else:
                # Unknown content type — report metadata
                result = await self._handle_binary(url, content_type)

            # Cache successful results
            if not result.error:
                self._cache.put(url, result.content, content_type)

            return result

        except TimeoutError:
            logger.error(f"Timeout while accessing {url}")
            return ToolResult(
                content=json.dumps(
                    {"url": url, "error": "Request timeout"},
                    ensure_ascii=False,
                ),
                display=f"访问 '{url}' 超时，请稍后再试或检查网络连接。",
                error=True,
            )

        except ConnectionError:
            logger.error(f"Connection error while accessing {url}")
            return ToolResult(
                content=json.dumps(
                    {"url": url, "error": "Connection error"},
                    ensure_ascii=False,
                ),
                display=f"无法连接到 '{url}'，请检查URL是否正确或网络连接。",
                error=True,
            )

        except RuntimeError as e:
            if "Playwright" in str(e):
                logger.error(f"Browser not available: {e}")
                return ToolResult(
                    content=json.dumps(
                        {"url": url, "error": str(e)},
                        ensure_ascii=False,
                    ),
                    display="浏览器模式不可用，请安装 Playwright。",
                    error=True,
                )
            logger.error(f"Runtime error fetching {url}: {e}")
            return ToolResult(
                content=json.dumps(
                    {"url": url, "error": str(e)},
                    ensure_ascii=False,
                ),
                display=f"获取 '{url}' 时出现错误: {e}",
                error=True,
            )

        except Exception as e:
            logger.error(f"Error fetching {url}: {e}")
            return ToolResult(
                content=json.dumps(
                    {"url": url, "error": str(e)},
                    ensure_ascii=False,
                ),
                display=f"获取 '{url}' 时出现错误: {e}",
                error=True,
            )

    def _map_error(
        self, url: str, status_code: int | None, error_message: str | None
    ) -> ToolResult:
        msg = error_message or "Unknown error"

        if status_code and 400 <= status_code < 600:
            return ToolResult(
                content=json.dumps(
                    {"url": url, "error": f"HTTP {status_code}"},
                    ensure_ascii=False,
                ),
                display=f"访问 '{url}' 时发生HTTP错误 {status_code}。",
                error=True,
            )

        lower_msg = msg.lower()
        if "timeout" in lower_msg:
            return ToolResult(
                content=json.dumps(
                    {"url": url, "error": "Request timeout"},
                    ensure_ascii=False,
                ),
                display=f"访问 '{url}' 超时，请稍后再试或检查网络连接。",
                error=True,
            )

        if "connect" in lower_msg or "dns" in lower_msg or "resolve" in lower_msg:
            return ToolResult(
                content=json.dumps(
                    {"url": url, "error": "Connection error"},
                    ensure_ascii=False,
                ),
                display=f"无法连接到 '{url}'，请检查URL是否正确或网络连接。",
                error=True,
            )

        return ToolResult(
            content=json.dumps(
                {"url": url, "error": msg},
                ensure_ascii=False,
            ),
            display=f"获取 '{url}' 时出现错误: {msg}",
            error=True,
        )

    async def close(self) -> None:
        if self._http_crawler:
            await self._http_crawler.close()
            self._http_crawler = None
        if self._browser_crawler:
            await self._browser_crawler.close()
            self._browser_crawler = None

    async def _request_approval(
        self, host: str, operation: str, reason: str,
    ) -> bool:
        """Request host-specific approval. Returns False if no callback or denied."""
        if self._approval_callback is None:
            logger.warning(
                "web_fetch require_approval but no callback — denying: %s",
                host,
            )
            return False
        return await self._approval_callback(
            "web_fetch", host, operation, reason,
        )
