from textual.widgets import Static, Markdown
from textual.containers import Container, Vertical
from textual.app import ComposeResult
from typing import Dict, Optional
import uuid
from ...core.events import UpdateType, DisplayMessage

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
        self.current_text_accumulated = ""
        self.current_thought_accumulated = ""

    def compose(self) -> ComposeResult:
        yield Static("[bold blue]Tank:[/bold blue]", classes="assistant-header")

    def update_from_message(self, msg: DisplayMessage):
        # Determine if we need a new widget or update the last one
        is_new_type = msg.update_type != self.last_update_type
        
        if msg.update_type == UpdateType.THOUGHT:
            if is_new_type:
                self.current_thought_accumulated = msg.text
                new_thought = Static(f"💭 {self.current_thought_accumulated}", classes="thought-entry")
                self.mount(new_thought)
                self.last_widget = new_thought
            else:
                self.current_thought_accumulated += msg.text
                if self.last_widget:
                    self.last_widget.update(f"💭 {self.current_thought_accumulated}")
        
        elif msg.update_type == UpdateType.TOOL_CALL:
            # For tool calls, if we get updates for the SAME tool call (same index), update it
            name = msg.metadata.get("name", "")
            args = msg.metadata.get("arguments", "")
            content = f"🛠️ Calling: {name}({args[:50]}...)"
            
            # If the last thing was a tool call (likely the start of this one), update it
            if self.last_update_type == UpdateType.TOOL_CALL and self.last_widget:
                 self.last_widget.update(content)
            else:
                new_tool = Static(content, classes="tool-entry")
                self.mount(new_tool)
                self.last_widget = new_tool

        elif msg.update_type == UpdateType.TOOL_RESULT:
            name = msg.metadata.get("name", "")
            result = msg.text
            summary = f"✅ Result [{name}]: {result[:200]}"
            new_result = Static(summary, classes="tool-result-entry")
            self.mount(new_result)
            self.last_widget = new_result
            
        elif msg.update_type == UpdateType.TEXT:
            if is_new_type:
                self.current_text_accumulated = msg.text
                new_text = Markdown(self.current_text_accumulated, classes="text-entry")
                self.mount(new_text)
                self.last_widget = new_text
            else:
                self.current_text_accumulated += msg.text
                if isinstance(self.last_widget, Markdown):
                    self.last_widget.update(self.current_text_accumulated)

        self.last_update_type = msg.update_type

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
        yield Container(id="conversation_container")
        
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
                
                self.scroll_end(animate=False)
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
            
        self.scroll_end(animate=False)