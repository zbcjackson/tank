import queue
import logging
from .shutdown import GracefulShutdown
from .speaker import SpeakerHandler
from .mic import MicHandler
from .brain import Brain
from .queues import display_queue, text_queue

# Configure logging (ensure this runs if this module is initialized/used as entry point or part of one)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(threadName)s] %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger("RefactoredAssistant")

class CLI:
    """
    Main Thread Interface.
    """
    def __init__(self):
        self.shutdown_signal = GracefulShutdown()
        self.speaker = SpeakerHandler(self.shutdown_signal)
        self.mic = MicHandler(self.shutdown_signal)
        self.brain = Brain(self.shutdown_signal, self.speaker)

    def start(self):
        # Start background threads
        self.mic.start()
        self.speaker.start()
        self.brain.start()

        print("\n=== System Started ===")
        print("Type 'quit' to exit, 'stop' to interrupt speech.")
        print("Mic is simulating inputs... Wait for it!")
        print("======================\n")

        try:
            self.loop()
        except KeyboardInterrupt:
            print("\nKeyboardInterrupt detected. Shutting down...")
        finally:
            self.shutdown_signal.stop()
            
            # Flush display queue one last time
            while not display_queue.empty():
                try:
                    msg = display_queue.get_nowait()
                    print(f"\n[DISPLAY] {msg}")
                except queue.Empty:
                    break

            self.mic.join()
            self.speaker.join()
            self.brain.join()
            print("System Shutdown Complete.")

    def loop(self):
        while not self.shutdown_signal.is_set():
            # 1. Handle Display (Non-blocking check)
            while not display_queue.empty():
                try:
                    msg = display_queue.get_nowait()
                    print(f"\n[DISPLAY] {msg}")
                    display_queue.task_done()
                except queue.Empty:
                    break

            # 2. Handle Input
            try:
                # We use a trick: check if input is available? 
                # No, standard python input() doesn't allow peeking.
                # We will just block on input() and let the Logger show the async activity.
                # The user can type at any time.
                
                user_input = input(">>> ")
                
                if user_input.lower() in ["quit", "exit"]:
                    break
                
                text_queue.put(user_input)
                
            except EOFError:
                break
