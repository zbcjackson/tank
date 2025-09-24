import asyncio
import inspect
from typing import Dict, Any, Callable, Optional, List
from abc import ABC, abstractmethod
from pydantic import BaseModel
import logging
import requests
from bs4 import BeautifulSoup
import re
from urllib.parse import quote_plus

logger = logging.getLogger(__name__)

class ToolParameter(BaseModel):
    name: str
    type: str
    description: str
    required: bool = True
    default: Any = None

class ToolInfo(BaseModel):
    name: str
    description: str
    parameters: List[ToolParameter]

class BaseTool(ABC):
    @abstractmethod
    def get_info(self) -> ToolInfo:
        pass

    @abstractmethod
    async def execute(self, **kwargs) -> Any:
        pass

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
                    required=True
                )
            ]
        )

    async def execute(self, location: str) -> Dict[str, Any]:
        logger.info(f"Getting weather for: {location}")
        return {
            "location": location,
            "temperature": "22°C",
            "condition": "Sunny",
            "message": f"The weather in {location} is sunny with a temperature of 22°C"
        }

class TimeTool(BaseTool):
    def get_info(self) -> ToolInfo:
        return ToolInfo(
            name="get_time",
            description="Get current time and date",
            parameters=[]
        )

    async def execute(self) -> Dict[str, Any]:
        import datetime
        now = datetime.datetime.now()
        return {
            "current_time": now.strftime("%Y-%m-%d %H:%M:%S"),
            "message": f"The current time is {now.strftime('%Y-%m-%d %H:%M:%S')}"
        }

class CalculatorTool(BaseTool):
    def get_info(self) -> ToolInfo:
        return ToolInfo(
            name="calculate",
            description="Perform basic mathematical calculations",
            parameters=[
                ToolParameter(
                    name="expression",
                    type="string",
                    description="Mathematical expression to evaluate (e.g., '2 + 2', '10 * 5')",
                    required=True
                )
            ]
        )

    async def execute(self, expression: str) -> Dict[str, Any]:
        logger.info(f"Calculating: {expression}")
        try:
            import ast
            import operator as op

            # Supported operators
            operators = {
                ast.Add: op.add,
                ast.Sub: op.sub,
                ast.Mult: op.mul,
                ast.Div: op.truediv,
                ast.Pow: op.pow,
                ast.BitXor: op.xor,
                ast.USub: op.neg,
            }

            def eval_expr(expr):
                return eval_(ast.parse(expr, mode='eval').body)

            def eval_(node):
                if isinstance(node, ast.Constant):
                    return node.value
                elif isinstance(node, ast.BinOp):
                    return operators[type(node.op)](eval_(node.left), eval_(node.right))
                elif isinstance(node, ast.UnaryOp):
                    return operators[type(node.op)](eval_(node.operand))
                else:
                    raise TypeError(node)

            result = eval_expr(expression)
            return {
                "expression": expression,
                "result": result,
                "message": f"{expression} = {result}"
            }

        except Exception as e:
            error_message = f"Error calculating {expression}: {str(e)}"
            logger.error(error_message)
            return {
                "expression": expression,
                "error": str(e),
                "message": error_message
            }

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
            import json
            arguments = json.loads(tool_call.function.arguments)
        except json.JSONDecodeError:
            return {
                "error": f"Could not parse arguments for {function_name}",
                "arguments": tool_call.function.arguments
            }

        return await self.execute_tool(function_name, **arguments)

    def parse_tool_call(self, text: str) -> Optional[Dict[str, Any]]:
        import re
        import json

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