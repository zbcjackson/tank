"""TUI client that connects to the Tank backend via WebSocket."""

import asyncio
import logging

from textual.app import App, ComposeResult
from textual.logging import TextualHandler
from textual.widgets import Footer

from ..schemas import WebsocketMessage, MessageType
from ..cli.client import TankClient
from ..cli.audio_capture import ClientAudioCapture
from ..cli.audio_playback import ClientAudioPlayback
from ..core.shutdown import GracefulShutdown
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

    def __init__(self, server_url: str = "localhost:8000"):
        super().__init__()
        self._shutdown_signal = GracefulShutdown()
        self._client = TankClient(base_url=server_url)
        self._capture = ClientAudioCapture(shutdown=self._shutdown_signal)
        self._playback = ClientAudioPlayback(shutdown=self._shutdown_signal)
        self._tasks: list[asyncio.Task] = []

    def compose(self) -> ComposeResult:
        yield TankHeader()
        yield ConversationArea()
        yield InputFooter()
        yield Footer()

    async def on_mount(self) -> None:
        self.title = "Tank"

        await self._client.connect(
            on_text_message=self._handle_ws_message,
            on_audio_chunk=self._playback.on_audio_chunk,
        )

        self._capture.start()
        self._playback.start()

        self._tasks.append(asyncio.create_task(self._client.receive_loop()))
        self._tasks.append(asyncio.create_task(
            self._capture.drain_to_ws(self._client.send_audio)
        ))

    def _handle_ws_message(self, msg: WebsocketMessage) -> None:
        """Handle text messages from the backend WebSocket."""
        if msg.type == MessageType.SIGNAL:
            if msg.content == "ready":
                self.call_from_thread(self.notify, "Connected to server")
            elif msg.content == "tts_ended":
                self._playback.end_stream()
            return

        self.call_from_thread(self._handle_ws_message, msg)

    def _handle_ws_message(self, msg: WebsocketMessage) -> None:
        """Handle WebSocket message on TUI thread."""
        # Check if app is still running and screen exists
        if not self.is_running or not self.screen_stack:
            return
        try:
            self.query_one(ConversationArea).write_ws_message(msg)
        except Exception:
            # Ignore errors during shutdown
            pass

    def on_input_submitted(self, event: InputFooter.Submitted) -> None:
        user_input = event.value
        if user_input:
            if user_input.lower() in ("quit", "exit"):
                self._shutdown_signal.stop()
                self.exit()
                return
            asyncio.create_task(self._client.send_text_input(user_input))
            self.query_one(InputFooter).value = ""

    async def on_unmount(self) -> None:
        self._shutdown_signal.stop()
        for task in self._tasks:
            task.cancel()
        await self._client.disconnect()
        self._playback.stop()
        self._capture.stop()
