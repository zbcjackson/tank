import asyncio
import inspect
from typing import Dict, Any, Callable, Optional, List
import logging
import json

from .base import BaseTool, ToolInfo, ToolParameter
from .weather import WeatherTool
from .time import TimeTool
from .calculator import CalculatorTool
from .web_search import WebSearchTool

logger = logging.getLogger(__name__)

class ToolManager:
    def __init__(self):
        self.tools: Dict[str, BaseTool] = {}
        self.register_default_tools()

    def register_default_tools(self):
        default_tools = [
            WeatherTool(),
            TimeTool(),
            CalculatorTool(),
            WebSearchTool()
        ]

        for tool in default_tools:
            self.register_tool(tool)

    def register_tool(self, tool: BaseTool):
        info = tool.get_info()
        self.tools[info.name] = tool
        logger.info(f"Registered tool: {info.name}")

    def get_tool_info(self) -> List[ToolInfo]:
        return [tool.get_info() for tool in self.tools.values()]

    def get_tools_description(self) -> str:
        descriptions = []
        for tool in self.tools.values():
            info = tool.get_info()
            params_desc = []
            for param in info.parameters:
                required_str = "required" if param.required else "optional"
                params_desc.append(f"  - {param.name} ({param.type}, {required_str}): {param.description}")

            tool_desc = f"**{info.name}**: {info.description}"
            if params_desc:
                tool_desc += "\n" + "\n".join(params_desc)

            descriptions.append(tool_desc)

        return "\n\n".join(descriptions)

    async def execute_tool(self, tool_name: str, **kwargs) -> Dict[str, Any]:
        if tool_name not in self.tools:
            error_msg = f"Tool '{tool_name}' not found. Available tools: {list(self.tools.keys())}"
            logger.error(error_msg)
            return {
                "error": error_msg,
                "available_tools": list(self.tools.keys())
            }

        try:
            tool = self.tools[tool_name]
            logger.info(f"Executing tool: {tool_name} with parameters: {kwargs}")
            result = await tool.execute(**kwargs)
            logger.info(f"Tool {tool_name} executed successfully")
            return result

        except Exception as e:
            error_msg = f"Error executing tool '{tool_name}': {str(e)}"
            logger.error(error_msg)
            return {
                "error": error_msg,
                "tool_name": tool_name,
                "parameters": kwargs
            }

    def get_openai_tools(self) -> List[Dict[str, Any]]:
        """Convert tools to OpenAI function calling format"""
        openai_tools = []

        for tool in self.tools.values():
            info = tool.get_info()

            # Build parameters schema
            properties = {}
            required = []

            for param in info.parameters:
                properties[param.name] = {
                    "type": param.type,
                    "description": param.description
                }
                if param.required:
                    required.append(param.name)

            # Create OpenAI tool format
            openai_tool = {
                "type": "function",
                "function": {
                    "name": info.name,
                    "description": info.description,
                    "parameters": {
                        "type": "object",
                        "properties": properties,
                        "required": required
                    }
                }
            }

            openai_tools.append(openai_tool)

        return openai_tools

    async def execute_openai_tool_call(self, tool_call) -> Dict[str, Any]:
        """Execute tool from OpenAI function call format"""
        function_name = tool_call.function.name
        try:
            arguments = json.loads(tool_call.function.arguments)
        except json.JSONDecodeError:
            return {
                "error": f"Could not parse arguments for {function_name}",
                "arguments": tool_call.function.arguments
            }

        return await self.execute_tool(function_name, **arguments)

    def parse_tool_call(self, text: str) -> Optional[Dict[str, Any]]:
        import re

        tool_pattern = r'(\w+)\((.*?)\)'
        match = re.search(tool_pattern, text)

        if match:
            tool_name = match.group(1)
            params_str = match.group(2)

            if tool_name in self.tools:
                try:
                    if params_str.strip():
                        if params_str.strip().startswith('{'):
                            params = json.loads(params_str)
                        else:
                            params = {"input": params_str.strip().strip('\'"')}
                    else:
                        params = {}

                    return {
                        "tool_name": tool_name,
                        "parameters": params
                    }
                except json.JSONDecodeError:
                    logger.warning(f"Could not parse parameters for tool call: {text}")

        return None