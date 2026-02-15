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
        background: $boost;
        border-left: solid $accent;
    }
    
    .thought-section {
        color: $text-muted;
        text-style: italic;
        padding: 0 1;
        margin: 0 0 1 0;
        border-left: solid gray;
    }
    
    .tools-section {
        background: $surface;
        padding: 0 1;
        margin: 0 0 1 0;
        border: solid $primary;
    }
    
    .tool-entry {
        padding: 0 1;
        border-bottom: solid gray;
    }
    
    .response-section {
        padding: 0 1;
    }
    """
    
    def __init__(self, msg_id: str):
        super().__init__(id=msg_id)
        self.thought_text = ""
        self.response_text = ""
        self.tool_calls: Dict[int, Dict] = {}

    def compose(self) -> ComposeResult:
        yield Static("", id="thought", classes="thought-section")
        yield Vertical(id="tools", classes="tools-section")
        yield Markdown("", id="response", classes="response-section")

    def on_mount(self):
        # Initial state: hide optional sections
        self.query_one("#thought").display = False
        self.query_one("#tools").display = False

    def update_from_message(self, msg: DisplayMessage):
        if msg.update_type == UpdateType.THOUGHT:
            self.thought_text += msg.text
            thought_widget = self.query_one("#thought", Static)
            thought_widget.update(f"💭 {self.thought_text}")
            thought_widget.display = True
        
        elif msg.update_type == UpdateType.TOOL_CALL:
            idx = msg.metadata.get("index", 0)
            self.tool_calls[idx] = msg.metadata
            self.query_one("#tools").display = True
            self._update_tools_section()
            
        elif msg.update_type == UpdateType.TOOL_RESULT:
            idx = msg.metadata.get("index", 0)
            if idx in self.tool_calls:
                self.tool_calls[idx].update(msg.metadata)
                self.tool_calls[idx]["result"] = msg.text
            self.query_one("#tools").display = True
            self._update_tools_section()
            
        elif msg.update_type == UpdateType.TEXT:
            self.response_text += msg.text
            self.query_one("#response", Markdown).update(self.response_text)

    def _update_tools_section(self):
        tools_container = self.query_one("#tools", Vertical)
        # Clear and rebuild or update intelligently. Rebuild is easier for now.
        # But in Textual, rebuild means unmount/mount. 
        # For simplicity, we'll just update a static summary if it's too complex.
        content = "🛠️ **Tools Execution**\n"
        for idx in sorted(self.tool_calls.keys()):
            tc = self.tool_calls[idx]
            status_icon = "⏳" if tc.get("status") in ["calling", "executing"] else "✅" if tc.get("status") == "success" else "❌"
            content += f"{status_icon} {tc.get('name')}({tc.get('arguments', '')[:30]}...)\n"
            if "result" in tc:
                content += f"   └─ Result: {tc['result'][:100]}\n"
        
        # We'll use a single Static for tools for now for simplicity
        tools_container.remove_children()
        tools_container.mount(Static(content))

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