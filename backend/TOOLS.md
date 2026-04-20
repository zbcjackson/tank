# Tool Development Guide

## Overview

Tools extend the assistant's capabilities by providing access to external systems (files, web, commands) and utilities (calculator, time). Each tool is a Python class that inherits from `BaseTool` and returns strongly-typed `ToolResult` objects.

## Architecture

```
tool.execute() → ToolResult | str
    ↓
llm.py: _tool_result_to_str(result) → (llm_content, ui_display)
    ↓
LLM gets llm_content (full data, never truncated)
UI gets ui_display (concise summary for tool card)
```

- `ToolResult.content` — Complete data for the LLM (typically `json.dumps` of structured result)
- `ToolResult.display` — Human-friendly summary for the UI tool card
- Plain `str` return — For tools that produce text directly (e.g. skill instructions)

## Creating a Tool

### 1. Define the tool class

```python
import json
from .base import BaseTool, ToolInfo, ToolParameter, ToolResult

class MyTool(BaseTool):
    def get_info(self) -> ToolInfo:
        return ToolInfo(
            name="my_tool",
            description="What this tool does",
            parameters=[
                ToolParameter(
                    name="query",
                    type="string",
                    description="The search query",
                    required=True,
                ),
                ToolParameter(
                    name="limit",
                    type="integer",
                    description="Max results",
                    required=False,
                    default=10,
                ),
            ],
        )

    async def execute(self, query: str, limit: int = 10) -> ToolResult:
        try:
            results = await do_search(query, limit)
            return ToolResult(
                content=json.dumps(
                    {"query": query, "results": results},
                    ensure_ascii=False,
                ),
                display=f"Found {len(results)} results for '{query}'",
            )
        except Exception as e:
            return ToolResult(
                content=json.dumps(
                    {"query": query, "error": str(e)},
                    ensure_ascii=False,
                ),
                display=f"Search failed: {e}",
                error=True,
            )
```

### 2. Add to a ToolGroup

Tools are organized into groups that share construction dependencies:

```python
# In tools/groups.py
class MyToolGroup(ToolGroup):
    def __init__(self, config: dict[str, Any]) -> None:
        self._config = config

    def create_tools(self) -> list[BaseTool]:
        if not self._config.get("enabled", True):
            return []
        return [MyTool(self._config)]
```

Register the group in `ToolManager.__init__()`.

### 3. Write tests

```python
import json
import pytest
from tank_backend.tools.base import ToolResult
from tank_backend.tools.my_tool import MyTool

async def test_success():
    tool = MyTool()
    result = await tool.execute(query="test")

    assert isinstance(result, ToolResult)
    assert not result.error

    data = json.loads(result.content)
    assert data["query"] == "test"
    assert "results" in data
    assert len(result.display) < 300

async def test_error():
    tool = MyTool()
    result = await tool.execute(query="")

    assert isinstance(result, ToolResult)
    assert result.error

    data = json.loads(result.content)
    assert "error" in data
```

## Return Type Conventions

### ToolResult (recommended for all tools)

```python
return ToolResult(
    content=json.dumps(data, ensure_ascii=False),  # Full data for LLM
    display="Human-friendly summary",               # Concise UI text
    error=False,                                     # True for errors
)
```

### str (for skill instructions only)

```python
return f"SKILL ACTIVATED: {name}\n{instructions}"
```

### Never return dict

Dicts with implicit keys caused a class of bugs where tool data was silently hidden from the LLM. Use `ToolResult` for type safety.

## Common Patterns

### File access with policy

```python
class MyFileTool(BaseTool):
    def __init__(
        self,
        policy: FileAccessPolicy,
        approval_callback: ApprovalCallback | None = None,
    ) -> None:
        self._policy = policy
        self._approval_callback = approval_callback

    async def execute(self, path: str) -> ToolResult:
        decision = self._policy.evaluate(path, "read")
        if decision.level == "deny":
            return ToolResult(
                content=json.dumps({"error": f"Access denied: {path}"}),
                display=f"Cannot access {path}: {decision.reason}",
                error=True,
            )
        if decision.level == "require_approval":
            approved = await self._request_approval(path, "read", decision.reason)
            if not approved:
                return ToolResult(
                    content=json.dumps({"error": f"Denied: {path}"}),
                    display=f"User denied access to {path}",
                    error=True,
                )
        # ... proceed with operation
```

### Network access with policy

```python
host = parsed_url.netloc.lower()
if self._network_policy is not None:
    decision = self._network_policy.evaluate(host)
    if decision.level == "deny":
        return ToolResult(
            content=json.dumps({"error": f"Blocked: {host}"}),
            display=f"Network policy blocks {host}",
            error=True,
        )
```

### Custom OpenAI schema

Override `get_raw_schema()` when `ToolParameter` is too limited:

```python
def get_raw_schema(self) -> dict | None:
    return {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "File path"},
            "options": {
                "type": "object",
                "properties": {
                    "encoding": {"type": "string", "default": "utf-8"},
                },
            },
        },
        "required": ["path"],
    }
```

## ToolResult Design Rationale

The `ToolResult` dataclass was introduced to fix a critical bug where tool results were silently truncated before reaching the LLM. The previous design used dicts with an implicit `"message"` key convention — if a dict had a `"message"` key, only that string was sent to the LLM, discarding all other data.

This caused tools like `file_read` to return `"Read /path (1234 chars)"` to the LLM instead of the actual file content.

`ToolResult` solves this by:
- **Explicit separation** — `content` (LLM) and `display` (UI) are distinct fields
- **Type safety** — Can't accidentally add a field that changes behavior
- **Immutability** — `frozen=True` prevents accidental mutation
- **Self-documenting** — The dataclass makes the contract obvious
