import logging
import re
from typing import Any
from urllib.parse import urlparse

from .base import BaseTool, ToolInfo, ToolParameter

logger = logging.getLogger(__name__)

_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+)$", re.MULTILINE)


class WebScraperTool(BaseTool):
    def __init__(
        self,
        timeout: int = 15,
        max_content_length: int = 50000,
        network_policy: Any = None,
        audit_logger: Any = None,
        approval_callback: Any = None,
    ):
        self.timeout = timeout
        self.max_content_length = max_content_length
        self._http_crawler: Any = None
        self._browser_crawler: Any = None
        self._network_policy = network_policy
        self._audit = audit_logger
        self._approval_callback = approval_callback

    def get_info(self) -> ToolInfo:
        return ToolInfo(
            name="web_scraper",
            description=(
                "Fetch and extract content from web URLs."
                " Returns clean markdown for LLM consumption."
                " Supports JavaScript-rendered pages via use_browser option."
            ),
            parameters=[
                ToolParameter(
                    name="url",
                    type="string",
                    description=(
                        "The URL to scrape and extract content from"
                        " (must be a valid HTTP/HTTPS URL)"
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="extract_links",
                    type="boolean",
                    description="Whether to extract and return links from the page",
                    required=False,
                    default=False,
                ),
                ToolParameter(
                    name="use_browser",
                    type="boolean",
                    description=(
                        "Set to true for JavaScript-heavy pages that need browser rendering."
                        " Slower but handles SPAs and dynamic content."
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

    async def execute(
        self, url: str, extract_links: bool = False, use_browser: bool = False
    ) -> dict[str, Any]:
        logger.info(f"Web scraping URL: {url} (browser={use_browser})")

        # Validate URL
        try:
            parsed_url = urlparse(url)
            if not parsed_url.scheme or not parsed_url.netloc:
                return {
                    "url": url,
                    "error": "Invalid URL format. Please provide a valid HTTP or HTTPS URL.",
                    "message": f"无法访问URL '{url}'，请检查URL格式是否正确。",
                }

            if parsed_url.scheme not in ("http", "https"):
                return {
                    "url": url,
                    "error": "Only HTTP and HTTPS URLs are supported.",
                    "message": "仅支持HTTP和HTTPS协议的URL。",
                }

        except Exception as e:
            return {
                "url": url,
                "error": f"URL validation failed: {str(e)}",
                "message": f"URL格式验证失败: {str(e)}",
            }

        # Network policy check
        host = parsed_url.netloc.lower()
        if self._network_policy is not None:
            decision = self._network_policy.evaluate(host)
            if decision.level == "deny":
                logger.warning("web_scraper denied by network policy: %s", host)
                if self._audit is not None:
                    await self._audit.log_network_op(host, "deny", decision.reason)
                return {
                    "url": url,
                    "error": f"Network access denied: {host} ({decision.reason})",
                    "message": f"Cannot scrape: network policy blocks {host}.",
                }
            if decision.level == "require_approval":
                approved = await self._request_approval(
                    host, "connect", decision.reason,
                )
                if not approved:
                    if self._audit is not None:
                        await self._audit.log_network_op(
                            host, "denied_by_user", decision.reason,
                        )
                    return {
                        "url": url,
                        "error": f"Approval denied: {host} ({decision.reason})",
                        "message": f"User denied connecting to {host}.",
                    }
            if self._audit is not None:
                await self._audit.log_network_op(host, "allow", decision.reason)

        try:
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

            response = {
                "url": result.redirected_url or url,
                "title": title,
                "meta_description": meta_desc,
                "text_content": text_content,
                "headings": self._extract_headings(markdown_text),
                "status": "success",
                "message": f"Successfully extracted content from '{title or url}'",
            }

            if extract_links:
                links = self._extract_links(result.links or {})
                response["links"] = links
                response["message"] += f" and found {len(links)} links"

            return response

        except TimeoutError:
            logger.error(f"Timeout while accessing {url}")
            return {
                "url": url,
                "error": "Request timeout",
                "message": f"访问 '{url}' 超时，请稍后再试或检查网络连接。",
            }

        except ConnectionError:
            logger.error(f"Connection error while accessing {url}")
            return {
                "url": url,
                "error": "Connection error",
                "message": f"无法连接到 '{url}'，请检查URL是否正确或网络连接。",
            }

        except RuntimeError as e:
            if "Playwright" in str(e):
                logger.error(f"Browser not available: {e}")
                return {
                    "url": url,
                    "error": str(e),
                    "message": "浏览器模式不可用，请安装 Playwright。",
                }
            logger.error(f"Runtime error scraping {url}: {e}")
            return {"url": url, "error": str(e), "message": f"抓取 '{url}' 时出现错误: {e}"}

        except Exception as e:
            logger.error(f"Error scraping {url}: {e}")
            return {"url": url, "error": str(e), "message": f"抓取 '{url}' 时出现错误: {e}"}

    def _map_error(
        self, url: str, status_code: int | None, error_message: str | None
    ) -> dict[str, Any]:
        msg = error_message or "Unknown error"

        if status_code and 400 <= status_code < 600:
            return {
                "url": url,
                "error": f"HTTP {status_code}",
                "message": f"访问 '{url}' 时发生HTTP错误 {status_code}。",
            }

        lower_msg = msg.lower()
        if "timeout" in lower_msg:
            return {
                "url": url,
                "error": "Request timeout",
                "message": f"访问 '{url}' 超时，请稍后再试或检查网络连接。",
            }

        if "connect" in lower_msg or "dns" in lower_msg or "resolve" in lower_msg:
            return {
                "url": url,
                "error": "Connection error",
                "message": f"无法连接到 '{url}'，请检查URL是否正确或网络连接。",
            }

        return {"url": url, "error": msg, "message": f"抓取 '{url}' 时出现错误: {msg}"}

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
                "web_scraper require_approval but no callback — denying: %s",
                host,
            )
            return False
        return await self._approval_callback(
            "web_scraper", host, operation, reason,
        )
