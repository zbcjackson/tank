import logging
import requests
from bs4 import BeautifulSoup
from urllib.parse import quote_plus
from typing import Dict, Any
from .base import BaseTool, ToolInfo, ToolParameter

logger = logging.getLogger(__name__)


class WebSearchTool(BaseTool):
    def get_info(self) -> ToolInfo:
        return ToolInfo(
            name="web_search",
            description="Search the web for current information when you don't know the answer to a question",
            parameters=[
                ToolParameter(
                    name="query",
                    type="string",
                    description="Search query to find information (e.g., 'current weather in Beijing', 'latest news about AI')",
                    required=True
                )
            ]
        )

    async def execute(self, query: str) -> Dict[str, Any]:
        logger.info(f"Web searching for: {query}")
        try:
            # Use DuckDuckGo Instant Answer API (doesn't require API key)
            search_url = f"https://api.duckduckgo.com/?q={quote_plus(query)}&format=json&no_html=1&skip_disambig=1"

            response = requests.get(search_url, timeout=10)
            response.raise_for_status()
            data = response.json()

            # Try to get instant answer first
            if data.get("AbstractText"):
                return {
                    "query": query,
                    "source": "DuckDuckGo",
                    "answer": data["AbstractText"],
                    "url": data.get("AbstractURL", ""),
                    "message": f"Found information about '{query}': {data['AbstractText'][:200]}..."
                }

            # If no instant answer, try definition
            if data.get("Definition"):
                return {
                    "query": query,
                    "source": "DuckDuckGo",
                    "answer": data["Definition"],
                    "url": data.get("DefinitionURL", ""),
                    "message": f"Definition of '{query}': {data['Definition'][:200]}..."
                }

            # If no structured data, search for basic web results
            search_results = data.get("RelatedTopics", [])
            if search_results and isinstance(search_results[0], dict):
                first_result = search_results[0]
                if "Text" in first_result:
                    return {
                        "query": query,
                        "source": "DuckDuckGo",
                        "answer": first_result["Text"],
                        "url": first_result.get("FirstURL", ""),
                        "message": f"Found information about '{query}': {first_result['Text'][:200]}..."
                    }

            # Fallback: simple Google search scraping (use sparingly)
            return await self._fallback_search(query)

        except Exception as e:
            error_message = f"Error searching for '{query}': {str(e)}"
            logger.error(error_message)
            return {
                "query": query,
                "error": str(e),
                "message": f"抱歉，我无法搜索到关于'{query}'的信息。请尝试重新表述您的问题。"
            }

    async def _fallback_search(self, query: str) -> Dict[str, Any]:
        """Fallback search using basic web scraping"""
        try:
            # Use a simple search engine that allows scraping
            search_url = f"https://html.duckduckgo.com/html/?q={quote_plus(query)}"
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
            }

            response = requests.get(search_url, headers=headers, timeout=10)
            response.raise_for_status()

            soup = BeautifulSoup(response.content, 'html.parser')

            # Look for search result snippets
            results = soup.find_all('a', class_='result__snippet')
            if results:
                snippet = results[0].get_text(strip=True)
                return {
                    "query": query,
                    "source": "Web Search",
                    "answer": snippet,
                    "message": f"找到关于'{query}'的信息: {snippet[:200]}..."
                }

            return {
                "query": query,
                "source": "Web Search",
                "message": f"抱歉，没有找到关于'{query}'的具体信息。"
            }

        except Exception as e:
            return {
                "query": query,
                "error": str(e),
                "message": f"搜索时出现错误: {str(e)}"
            }