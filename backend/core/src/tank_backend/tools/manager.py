from __future__ import annotations

import json
import logging
from typing import Any

from .base import BaseTool, ToolInfo
from .calculator import CalculatorTool
from .time import TimeTool
from .weather import WeatherTool
from .web_scraper import WebScraperTool
from .web_search import WebSearchTool

logger = logging.getLogger("ToolManager")


class ToolManager:
    def __init__(
        self,
        serper_api_key: str = None,
        network_policy: Any = None,
        audit_logger: Any = None,
    ):
        self.serper_api_key = serper_api_key
        self._network_policy = network_policy
        self._audit_logger = audit_logger
        self.tools: dict[str, BaseTool] = {}
        self.register_default_tools()

    def register_default_tools(self):
        default_tools = [
            WeatherTool(),
            TimeTool(),
            CalculatorTool(),
        ]

        for tool in default_tools:
            self.register_tool(tool)

    def register_web_tools(
        self,
        approval_manager: Any = None,
        bus: Any = None,
    ) -> None:
        """Register web tools with network policy and approval wiring.

        Called after ApprovalManager exists so ``require_approval`` hosts
        can trigger the approval flow.

        Args:
            approval_manager: Optional ApprovalManager for host-specific approval.
            bus: Optional pipeline Bus for posting approval UI notifications.
        """
        callback = None
        if approval_manager is not None:
            callback = _make_file_approval_callback(approval_manager, bus)

        self.register_tool(WebScraperTool(
            network_policy=self._network_policy,
            audit_logger=self._audit_logger,
            approval_callback=callback,
        ))

        if self.serper_api_key:
            self.register_tool(WebSearchTool(
                self.serper_api_key,
                network_policy=self._network_policy,
                audit_logger=self._audit_logger,
                approval_callback=callback,
            ))

    def register_sandbox_tools(self, sandbox: Any) -> None:
        """Register sandbox tools with a Sandbox backend.

        ``sandbox_exec`` and ``sandbox_process`` are registered on all
        backends.  ``sandbox_bash`` is only registered when the backend
        supports persistent sessions (Docker).

        Args:
            sandbox: A Sandbox protocol implementation (DockerSandbox,
                SeatbeltSandbox, or BubblewrapSandbox).
        """
        from .sandbox_exec import SandboxExecTool
        from .sandbox_process import SandboxProcessTool

        self.register_tool(SandboxExecTool(sandbox))
        self.register_tool(SandboxProcessTool(sandbox))

        # sandbox_bash requires persistent sessions (Docker-only)
        caps = getattr(sandbox, "capabilities", None)
        if caps is not None and caps.persistent_sessions:
            from .sandbox_bash import SandboxBashTool

            self.register_tool(SandboxBashTool(sandbox))
            logger.info("sandbox_bash registered (persistent sessions available)")
        else:
            logger.info("sandbox_bash skipped (backend has no persistent sessions)")

    def register_file_tools(
        self,
        config: dict | None = None,
        approval_manager: Any = None,
        bus: Any = None,
        audit_logger: Any = None,
    ) -> None:
        """Register file tools from config, with approval and bus wiring.

        Args:
            config: Parsed ``file_access:`` section from config.yaml.
            approval_manager: Optional ApprovalManager for path-specific approval.
            bus: Optional pipeline Bus for posting approval UI notifications.
            audit_logger: Optional AuditLogger for structured operation logging.
        """
        from ..policy import BackupManager, FileAccessPolicy
        from .file_delete import FileDeleteTool
        from .file_list import FileListTool
        from .file_read import FileReadTool
        from .file_write import FileWriteTool

        config = config or {}
        policy = FileAccessPolicy.from_dict(config)
        backup = BackupManager.from_dict(config.get("backup", {}))

        callback = None
        if approval_manager is not None:
            callback = _make_file_approval_callback(approval_manager, bus)

        for tool in [
            FileReadTool(policy, approval_callback=callback, audit_logger=audit_logger),
            FileWriteTool(policy, backup, approval_callback=callback, audit_logger=audit_logger),
            FileDeleteTool(policy, backup, approval_callback=callback, audit_logger=audit_logger),
            FileListTool(policy, approval_callback=callback, audit_logger=audit_logger),
        ]:
            self.register_tool(tool)

    def register_tool(self, tool: BaseTool):
        info = tool.get_info()
        self.tools[info.name] = tool
        logger.info(f"Registered tool: {info.name}")

    def get_tool_info(self) -> list[ToolInfo]:
        return [tool.get_info() for tool in self.tools.values()]

    def get_tools_description(self) -> str:
        descriptions = []
        for tool in self.tools.values():
            info = tool.get_info()
            params_desc = []
            for param in info.parameters:
                required_str = "required" if param.required else "optional"
                params_desc.append(
                    f"  - {param.name} ({param.type}, {required_str}): {param.description}"
                )

            tool_desc = f"**{info.name}**: {info.description}"
            if params_desc:
                tool_desc += "\n" + "\n".join(params_desc)

            descriptions.append(tool_desc)

        return "\n\n".join(descriptions)

    async def execute_tool(self, tool_name: str, **kwargs) -> dict[str, Any]:
        if tool_name not in self.tools:
            error_msg = f"Tool '{tool_name}' not found. Available tools: {list(self.tools.keys())}"
            logger.error(error_msg)
            return {"error": error_msg, "available_tools": list(self.tools.keys())}

        try:
            tool = self.tools[tool_name]
            logger.info(f"Executing tool: {tool_name} with parameters: {kwargs}")
            result = await tool.execute(**kwargs)
            logger.info(f"Tool {tool_name} executed successfully")
            return result

        except Exception as e:
            error_msg = f"Error executing tool '{tool_name}': {str(e)}"
            logger.error(error_msg)
            return {"error": error_msg, "tool_name": tool_name, "parameters": kwargs}

    def get_openai_tools(self) -> list[dict[str, Any]]:
        """Convert tools to OpenAI function calling format"""
        openai_tools = []

        for tool in self.tools.values():
            info = tool.get_info()

            # Build parameters schema
            properties = {}
            required = []

            for param in info.parameters:
                properties[param.name] = {"type": param.type, "description": param.description}
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
                        "required": required,
                    },
                },
            }

            openai_tools.append(openai_tool)

        return openai_tools

    async def execute_openai_tool_call(self, tool_call) -> dict[str, Any]:
        """Execute tool from OpenAI function call format"""
        function_name = tool_call.function.name
        try:
            arguments = json.loads(tool_call.function.arguments)
        except json.JSONDecodeError:
            return {
                "error": f"Could not parse arguments for {function_name}",
                "arguments": tool_call.function.arguments,
            }

        return await self.execute_tool(function_name, **arguments)

    def parse_tool_call(self, text: str) -> dict[str, Any] | None:
        import re

        tool_pattern = r"(\w+)\((.*?)\)"
        match = re.search(tool_pattern, text)

        if match:
            tool_name = match.group(1)
            params_str = match.group(2)

            if tool_name in self.tools:
                try:
                    if params_str.strip():
                        if params_str.strip().startswith("{"):
                            params = json.loads(params_str)
                        else:
                            params = {"input": params_str.strip().strip("'\"")}
                    else:
                        params = {}

                    return {"tool_name": tool_name, "parameters": params}
                except json.JSONDecodeError:
                    logger.warning(f"Could not parse parameters for tool call: {text}")

        return None


def _make_file_approval_callback(approval_manager: Any, bus: Any = None) -> Any:
    """Create an ApprovalCallback that bridges to ApprovalManager + Bus.

    Returns an async callable matching the ``ApprovalCallback`` protocol.
    """

    async def callback(
        tool_name: str, path: str, operation: str, reason: str,
    ) -> bool:
        from ..agents.approval import ApprovalRequest, make_approval_id, request_with_notification

        request = ApprovalRequest(
            approval_id=make_approval_id(),
            tool_name=tool_name,
            tool_args={"path": path, "operation": operation},
            description=f"{operation} {path} ({reason})",
            session_id="file_access",
        )
        result = await request_with_notification(approval_manager, request, bus)
        return result.approved

    return callback
