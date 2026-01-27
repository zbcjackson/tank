from textual.app import App, ComposeResult
from textual.widgets import Footer

from .assistant import Assistant
from .ui.header import TankHeader
from .ui.conversation import ConversationArea
from .ui.footer import InputFooter

class TankApp(App):
    CSS = """
    Screen {
        layout: vertical;
    }
    """

    def __init__(self):
        super().__init__()
        self.assistant = Assistant()

    def compose(self) -> ComposeResult:
        yield TankHeader()
        yield ConversationArea()
        yield InputFooter()
        # Keeping standard Footer for potential key bindings/status if needed, 
        # though visually the InputFooter acts as the main user interaction footer.
        # Use standard footer for key hints if we add them later.
        yield Footer() 

    def on_mount(self) -> None:
        self.title = "Tank"
        
        # Start core logic
        self.assistant.start()
        
        # Start polling the display queue
        self.set_interval(0.1, self.check_display_queue)
        
        self.query_one(ConversationArea).write("[bold green]System Started.[/bold green] Type 'quit' to exit, 'stop' to interrupt.")

    def check_display_queue(self):
        """Check for new messages from the Brain/System to display."""
        for msg in self.assistant.get_messages():
            self.query_one(ConversationArea).write(msg)

    def on_input_submitted(self, event: InputFooter.Submitted) -> None:
        user_input = event.value
        if user_input:
            # Echo user input to log
            self.query_one(ConversationArea).write(f"[bold cyan]You:[/bold cyan] {user_input}")
            
            if user_input.lower() in ["quit", "exit"]:
                self.exit()
            else:
                self.assistant.process_input(user_input)
            
            # Clear input
            self.query_one(InputFooter).value = ""

    def on_unmount(self) -> None:
        self.assistant.stop()