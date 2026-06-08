import datetime
import json
import logging

from .base import BaseTool, ToolInfo, ToolMetadata, ToolResult

logger = logging.getLogger(__name__)


class TimeTool(BaseTool):
    def get_metadata(self) -> ToolMetadata:
        return ToolMetadata(idempotent=True)

    def get_info(self) -> ToolInfo:
        return ToolInfo(name="get_time", description="Get current time and date", parameters=[])

    async def execute(self) -> ToolResult:
        now = datetime.datetime.now()
        formatted = now.strftime("%Y-%m-%d %H:%M:%S")
        return ToolResult(
            content=json.dumps({"current_time": formatted}),
            display=f"The current time is {formatted}",
        )
