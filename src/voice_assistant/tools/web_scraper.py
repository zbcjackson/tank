import logging
import requests
from typing import Dict, Any, Optional
from urllib.parse import urlparse, urljoin
from bs4 import BeautifulSoup
from .base import BaseTool, ToolInfo, ToolParameter

logger = logging.getLogger(__name__)


class WebScraperTool(BaseTool):
    def __init__(self, timeout: int = 10, max_content_length: int = 50000):
        self.timeout = timeout
        self.max_content_length = max_content_length
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        })

    def get_info(self) -> ToolInfo:
        return ToolInfo(
            name="web_scraper",
            description="Fetch and extract content from web URLs to provide detailed information from web pages",
            parameters=[
                ToolParameter(
                    name="url",
                    type="string",
                    description="The URL to scrape and extract content from (must be a valid HTTP/HTTPS URL)",
                    required=True
                ),
                ToolParameter(
                    name="extract_links",
                    type="boolean",
                    description="Whether to extract and return links from the page",
                    required=False,
                    default=False
                )
            ]
        )

    def _clean_text(self, text: str) -> str:
        """Clean and normalize extracted text"""
        if not text:
            return ""

        # Remove extra whitespace and normalize line breaks
        lines = [line.strip() for line in text.split('\n')]
        lines = [line for line in lines if line]  # Remove empty lines
        return '\n'.join(lines)

    def _extract_content(self, soup: BeautifulSoup, url: str) -> Dict[str, Any]:
        """Extract meaningful content from the parsed HTML"""
        content = {}

        # Extract title
        title_tag = soup.find('title')
        content['title'] = title_tag.get_text().strip() if title_tag else ""

        # Extract meta description
        meta_desc = soup.find('meta', attrs={'name': 'description'})
        if not meta_desc:
            meta_desc = soup.find('meta', attrs={'property': 'og:description'})
        content['meta_description'] = meta_desc.get('content', '').strip() if meta_desc else ""

        # Remove script and style elements
        for script in soup(["script", "style", "nav", "header", "footer", "aside"]):
            script.decompose()

        # Try to find main content areas
        main_content = None
        for selector in ['main', 'article', '.content', '#content', '.main', '#main']:
            main_content = soup.select_one(selector)
            if main_content:
                break

        if not main_content:
            main_content = soup.find('body')

        if main_content:
            # Extract text content
            text_content = main_content.get_text()
            content['text'] = self._clean_text(text_content)

            # Limit content length to avoid overwhelming the LLM
            if len(content['text']) > self.max_content_length:
                content['text'] = content['text'][:self.max_content_length] + "... [Content truncated]"
        else:
            content['text'] = ""

        # Extract headings for structure
        headings = []
        for h in soup.find_all(['h1', 'h2', 'h3', 'h4', 'h5', 'h6']):
            headings.append({
                'level': h.name,
                'text': h.get_text().strip()
            })
        content['headings'] = headings[:10]  # Limit to first 10 headings

        return content

    def _extract_links(self, soup: BeautifulSoup, base_url: str) -> list:
        """Extract links from the page"""
        links = []
        for a_tag in soup.find_all('a', href=True):
            href = a_tag.get('href')
            if href:
                # Convert relative URLs to absolute
                absolute_url = urljoin(base_url, href)
                link_text = a_tag.get_text().strip()
                if link_text and absolute_url.startswith(('http://', 'https://')):
                    links.append({
                        'url': absolute_url,
                        'text': link_text
                    })

        return links[:20]  # Limit to first 20 links

    async def execute(self, url: str, extract_links: bool = False) -> Dict[str, Any]:
        logger.info(f"Web scraping URL: {url}")

        # Validate URL
        try:
            parsed_url = urlparse(url)
            if not parsed_url.scheme or not parsed_url.netloc:
                return {
                    "url": url,
                    "error": "Invalid URL format. Please provide a valid HTTP or HTTPS URL.",
                    "message": f"无法访问URL '{url}'，请检查URL格式是否正确。"
                }

            if parsed_url.scheme not in ['http', 'https']:
                return {
                    "url": url,
                    "error": "Only HTTP and HTTPS URLs are supported.",
                    "message": f"仅支持HTTP和HTTPS协议的URL。"
                }

        except Exception as e:
            return {
                "url": url,
                "error": f"URL validation failed: {str(e)}",
                "message": f"URL格式验证失败: {str(e)}"
            }

        try:
            # Fetch the webpage
            response = self.session.get(url, timeout=self.timeout)
            response.raise_for_status()

            # Check content type
            content_type = response.headers.get('content-type', '').lower()
            if 'text/html' not in content_type:
                return {
                    "url": url,
                    "error": f"URL does not return HTML content. Content-Type: {content_type}",
                    "message": f"该URL不是HTML网页，无法提取文本内容。内容类型: {content_type}"
                }

            # Parse HTML
            soup = BeautifulSoup(response.content, 'html.parser')

            # Extract content
            content = self._extract_content(soup, url)

            result = {
                "url": url,
                "title": content['title'],
                "meta_description": content['meta_description'],
                "text_content": content['text'],
                "headings": content['headings'],
                "status": "success",
                "message": f"Successfully extracted content from '{content['title'] or url}'"
            }

            # Add links if requested
            if extract_links:
                links = self._extract_links(soup, url)
                result['links'] = links
                result['message'] += f" and found {len(links)} links"

            return result

        except requests.exceptions.Timeout:
            error_message = f"Timeout while accessing {url}"
            logger.error(error_message)
            return {
                "url": url,
                "error": "Request timeout",
                "message": f"访问 '{url}' 超时，请稍后再试或检查网络连接。"
            }

        except requests.exceptions.ConnectionError:
            error_message = f"Connection error while accessing {url}"
            logger.error(error_message)
            return {
                "url": url,
                "error": "Connection error",
                "message": f"无法连接到 '{url}'，请检查URL是否正确或网络连接。"
            }

        except requests.exceptions.HTTPError as e:
            error_message = f"HTTP error {e.response.status_code} while accessing {url}"
            logger.error(error_message)
            return {
                "url": url,
                "error": f"HTTP {e.response.status_code}",
                "message": f"访问 '{url}' 时发生HTTP错误 {e.response.status_code}。"
            }

        except Exception as e:
            error_message = f"Error scraping {url}: {str(e)}"
            logger.error(error_message)
            return {
                "url": url,
                "error": str(e),
                "message": f"抓取 '{url}' 时出现错误: {str(e)}"
            }