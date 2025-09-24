import ast
import operator as op
import logging
from typing import Dict, Any
from .base import BaseTool, ToolInfo, ToolParameter

logger = logging.getLogger(__name__)


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