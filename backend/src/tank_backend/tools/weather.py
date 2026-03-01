import logging
from typing import Any

from .base import BaseTool, ToolInfo, ToolParameter

logger = logging.getLogger("WeatherTool")


class WeatherTool(BaseTool):
    def get_info(self) -> ToolInfo:
        return ToolInfo(
            name="get_weather",
            description="Get current weather information for a location",
            parameters=[
                ToolParameter(
                    name="location",
                    type="string",
                    description="The location to get weather for (e.g., 'New York', 'Beijing')",
                    required=True,
                )
            ],
        )

    async def execute(self, location: str) -> dict[str, Any]:
        logger.info(f"Getting weather for: {location}")
        return {
            "location": location,
            "temperature": "22°C",
            "condition": "Sunny",
            "message": f"The weather in {location} is sunny with a temperature of 22°C",
        }
