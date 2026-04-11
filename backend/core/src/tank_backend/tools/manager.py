"""ToolManager — owns the entire tool domain.

Creates policies, credentials, approval system, and tool groups internally.
External code only needs ``ToolManager(app_config, bus)`` and the public API.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from .base import BaseTool, ToolGroup, ToolInfo

logger = logging.getLogger("ToolManager")


class ToolManager:
    """Registry + domain owner for all tools.

    Owns: NetworkAccessPolicy, ServiceCredentialManager, AuditLogger,
    ApprovalManager, ToolApprovalPolicy, and all ToolGroups.
    """

    def __init__(self, app_config: Any, bus: Any = None) -> None:
        self.tools: dict[str, BaseTool] = {}
        self._groups: list[ToolGroup] = []
        self._bus = bus

        # --- Shared tool infrastructure ---
        from ..policy import (
            AuditLogger,
            NetworkAccessPolicy,
            ServiceCredentialManager,
        )

        net_raw = app_config.get_section("network_access", {})
        self._network_policy = NetworkAccessPolicy.from_dict(net_raw, bus=bus)
        self._credential_manager = ServiceCredentialManager.from_dict(
            net_raw.get("service_credentials", [])
        )

        audit_raw = app_config.get_section("audit", {})
        self._audit_logger = AuditLogger.from_dict(audit_raw)
        if bus is not None:
            self._audit_logger.subscribe(bus)

        # --- Approval system ---
        from ..agents.approval import ApprovalManager, ToolApprovalPolicy

        approval_raw = app_config.get_section("approval_policies") or {}
        self._approval_policy = ToolApprovalPolicy(
            always_approve=set(approval_raw.get("always_approve", [])),
            require_approval=set(approval_raw.get("require_approval", [])),
            require_approval_first_time=set(
                approval_raw.get("require_approval_first_time", [])
            ),
        )
        self._approval_manager = ApprovalManager()

        # --- Register tool groups ---
        from .groups import (
            DefaultToolGroup,
            FileToolGroup,
            SandboxToolGroup,
            SkillToolGroup,
            WebToolGroup,
            make_approval_callback,
        )

        self._register_group(DefaultToolGroup())

        sandbox_raw = app_config.get_section("sandbox", {})
        self._register_group(
            SandboxToolGroup(sandbox_raw, self._credential_manager)
        )

        approval_cb = make_approval_callback(self._approval_manager, bus)

        file_raw = app_config.get_section("file_access", {})
        self._register_group(FileToolGroup(file_raw, approval_cb, bus))

        self._register_group(
            WebToolGroup(
                self._credential_manager, self._network_policy, approval_cb,
            )
        )

        skills_raw = app_config.get_section("skills", {})
        self._skill_group = SkillToolGroup(skills_raw, bus, tool_manager=self)
        self._register_group(self._skill_group)

        logger.info(
            "ToolManager initialised: %d tools from %d groups",
            len(self.tools), len(self._groups),
        )

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def approval_manager(self) -> Any:
        """ApprovalManager for tool execution approval gates."""
        return self._approval_manager

    @property
    def approval_policy(self) -> Any:
        """ToolApprovalPolicy for deciding which tools need approval."""
        return self._approval_policy

    def set_agent_runner(self, runner: Any) -> None:
        """Register the agent tool and wire runner into skills.

        Called by Assistant after construction.
        """
        from ..agents.agent_tool import AgentTool

        self.register_tool(AgentTool(runner))
        self._skill_group.set_agent_runner(runner)

    def get_skill_catalog(self) -> str:
        """Return a compact skill catalog for system-reminder injection."""
        return self._skill_group.get_skill_catalog()

    # ------------------------------------------------------------------
    # Group lifecycle
    # ------------------------------------------------------------------

    def _register_group(self, group: ToolGroup) -> None:
        self._groups.append(group)
        for tool in group.create_tools():
            self.register_tool(tool)

    async def cleanup(self) -> None:
        """Delegate cleanup to all groups that own resources."""
        for group in self._groups:
            await group.cleanup()

    # ------------------------------------------------------------------
    # Tool registry
    # ------------------------------------------------------------------

    def register_tool(self, tool: BaseTool) -> None:
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
                    f"  - {param.name} ({param.type}, {required_str}): "
                    f"{param.description}"
                )

            tool_desc = f"**{info.name}**: {info.description}"
            if params_desc:
                tool_desc += "\n" + "\n".join(params_desc)

            descriptions.append(tool_desc)

        return "\n\n".join(descriptions)

    # ------------------------------------------------------------------
    # Tool execution
    # ------------------------------------------------------------------

    async def execute_tool(self, tool_name: str, **kwargs) -> dict[str, Any] | str:
        if tool_name not in self.tools:
            error_msg = (
                f"Tool '{tool_name}' not found. "
                f"Available tools: {list(self.tools.keys())}"
            )
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

    def get_openai_tools(
        self, exclude: set[str] | None = None,
    ) -> list[dict[str, Any]]:
        """Convert tools to OpenAI function calling format.

        Args:
            exclude: Optional set of tool names to omit from the result.
        """
        openai_tools = []

        for tool in self.tools.values():
            info = tool.get_info()

            if exclude and info.name in exclude:
                continue

            properties = {}
            required = []

            for param in info.parameters:
                properties[param.name] = {
                    "type": param.type,
                    "description": param.description,
                }
                if param.required:
                    required.append(param.name)

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
        """Execute tool from OpenAI function call format."""
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
                    logger.warning(
                        f"Could not parse parameters for tool call: {text}"
                    )

        return None
