from textual.widgets import RichLog, Static
from textual.containers import Container
from textual.app import ComposeResult
from textual import log

class ConversationArea(Container):
    DEFAULT_CSS = """
    ConversationArea {
        height: 1fr;
        border: solid $accent;
        margin: 0 1;
        overflow-y: scroll;
    }
    
    .conversation-entry {
        width: 100%;
        height: auto;
        padding: 0 1;
        margin: 0 0 1 0;
    }
    """
    
    def compose(self) -> ComposeResult:
        # We'll use a container to hold multiple entries
        yield Container(id="conversation_container")
        
    def write(self, content: str, msg_id: str = None) -> None:
        container = self.query_one("#conversation_container")
        
        if msg_id:
            # Try to find existing message by ID
            try:
                existing = self.query_one(f"#{msg_id}", Static)
                existing.update(content)
                # Scroll to end
                self.scroll_end(animate=False)
                return
            except Exception:
                pass
        
        # If no ID or not found, create new
        new_entry = Static(content, classes="conversation-entry")
        if msg_id:
            new_entry.id = msg_id
        container.mount(new_entry)
        self.scroll_end(animate=False)