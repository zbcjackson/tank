"""Isolated E2E process: actual SDK, dispatch, status/stop, Bus and notification frames."""

from __future__ import annotations

import asyncio
import base64
import io
import json
import sys
import tempfile
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

from PIL import Image
from yutori.navigator.macos.types import CancellationLatch

from agent_n2_sdk.agent import N2SdkSubAgent
from agent_n2_sdk.config import N2SdkConfig
from agent_n2_sdk.environment import GuardedComputer
from tank_backend.agents.agent_tool import AgentTool
from tank_backend.agents.approval import PendingToolCallStore
from tank_backend.agents.definition import AgentDefinition
from tank_backend.agents.notification_hub import NotificationHub, NotificationHubConfig
from tank_backend.agents.resources import DesktopResource
from tank_backend.agents.runner import AgentRunner
from tank_backend.agents.store import WorkerStore
from tank_backend.agents.supervisor import WorkerSupervisor
from tank_backend.agents.worker_tools import AgentStatusTool, AgentStopTool
from tank_backend.api.router import _worker_activity_to_ws_msg, _worker_event_to_ws_msg
from tank_backend.config.app_config import AppConfig
from tank_backend.config.models import SkillsConfig, AuditConfig
from tank_backend.persistence import Base, Database
from tank_backend.pipeline.bus import Bus
from tank_backend.plugin.manifest import ExtensionManifest
from tank_backend.plugin.registry import ExtensionRegistry
from tank_backend.tools.base import ToolContext, ToolResult
from tank_backend.tools.confirm_action import ConfirmActionTool
from tank_backend.tools.manager import ToolManager


class Computer:
    def __init__(self) -> None:
        self.cancellation = CancellationLatch()
        self.closed = False

    async def __aenter__(self) -> Computer:
        return self

    async def get_dimensions(self) -> tuple[int, int]:
        return 10, 10

    async def screenshot(self) -> str:
        image = io.BytesIO()
        Image.new("RGB", (10, 10)).save(image, format="PNG")
        return base64.b64encode(image.getvalue()).decode()

    async def aclose(self) -> None:
        self.closed = True


class Client:
    def __init__(self, outcome: str) -> None:
        self.outcome = outcome
        self.started = asyncio.Event()
        self.calls = 0
        self.closed = False

    async def create(self, **kwargs: Any) -> dict[str, Any]:
        self.started.set()
        self.calls += 1
        if self.outcome == "stopped":
            await asyncio.Event().wait()
        if self.outcome == "failed":
            raise RuntimeError("fake API failure")
        message: dict[str, Any] = {"role": "assistant", "content": "verified"}
        if self.calls == 1:
            message["tool_calls"] = [
                {
                    "id": "observe",
                    "type": "function",
                    "function": {
                        "name": "computer_batch",
                        "arguments": '{"actions":[{"name":"screenshot","arguments":{}}]}',
                    },
                }
            ]
        return {
            "choices": [{"message": message, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 5, "completion_tokens": 2, "total_tokens": 7},
        }

    async def aclose(self) -> None:
        self.closed = True


def payload(result: ToolResult) -> dict[str, Any]:
    assert isinstance(result.content, str)
    return json.loads(result.content)


async def dispatch(outcome: str, directory: Path) -> dict[str, Any]:
    config = AppConfig(
        skills=SkillsConfig(enabled=False, dirs=[]), audit=AuditConfig(enabled=False)
    )
    bus, pending = Bus(), PendingToolCallStore()
    manager = ToolManager(config, bus=bus)
    registry = ExtensionRegistry()
    computer, client = Computer(), Client(outcome)
    instances = []

    def create(_config: dict[str, Any]) -> N2SdkSubAgent:
        plugin = N2SdkSubAgent(
            N2SdkConfig(api_key="fake", screenshot_delay=0),
            computer_factory=lambda ctx: GuardedComputer(computer, ctx),
            client_factory=lambda cfg: client,
        )
        instances.append(plugin)
        return plugin

    # Factory injection is confined to this test process; no fake production plugin.
    setattr(sys.modules[__name__], "create", create)
    registry.register(
        "agent-n2-sdk",
        ExtensionManifest(
            "agent",
            "subagent",
            f"{__name__}:create",
            permissions=("desktop", "shell", "filesystem", "network"),
        ),
    )
    definition = AgentDefinition(
        "n2_sdk", "SDK", "", extension="agent-n2-sdk:agent", background=True
    )
    runner = AgentRunner(
        MagicMock(),
        manager,
        bus,
        manager.approval_policy,
        pending,
        {"n2_sdk": definition},
        registry=registry,
        app_config=config,
        desktop_resource=DesktopResource(),
    )
    db = Database(f"sqlite+pysqlite:///{directory}/tank.db")
    Base.metadata.create_all(db.engine)
    store = WorkerStore(db)
    supervisor = WorkerSupervisor(runner, store, bus=bus)
    hub = NotificationHub(bus, NotificationHubConfig(proactive_delivery=False))
    frames = []

    def worker(message: Any) -> None:
        converter = (
            _worker_activity_to_ws_msg
            if message.type == "worker_activity"
            else _worker_event_to_ws_msg
        )
        frame = converter(message.payload, "test-conversation")
        if frame is not None:
            frames.append(frame.model_dump(mode="json"))

    bus.subscribe("worker", worker)
    bus.subscribe("worker_activity", worker)
    tool = AgentTool(runner, supervisor=supervisor)
    manager.register_tool(tool)
    ctx = ToolContext(session_id="test-conversation")
    parked = await tool.execute(
        ctx=ctx, prompt="observe fake desktop", subagent_type="n2_sdk"
    )
    assert "APPROVAL REQUIRED" in str(parked.content) and not instances
    confirm = ConfirmActionTool(pending, manager, manager.approval_policy)
    # Preserve the conversation through the actual approved tool re-entry.
    manager.set_session_id("test-conversation")
    result = await confirm.execute(approved=outcome != "rejected")
    if outcome == "rejected":
        assert payload(result)["status"] == "rejected" and not instances
        db.dispose()
        return {
            "status": "rejected",
            "started": False,
            "frames": [],
            "notifications": [],
        }
    task_id = payload(result)["task_id"]
    if outcome == "stopped":
        await client.started.wait()
        await AgentStopTool(store, supervisor).execute(task_id=task_id)
    await supervisor.wait(task_id, timeout=5)
    bus.poll()
    status = payload(await AgentStatusTool(store, supervisor).execute(task_id=task_id))
    notifications = hub.drain("test-conversation")
    expected = {"approved": "completed", "stopped": "cancelled", "failed": "failed"}[
        outcome
    ]
    assert status["status"] == expected and computer.closed and client.closed
    assert len(notifications) == 1 and notifications[0].metadata["status"] == expected
    if outcome == "approved":
        assert any(
            f.get("metadata", {}).get("tool_name") == "computer_batch" for f in frames
        )
    db.dispose()
    return {
        "status": expected,
        "started": True,
        "frames": frames,
        "notifications": [n.summary for n in notifications],
        "cleanup": "confirmed",
    }


if __name__ == "__main__":
    with tempfile.TemporaryDirectory(prefix="tank-sdk-e2e-") as directory:
        print(
            json.dumps(
                asyncio.run(dispatch(sys.argv[1], Path(directory))), ensure_ascii=False
            )
        )
