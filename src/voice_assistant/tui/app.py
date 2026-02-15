import logging

from textual.app import App, ComposeResult
from textual.logging import TextualHandler
from textual.widgets import Footer
import uuid

from ..core.assistant import Assistant
from .ui.header import TankHeader
from .ui.conversation import ConversationArea
from .ui.footer import InputFooter

logging.basicConfig(
    level="NOTSET",
    handlers=[TextualHandler()],
    format="[%(levelname)s] %(name)s: %(message)s",
)

class TankApp(App):
    CSS = """
    Screen {
        layout: vertical;
    }
    """

    def __init__(self):
        super().__init__()
        # Pass self.exit as the callback for when assistant requests an exit
        self.assistant = Assistant(on_exit_request=self.exit)

    def compose(self) -> ComposeResult:
        yield TankHeader()
        yield ConversationArea()
        yield InputFooter()
        yield Footer() 

    def on_mount(self) -> None:
        self.title = "Tank"
        
        # Start core logic
        self.assistant.start()
        
        # Start polling the display queue
        self.set_interval(0.1, self.check_display_queue)

    def check_display_queue(self):
        """Check for new messages from the Brain/System/User to display."""
        for msg in self.assistant.get_messages():
            if msg.speaker in ("User", "Unknown", "Keyboard"):
                content = f"[bold green]You:[/bold green] [white]{msg.text}[/white]"
                self.query_one(ConversationArea).write(content, msg_id=msg.msg_id)
            else:
                self.query_one(ConversationArea).write(
                    f"[bold blue]Tank:[/bold blue] [white]{msg.text}[/white]",
                    msg_id=msg.msg_id
                )

    def on_input_submitted(self, event: InputFooter.Submitted) -> None:
        user_input = event.value
        if user_input:
            self.assistant.process_input(user_input)
            # Clear input
            self.query_one(InputFooter).value = ""

    def on_unmount(self) -> None:
        self.assistant.stop()
