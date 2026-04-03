import json
import logging
from typing import Any

import requests

from ..policy.credentials import ServiceCredentialManager
from .base import BaseTool, ToolInfo, ToolParameter

logger = logging.getLogger(__name__)


class WebSearchTool(BaseTool):
    def __init__(
        self,
        credential_manager: ServiceCredentialManager,
        network_policy: Any = None,
        approval_callback: Any = None,
    ):
        self._credentials = credential_manager
        self._network_policy = network_policy
        self._approval_callback = approval_callback

    def get_info(self) -> ToolInfo:
        return ToolInfo(
            name="web_search",
            description=(
                "Search the web for current information"
                " when you don't know the answer to a question"
            ),
            parameters=[
                ToolParameter(
                    name="query",
                    type="string",
                    description=(
                        "Search query to find information"
                        " (e.g., 'current weather in Beijing',"
                        " 'latest news about AI')"
                    ),
                    required=True,
                )
            ],
        )

    async def execute(self, query: str) -> dict[str, Any]:
        logger.info(f"Web searching for: {query}")

        # Resolve credential at call time
        api_key = self._credentials.get_credential("serper")
        if not api_key:
            return {
                "query": query,
                "error": "No API key configured for web search",
                "message": "Web search is not available — no serper credential.",
            }

        # Network policy check
        host = "google.serper.dev"
        if self._network_policy is not None:
            decision = self._network_policy.evaluate(host)
            if decision.level == "deny":
                logger.warning("web_search denied by network policy: %s", host)
                return {
                    "query": query,
                    "error": f"Network access denied: {host} ({decision.reason})",
                    "message": f"Cannot search: network policy blocks {host}.",
                }
            if decision.level == "require_approval":
                approved = await self._request_approval(
                    host, "connect", decision.reason,
                )
                if not approved:
                    return {
                        "query": query,
                        "error": f"Approval denied: {host} ({decision.reason})",
                        "message": f"User denied connecting to {host}.",
                    }

        try:
            # Use Serper API for web search
            url = "https://google.serper.dev/search"

            payload = json.dumps(
                {
                    "q": query,
                    "num": 5,  # Get top 5 results
                }
            )

            headers = {"X-API-KEY": api_key, "Content-Type": "application/json"}

            response = requests.post(url, headers=headers, data=payload, timeout=10)
            response.raise_for_status()
            data = response.json()

            # Process search results
            if "organic" in data and len(data["organic"]) > 0:
                results = data["organic"][:3]  # Take top 3 results

                # Build a comprehensive answer from multiple sources
                answer_parts = []
                sources = []

                for result in results:
                    title = result.get("title", "")
                    snippet = result.get("snippet", "")
                    link = result.get("link", "")

                    if snippet:
                        answer_parts.append(f"{title}: {snippet}")
                        sources.append(link)

                # Check if there's a knowledge graph result
                if "knowledgeGraph" in data:
                    kg = data["knowledgeGraph"]
                    kg_title = kg.get("title", "")
                    kg_description = kg.get("description", "")
                    if kg_title and kg_description:
                        answer_parts.insert(0, f"{kg_title}: {kg_description}")

                # Check if there's a featured snippet/answer box
                if "answerBox" in data:
                    answer_box = data["answerBox"]
                    answer_text = answer_box.get("answer", "") or answer_box.get("snippet", "")
                    if answer_text:
                        answer_parts.insert(0, f"Direct Answer: {answer_text}")

                if answer_parts:
                    combined_answer = "\n\n".join(answer_parts[:3])  # Limit to 3 parts
                    return {
                        "query": query,
                        "source": "Serper (Google Search)",
                        "answer": combined_answer,
                        "urls": sources[:3],
                        "message": f"Found information about '{query}': {combined_answer[:200]}...",
                    }

            # If no organic results, try to provide any available information
            if "answerBox" in data:
                answer_box = data["answerBox"]
                answer_text = answer_box.get("answer", "") or answer_box.get("snippet", "")
                if answer_text:
                    return {
                        "query": query,
                        "source": "Serper (Google Search)",
                        "answer": answer_text,
                        "url": answer_box.get("link", ""),
                        "message": f"Found direct answer for '{query}': {answer_text[:200]}...",
                    }

            return {
                "query": query,
                "source": "Serper (Google Search)",
                "message": (
                    f"Sorry, no specific information found for '{query}'."
                    " You may want to try rephrasing your search query."
                ),
            }

        except Exception as e:
            error_message = f"Error searching for '{query}': {str(e)}"
            logger.error(error_message)
            return {
                "query": query,
                "error": str(e),
                "message": f"抱歉，搜索'{query}'时出现错误。请稍后再试或重新表述您的问题。",
            }

    async def _request_approval(
        self, host: str, operation: str, reason: str,
    ) -> bool:
        """Request host-specific approval. Returns False if no callback or denied."""
        if self._approval_callback is None:
            logger.warning(
                "web_search require_approval but no callback — denying: %s",
                host,
            )
            return False
        return await self._approval_callback(
            "web_search", host, operation, reason,
        )
