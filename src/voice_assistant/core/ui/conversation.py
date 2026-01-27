from textual.widgets import RichLog
from textual.containers import Container
from textual.app import ComposeResult

class ConversationArea(Container):
    DEFAULT_CSS = """
    ConversationArea {
        height: 1fr;
        border: solid $accent;
        margin: 0 1;
    }
    
    ConversationArea RichLog {
        height: 1fr;
        background: $surface;
    }
    """
    
    def compose(self) -> ComposeResult:
        yield RichLog(id="conversation_log", highlight=True, markup=True, wrap=True)
        
    def write(self, content: str) -> None:
        self.query_one(RichLog).write(content)
