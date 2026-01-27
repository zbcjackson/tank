from textual.app import App, ComposeResult
from textual.widgets import Footer
import queue

from .shutdown import GracefulShutdown
from .speaker import SpeakerHandler
from .mic import MicHandler
from .brain import Brain
from .queues import display_queue, text_queue
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
        self.shutdown_signal = GracefulShutdown()
        self.speaker = SpeakerHandler(self.shutdown_signal)
        self.mic = MicHandler(self.shutdown_signal)
        self.brain = Brain(self.shutdown_signal, self.speaker)

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
        
        # Start background threads
        self.mic.start()
        self.speaker.start()
        self.brain.start()
        
        # Start polling the display queue
        self.set_interval(0.1, self.check_display_queue)
        
        self.query_one(ConversationArea).write("[bold green]System Started.[/bold green] Type 'quit' to exit, 'stop' to interrupt.")

    def check_display_queue(self):
        """Check for new messages from the Brain/System to display."""
        while not display_queue.empty():
            try:
                msg = display_queue.get_nowait()
                self.query_one(ConversationArea).write(msg)
                display_queue.task_done()
            except queue.Empty:
                break

    def on_input_submitted(self, event: InputFooter.Submitted) -> None:
        user_input = event.value
        if user_input:
            # Echo user input to log
            self.query_one(ConversationArea).write(f"[bold cyan]You:[/bold cyan] {user_input}")
            
            if user_input.lower() in ["quit", "exit"]:
                self.exit()
            else:
                text_queue.put(user_input)
            
            # Clear input
            self.query_one(InputFooter).value = ""

    def on_unmount(self) -> None:
        self.shutdown_signal.stop()