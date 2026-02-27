from textual.widgets import Static, Markdown
from textual.containers import Container, Vertical, ScrollableContainer
from textual.app import ComposeResult
from typing import Dict, Optional, Union
import uuid
from ...core.events import UpdateType, DisplayMessage
from ...schemas import WebsocketMessage, MessageType


class AssistantMessageBlock(Vertical):
    DEFAULT_CSS = """
    AssistantMessageBlock {
        width: 100%;
        height: auto;
        padding: 0 1;
        margin: 0 0 1 0;
    }

    .assistant-header {
        color: $accent;
        text-style: bold;
        margin-bottom: 0;
    }

    .thought-entry {
        color: $text-muted;
        text-style: italic;
        margin: 0 0 0 2;
    }

    .tool-entry {
        background: $surface;
        color: $primary;
        margin: 0 0 0 2;
        padding: 0 1;
        border-left: solid $primary;
    }

    .tool-result-entry {
        background: $surface;
        color: $success;
        margin: 0 0 1 2;
        padding: 0 1;
        border-left: solid $success;
    }

    .text-entry {
        margin: 0 0 0 2;
    }
    """

    def __init__(self, msg_id: str):
        super().__init__(id=msg_id)
        self.last_update_type: Optional[UpdateType] = None
        self.last_widget: Optional[Static] = None
        self.last_step_id: Optional[str] = None
        self.current_text_accumulated = ""
        self.current_thought_accumulated = ""
        # Track widgets by step_id for tool call/result pairing
        self.step_widgets: Dict[str, Static] = {}

    def compose(self) -> ComposeResult:
        yield Static("[bold blue]Tank:[/bold blue]", classes="assistant-header")

    def update_from_message(self, msg: DisplayMessage):
        # Get step_id from metadata (server-provided)
        step_id = msg.metadata.get("step_id")

        # Fallback: compute step_id if not provided
        if not step_id:
            turn = msg.metadata.get("turn", 0)
            step_type = msg.update_type.name.lower()
            step_id = f"{msg.msg_id}_{step_type}_{turn}"
            if msg.update_type == UpdateType.TOOL:
                index = msg.metadata.get("index", 0)
                step_id += f"_{index}"

        # Determine if we need a new widget or update existing
        is_new_step = step_id != self.last_step_id

        if msg.update_type == UpdateType.THOUGHT:
            if is_new_step:
                self.current_thought_accumulated = msg.text
                new_thought = Static(f"💭 {self.current_thought_accumulated}", classes="thought-entry")
                self.mount(new_thought)
                self.last_widget = new_thought
                self.step_widgets[step_id] = new_thought
            else:
                self.current_thought_accumulated += msg.text
                if step_id in self.step_widgets:
                    self.step_widgets[step_id].update(f"💭 {self.current_thought_accumulated}")

        elif msg.update_type == UpdateType.TOOL:
            name = msg.metadata.get("name", "")
            args = msg.metadata.get("arguments", "")
            status = msg.metadata.get("status", "calling")
            result = msg.text

            # Determine display based on status
            if status in ("success", "error"):
                summary = f"✅ Result [{name}]: {result[:200]}" if status == "success" else f"❌ Error [{name}]: {result[:200]}"
                css_class = "tool-result-entry"
            else:
                content = f"🛠️ {status.capitalize()}: {name}({args[:50]}...)"
                summary = content
                css_class = "tool-entry"

            if step_id in self.step_widgets:
                self.step_widgets[step_id].update(summary)
                # Swap CSS class when transitioning to result
                if status in ("success", "error"):
                    self.step_widgets[step_id].remove_class("tool-entry")
                    self.step_widgets[step_id].add_class("tool-result-entry")
            else:
                new_tool = Static(summary, classes=css_class)
                self.mount(new_tool)
                self.last_widget = new_tool
                self.step_widgets[step_id] = new_tool

        elif msg.update_type == UpdateType.TEXT:
            if is_new_step:
                self.current_text_accumulated = msg.text
                new_text = Markdown(self.current_text_accumulated, classes="text-entry")
                self.mount(new_text)
                self.last_widget = new_text
                self.step_widgets[step_id] = new_text
            else:
                self.current_text_accumulated += msg.text
                if step_id in self.step_widgets and isinstance(self.step_widgets[step_id], Markdown):
                    self.step_widgets[step_id].update(self.current_text_accumulated)

        self.last_update_type = msg.update_type
        self.last_step_id = step_id

class ConversationArea(Container):
    DEFAULT_CSS = """
    ConversationArea {
        height: 1fr;
        border: solid $accent;
        margin: 0 1;
        overflow-y: scroll;
    }
    
    .user-message {
        width: 100%;
        height: auto;
        padding: 0 1;
        margin: 0 0 1 0;
        color: white;
        text-style: bold;
    }
    """

    def compose(self) -> ComposeResult:
        yield ScrollableContainer(id="conversation_container")
        
    def write(self, msg: DisplayMessage) -> None:
        container = self.query_one("#conversation_container")

        if msg.msg_id:
            # Try to find existing widget
            try:
                if msg.is_user:
                    existing = self.query_one(f"#{msg.msg_id}", Static)
                    existing.update(f"[bold blue]You:[/bold blue] {msg.text}")
                else:
                    existing = self.query_one(f"#{msg.msg_id}", AssistantMessageBlock)
                    existing.update_from_message(msg)

                # After updating content, scroll to the new end
                # Use call_after_refresh to ensure the layout has updated
                self.call_after_refresh(container.scroll_end, animate=False)
                return
            except Exception:
                pass

        # Create new
        if msg.is_user:
            new_entry = Static(f"[bold blue]You:[/bold blue] {msg.text}", classes="user-message")
            if msg.msg_id:
                new_entry.id = msg.msg_id
            container.mount(new_entry)
        else:
            new_entry = AssistantMessageBlock(msg_id=msg.msg_id or f"brain_{uuid.uuid4().hex[:8]}")
            container.mount(new_entry)
            new_entry.update_from_message(msg)

        # Scroll after mounting new content
        self.call_after_refresh(container.scroll_end, animate=False)

    def write_ws_message(self, msg: WebsocketMessage) -> None:
        """Render a WebSocket message by converting to DisplayMessage."""
        update_type = UpdateType.TEXT
        if msg.type == MessageType.UPDATE:
            raw = msg.metadata.get("update_type", "")
            if "THOUGHT" in raw:
                update_type = UpdateType.THOUGHT
            elif "TOOL" in raw:
                update_type = UpdateType.TOOL

        display_msg = DisplayMessage(
            speaker="You" if msg.is_user else "Tank",
            text=msg.content,
            is_user=msg.is_user,
            is_final=msg.is_final,
            msg_id=msg.msg_id,
            update_type=update_type,
            metadata=msg.metadata.copy() if msg.metadata else {},
        )
        self.write(display_msg)
