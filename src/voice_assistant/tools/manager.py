import asyncio
import inspect
from typing import Dict, Any, Callable, Optional, List
from abc import ABC, abstractmethod
from pydantic import BaseModel
import logging

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

class ToolManager:
    def __init__(self):
        self.tools: Dict[str, BaseTool] = {}
        self.register_default_tools()

    def register_default_tools(self):
        default_tools = [
            WeatherTool(),
            TimeTool(),
            CalculatorTool()
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