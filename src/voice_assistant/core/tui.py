from textual.app import App, ComposeResult
from textual.widgets import Header, Footer, Input, RichLog
from textual.containers import Container
import queue
from .shutdown import GracefulShutdown
from .speaker import SpeakerHandler
from .mic import MicHandler
from .brain import Brain
from .queues import display_queue, text_queue

class TankApp(App):
    CSS = """
    Screen {
        layout: vertical;
    }

    Header {
        dock: top;
        height: 1;
        content-align: center middle;
    }

    #log_container {
        height: 1fr;
        border: solid $accent;
        margin: 0 1;
    }

    RichLog {
        height: 1fr;
    }

    Input {
        dock: bottom;
        margin: 0 1 1 1;
    }
    """

    def __init__(self):
        super().__init__()
        self.shutdown_signal = GracefulShutdown()
        self.speaker = SpeakerHandler(self.shutdown_signal)
        self.mic = MicHandler(self.shutdown_signal)
        self.brain = Brain(self.shutdown_signal, self.speaker)

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Container(id="log_container"):
            yield RichLog(id="conversation_log", highlight=True, markup=True, wrap=True)
        yield Input(placeholder="Type your message here... (Type 'quit' to exit)", id="user_input")
        yield Footer()

    def on_mount(self) -> None:
        self.title = "Tank"
        
        # Start background threads
        self.mic.start()
        self.speaker.start()
        self.brain.start()
        
        # Start polling the display queue
        self.set_interval(0.1, self.check_display_queue)
        
        self.query_one("#conversation_log").write("[bold green]System Started.[/bold green] Type 'quit' to exit, 'stop' to interrupt.")

    def check_display_queue(self):
        """Check for new messages from the Brain/System to display."""
        while not display_queue.empty():
            try:
                msg = display_queue.get_nowait()
                self.query_one("#conversation_log").write(msg)
                display_queue.task_done()
            except queue.Empty:
                break

    def on_input_submitted(self, event: Input.Submitted) -> None:
        user_input = event.value
        if user_input:
            # Echo user input to log
            self.query_one("#conversation_log").write(f"[bold cyan]You:[/bold cyan] {user_input}")
            
            if user_input.lower() in ["quit", "exit"]:
                self.exit()
            else:
                text_queue.put(user_input)
            
            # Clear input
            self.query_one("#user_input").value = ""

    def on_unmount(self) -> None:
        self.shutdown_signal.stop()
        # Ideally wait for threads, but Textual exit should be fast.
        # The threads are daemon-like or will stop when shutdown_signal is set.
