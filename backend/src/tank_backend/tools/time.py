import datetime
import logging
from typing import Dict, Any
from .base import BaseTool, ToolInfo

logger = logging.getLogger(__name__)


class TimeTool(BaseTool):
    def get_info(self) -> ToolInfo:
        return ToolInfo(
            name="get_time",
            description="Get current time and date",
            parameters=[]
        )

    async def execute(self) -> Dict[str, Any]:
        now = datetime.datetime.now()
        return {
            "current_time": now.strftime("%Y-%m-%d %H:%M:%S"),
            "message": f"The current time is {now.strftime('%Y-%m-%d %H:%M:%S')}"
        }