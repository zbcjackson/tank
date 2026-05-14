"""ToolManager — owns the entire tool domain.

Creates policies, credentials, approval system, and tool groups internally.
External code only needs ``ToolManager(app_config, bus)`` and the public API.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from .base import BaseTool, ToolGroup, ToolInfo, ToolResult

logger = logging.getLogger("ToolManager")


class ToolManager:
    """Registry + domain owner for all tools.

    Owns: NetworkAccessPolicy, ServiceCredentialManager, AuditLogger,
    ToolApprovalPolicy, and all ToolGroups.
    """

    def __init__(
        self,
        app_config: Any,
        bus: Any = None,
        max_history_tokens: int = 8000,
    ) -> None:
        self.tools: dict[str, BaseTool] = {}
        self._groups: list[ToolGroup] = []
        self._bus = bus

        # --- Shared tool infrastructure ---
        from ..policy import (
            AuditLogger,
            FileAccessPolicy,
            NetworkAccessPolicy,
            ServiceCredentialManager,
        )

        self._network_policy = NetworkAccessPolicy(
            app_config.network_access, bus=bus,
        )
        self._credential_manager = ServiceCredentialManager(
            app_config.network_access.service_credentials,
        )

        self._file_policy = FileAccessPolicy(
            app_config.file_access, bus=bus,
        )

        self._audit_logger = AuditLogger(app_config.audit)
        if bus is not None:
            self._audit_logger.subscribe(bus)

        # --- Approval system ---
        from ..agents.approval import ToolApprovalPolicy
        from ..policy.command_security import CommandSecurityPolicy

        command_policy = CommandSecurityPolicy(app_config.command_security)

        # Create dedicated LLM for command security evaluation (if configured)
        command_llm = None
        llm_cfg = app_config.command_security.llm_evaluation
        if llm_cfg.enabled:
            try:
                from ..llm.profile import LLMProfile, create_llm_from_profile

                # Fall back to default LLM profile values when not specified
                default_profile = app_config.get_llm_profile("default")
                command_llm = create_llm_from_profile(LLMProfile(
                    name="command_security",
                    api_key=llm_cfg.api_key or default_profile.api_key,
                    model=llm_cfg.model or default_profile.model,
                    base_url=llm_cfg.base_url or default_profile.base_url,
                    temperature=0.0,
                    max_tokens=16,
                    extra_headers=default_profile.extra_headers,
                    stream_options=False,
                ))
                logger.info("Command security LLM enabled: %s", command_llm.model)
            except Exception as e:
                logger.warning("Failed to create command security LLM: %s", e)

        self._approval_policy = ToolApprovalPolicy(
            command_policy=command_policy,
            file_policy=self._file_policy,
            network_policy=self._network_policy,
            llm=command_llm,
        )

        # --- Register tool groups ---
        from .groups import (
            DefaultToolGroup,
            FileToolGroup,
            SandboxToolGroup,
            SkillToolGroup,
            WebToolGroup,
        )

        self._register_group(DefaultToolGroup())

        self._register_group(
            SandboxToolGroup(
                config=app_config.sandbox,
                credential_manager=self._credential_manager,
            )
        )

        self._register_group(
            FileToolGroup(
                config=app_config.file_access, bus=bus, policy=self._file_policy,
            )
        )

        self._register_group(
            WebToolGroup(
                self._credential_manager, self._network_policy,
            )
        )

        self._skill_group = SkillToolGroup(
            config=app_config.skills,
            bus=bus, tool_manager=self, max_history_tokens=max_history_tokens,
        )
        self._register_group(self._skill_group)

        # --- MCP servers (async connection deferred to async_init) ---
        self._mcp_group = None
        from ..mcp.client import load_mcp_configs
        from ..mcp.tool_group import MCPToolGroup

        mcp_configs = load_mcp_configs()
        if mcp_configs:
            self._mcp_group = MCPToolGroup(mcp_configs)
            self._groups.append(self._mcp_group)

        logger.info(
            "ToolManager initialised: %d tools from %d groups",
            len(self.tools), len(self._groups),
        )

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

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

    def set_job_manager(self, job_store: Any, scheduler: Any) -> None:
        """Register the job management tool for conversational job setup.

        Called by Assistant when the job scheduler is enabled.
        """
        from .job_tools import JobManagementTool

        self.register_tool(JobManagementTool(job_store, scheduler))

    def get_skill_catalog(self) -> str:
        """Return a compact skill catalog for system-reminder injection."""
        return self._skill_group.get_skill_catalog()

    def reload_skills(self) -> dict[str, list[str]]:
        """Rescan skill directories, re-review, return diff of changes."""
        return self._skill_group.reload_skills()

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

    async def connect_mcp_servers(self) -> None:
        """Connect to configured MCP servers and register their tools.

        Call after construction (e.g. in Assistant.start or FastAPI lifespan).
        """
        if self._mcp_group is None:
            return
        errors = await self._mcp_group.connect_servers()
        for tool in self._mcp_group.create_tools():
            self.register_tool(tool)
        # MCP approval overrides are no longer needed — command tools use
        # CommandSecurityPolicy, and all other tools are auto-approved.
        # Log any overrides for visibility but don't apply them.
        overrides = self._mcp_group.get_approval_overrides()
        if overrides:
            logger.info(
                "MCP approval overrides ignored (command security handles shell tools): %s",
                overrides,
            )
        if errors:
            logger.warning(f"MCP servers with errors: {list(errors.keys())}")

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

    async def execute_tool(self, tool_name: str, **kwargs) -> ToolResult | str:
        if tool_name not in self.tools:
            error_msg = (
                f"Tool '{tool_name}' not found. "
                f"Available tools: {list(self.tools.keys())}"
            )
            logger.error(error_msg)
            return ToolResult(
                content=error_msg, display=error_msg, error=True,
            )

        try:
            tool = self.tools[tool_name]
            logger.info(f"Executing tool: {tool_name} with parameters: {kwargs}")
            result = await tool.execute(**kwargs)
            logger.info(f"Tool {tool_name} executed successfully")
        except Exception as e:
            error_msg = f"Error executing tool '{tool_name}': {str(e)}"
            logger.error(error_msg)
            return ToolResult(content=error_msg, display=error_msg, error=True)

        # Phase 16: when a tool returns a ``ToolResult`` that carries
        # non-text ``ContentBlock`` s (images today, more kinds later),
        # also post them as an ``outbound_attachment`` bus event so
        # they're delivered to the user through the connector that
        # opened this session. The LLM still sees the same blocks via
        # the ``user``-role follow-up message (see
        # ``llm._tool_result_to_llm``); this hook is purely about
        # surfacing the image on the end-user side.
        #
        # Bus availability is defensive — some ToolManager instances
        # (e.g. in narrow unit tests) are built with ``bus=None`` and
        # the outbound path just falls away.
        if self._bus is not None and isinstance(result, ToolResult):
            self._emit_tool_output_attachments(tool_name, result)

        return result

    def _emit_tool_output_attachments(
        self, tool_name: str, result: ToolResult,
    ) -> None:
        """Publish image blocks from a tool result as an outbound attachment.

        Keeps the bus payload aligned with
        :meth:`~tank_backend.core.assistant.Assistant.emit_outbound_attachment`
        so :class:`~tank_backend.connectors.manager._ImageDispatcher`
        can consume both paths through the same subscriber. The tool's
        ``display`` string becomes the caption — most tools use
        ``display`` for the short human-readable summary, which is
        exactly the right thing to render alongside an image.
        """
        from ..core.content import ImageBlock  # local to avoid cycles
        from ..pipeline.bus import BusMessage

        blocks = result.to_blocks()
        image_blocks = [b for b in blocks if isinstance(b, ImageBlock)]
        if not image_blocks:
            return

        caption = result.display or None
        try:
            self._bus.post(
                BusMessage(
                    type="outbound_attachment",
                    source=f"tool:{tool_name}",
                    payload={
                        "msg_id": None,
                        "blocks": image_blocks,
                        "caption": caption,
                    },
                )
            )
        except Exception:
            # Don't let a bus publish failure swallow the tool's result.
            # Worst case the user doesn't see the image; the tool's
            # text content still reaches the LLM.
            logger.exception(
                "ToolManager: failed to emit outbound_attachment for %s",
                tool_name,
            )

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

            raw_schema = tool.get_raw_schema()
            if raw_schema is not None:
                parameters = raw_schema
            else:
                properties = {}
                required = []

                for param in info.parameters:
                    properties[param.name] = {
                        "type": param.type,
                        "description": param.description,
                    }
                    if param.required:
                        required.append(param.name)

                parameters = {
                    "type": "object",
                    "properties": properties,
                    "required": required,
                }

            openai_tool = {
                "type": "function",
                "function": {
                    "name": info.name,
                    "description": info.description,
                    "parameters": parameters,
                },
            }

            openai_tools.append(openai_tool)

        return openai_tools

    async def execute_openai_tool_call(self, tool_call) -> ToolResult | str:
        """Execute tool from OpenAI function call format."""
        function_name = tool_call.function.name
        try:
            arguments = json.loads(tool_call.function.arguments)
        except json.JSONDecodeError:
            return ToolResult(
                content=f"Could not parse arguments for {function_name}",
                display=f"Could not parse arguments for {function_name}",
                error=True,
            )

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
