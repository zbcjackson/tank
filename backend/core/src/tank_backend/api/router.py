"""WebSocket router for real-time interaction."""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import time

import numpy as np
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from ..audio.input.queue_source import QueueAudioSource
from ..audio.input.types import AudioFrame
from ..audio.output.callback_sink import CallbackAudioSink
from ..audio.output.types import AudioChunk
from ..core.assistant_v2 import AssistantV2
from ..core.events import DisplayMessage, SignalMessage, UIMessage, UpdateType
from .manager import SessionManager
from .schemas import MessageType, WebsocketMessage

logger = logging.getLogger("ApiRouter")

router = APIRouter()
session_manager = SessionManager()


@router.websocket("/ws/{session_id}")
async def websocket_endpoint(websocket: WebSocket, session_id: str):
    await websocket.accept()
    logger.info(f"WebSocket connected: {session_id}")

    # Guard flag: set to False before cleanup to prevent sends on dead socket
    ws_connected = True

    def source_factory(q, stop_sig):
        return QueueAudioSource(q)

    def sink_factory(q, stop_sig):
        async def on_chunk_async(chunk: AudioChunk):
            if not ws_connected:
                return
            try:
                await websocket.send_bytes(chunk.data)
            except Exception as e:
                logger.debug(f"Error sending audio chunk: {e}")

        async def on_stream_end_async():
            if not ws_connected:
                return
            try:
                msg = WebsocketMessage(
                    type=MessageType.SIGNAL, content="tts_ended", session_id=session_id
                )
                await websocket.send_text(msg.model_dump_json())
            except Exception as e:
                logger.debug(f"Error sending tts_ended signal: {e}")

        loop = asyncio.get_event_loop()

        def on_chunk_sync(chunk: AudioChunk):
            if not ws_connected:
                return
            asyncio.run_coroutine_threadsafe(on_chunk_async(chunk), loop)

        def on_stream_end_sync():
            if not ws_connected:
                return
            asyncio.run_coroutine_threadsafe(on_stream_end_async(), loop)

        return CallbackAudioSink(
            stop_signal=stop_sig,
            audio_chunk_queue=q,
            on_chunk=on_chunk_sync,
            on_stream_end=on_stream_end_sync,
        )

    assistant = session_manager.create_assistant(
        session_id=session_id, audio_source_factory=source_factory, audio_sink_factory=sink_factory
    )

    # Task to pipe Assistant's UI messages (signals, transcripts, text) to WS
    async def pipe_display_messages():
        try:
            while True:
                for msg in assistant.get_messages():
                    # Handle SignalMessage
                    if isinstance(msg, SignalMessage):
                        ws_msg = WebsocketMessage(
                            type=MessageType.SIGNAL,
                            content=msg.signal_type,
                            msg_id=msg.msg_id,
                            session_id=session_id,
                            metadata=msg.metadata.copy() if msg.metadata else {},
                        )
                    # Handle DisplayMessage
                    elif isinstance(msg, DisplayMessage):
                        ws_msg = WebsocketMessage(
                            type=MessageType.TRANSCRIPT if msg.is_user else MessageType.TEXT,
                            content=msg.text,
                            speaker=msg.speaker,
                            is_user=msg.is_user,
                            is_final=msg.is_final,
                            msg_id=msg.msg_id,
                            session_id=session_id,
                            metadata=msg.metadata.copy() if msg.metadata else {},
                        )

                        # For non-text updates (tool calls, thoughts, etc.)
                        if msg.update_type.name != "TEXT":
                            ws_msg.type = MessageType.UPDATE
                            ws_msg.metadata["update_type"] = str(msg.update_type)

                        # Compute and add step_id for all messages
                        if msg.msg_id:
                            turn = msg.metadata.get("turn", 0)
                            step_type = msg.update_type.name.lower()

                            step_id = f"{msg.msg_id}_{step_type}_{turn}"

                            if msg.update_type == UpdateType.TOOL:
                                index = msg.metadata.get("index", 0)
                                step_id += f"_{index}"

                            ws_msg.metadata["step_id"] = step_id
                    else:
                        logger.warning(f"Unknown message type: {type(msg)}")
                        continue

                    await websocket.send_text(ws_msg.model_dump_json())
                await asyncio.sleep(0.05)
        except Exception as e:
            logger.debug(f"Display pipe stopped: {e}")

    display_task = asyncio.create_task(pipe_display_messages())

    try:
        # Send 'ready' signal with capabilities
        ready_msg = WebsocketMessage(
            type=MessageType.SIGNAL,
            content="ready",
            session_id=session_id,
            metadata={"capabilities": assistant.capabilities},
        )
        await websocket.send_text(ready_msg.model_dump_json())

        while True:
            # Main loop: receive from client
            # Could be bytes (audio) or text (signals/keyboard)
            data = await websocket.receive()

            if "bytes" in data:
                # Binary: push to Assistant's QueueAudioSource
                if assistant.audio_input is None:
                    continue  # ASR disabled — silently drop audio

                import time

                import numpy as np

                # Assume 16kHz, 16bit, Mono PCM from client
                pcm_data = np.frombuffer(data["bytes"], dtype=np.int16).astype(np.float32) / 32768.0
                frame = AudioFrame(pcm=pcm_data, sample_rate=16000, timestamp_s=time.time())
                assistant.audio_input._source.push(frame)

            elif "text" in data:
                # Text: parse WebsocketMessage
                msg_json = json.loads(data["text"])
                msg = WebsocketMessage(**msg_json)

                if msg.type == MessageType.SIGNAL:
                    if msg.content == "interrupt":
                        if assistant.audio_output is not None:
                            assistant.audio_output.interrupt()
                    elif msg.content == "disconnect":
                        break
                    elif msg.content == "session_start":
                        try:
                            assistant.reset_session()
                            ready_msg = WebsocketMessage(
                                type=MessageType.SIGNAL,
                                content="session_ready",
                                session_id=session_id,
                            )
                            await websocket.send_text(ready_msg.model_dump_json())
                        except Exception as e:
                            logger.error(f"Session reset failed: {e}", exc_info=True)
                            error_msg = WebsocketMessage(
                                type=MessageType.SIGNAL,
                                content="session_reset_failed",
                                session_id=session_id,
                                metadata={"error": str(e)},
                            )
                            await websocket.send_text(error_msg.model_dump_json())
                    elif msg.content == "session_end":
                        if assistant.audio_output is not None:
                            assistant.audio_output.interrupt()
                        logger.info(f"Session ended by client: {session_id}")
                    elif msg.content == "ping":
                        pong_msg = WebsocketMessage(
                            type=MessageType.SIGNAL,
                            content="pong",
                            session_id=session_id,
                            metadata=msg.metadata.copy() if msg.metadata else {},
                        )
                        await websocket.send_text(pong_msg.model_dump_json())
                elif msg.type == MessageType.INPUT:
                    assistant.process_input(msg.content)

    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected: {session_id}")
    except RuntimeError as e:
        if "disconnect message has been received" in str(e):
            logger.info(f"WebSocket disconnected: {session_id}")
        else:
            logger.error(f"WebSocket error in {session_id}: {e}", exc_info=True)
    except Exception as e:
        logger.error(f"WebSocket error in {session_id}: {e}", exc_info=True)
    finally:
        ws_connected = False
        display_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await display_task
        await asyncio.to_thread(session_manager.close_session, session_id)


# ---------------------------------------------------------------------------
# V2 WebSocket endpoint — pipeline-based AssistantV2
# ---------------------------------------------------------------------------


def _ui_msg_to_ws_msg(msg: UIMessage, session_id: str) -> WebsocketMessage | None:
    """Convert a UIMessage to a WebsocketMessage (shared by V2 endpoint)."""
    if isinstance(msg, SignalMessage):
        return WebsocketMessage(
            type=MessageType.SIGNAL,
            content=msg.signal_type,
            msg_id=msg.msg_id,
            session_id=session_id,
            metadata=msg.metadata.copy() if msg.metadata else {},
        )
    if isinstance(msg, DisplayMessage):
        ws_msg = WebsocketMessage(
            type=MessageType.TRANSCRIPT if msg.is_user else MessageType.TEXT,
            content=msg.text,
            speaker=msg.speaker,
            is_user=msg.is_user,
            is_final=msg.is_final,
            msg_id=msg.msg_id,
            session_id=session_id,
            metadata=msg.metadata.copy() if msg.metadata else {},
        )
        if msg.update_type.name != "TEXT":
            ws_msg.type = MessageType.UPDATE
            ws_msg.metadata["update_type"] = str(msg.update_type)

        if msg.msg_id:
            turn = msg.metadata.get("turn", 0)
            step_type = msg.update_type.name.lower()
            step_id = f"{msg.msg_id}_{step_type}_{turn}"
            if msg.update_type == UpdateType.TOOL:
                index = msg.metadata.get("index", 0)
                step_id += f"_{index}"
            ws_msg.metadata["step_id"] = step_id
        return ws_msg
    logger.warning(f"Unknown UI message type: {type(msg)}")
    return None


@router.websocket("/v2/ws/{session_id}")
async def websocket_v2_endpoint(websocket: WebSocket, session_id: str):
    """Pipeline-based WebSocket endpoint using AssistantV2."""
    await websocket.accept()
    logger.info(f"WebSocket V2 connected: {session_id}")

    ws_connected = True
    loop = asyncio.get_event_loop()

    assistant: AssistantV2 = await session_manager.create_assistant_v2(session_id)

    # Bus-based UI push: forward UI messages to WebSocket
    def on_ui_message(msg: UIMessage) -> None:
        if not ws_connected:
            return
        ws_msg = _ui_msg_to_ws_msg(msg, session_id)
        if ws_msg is None:
            return

        async def _send() -> None:
            if not ws_connected:
                return
            try:
                await websocket.send_text(ws_msg.model_dump_json())
            except Exception as e:
                logger.debug(f"V2 send error: {e}")

        asyncio.run_coroutine_threadsafe(_send(), loop)

    assistant.subscribe_ui(on_ui_message)

    # Playback callback: send audio chunks over WebSocket
    def on_playback_chunk(chunk: AudioChunk) -> None:
        if not ws_connected:
            return

        async def _send_chunk() -> None:
            if not ws_connected:
                return
            try:
                await websocket.send_bytes(chunk.data)
            except Exception as e:
                logger.debug(f"V2 audio send error: {e}")

        asyncio.run_coroutine_threadsafe(_send_chunk(), loop)

    assistant.set_playback_callback(on_playback_chunk)

    try:
        # Send 'ready' signal with capabilities
        ready_msg = WebsocketMessage(
            type=MessageType.SIGNAL,
            content="ready",
            session_id=session_id,
            metadata={"capabilities": assistant.capabilities},
        )
        await websocket.send_text(ready_msg.model_dump_json())

        while True:
            data = await websocket.receive()

            if "bytes" in data:
                # Binary: push audio into pipeline
                pcm_data = (
                    np.frombuffer(data["bytes"], dtype=np.int16).astype(np.float32)
                    / 32768.0
                )
                frame = AudioFrame(
                    pcm=pcm_data, sample_rate=16000, timestamp_s=time.time()
                )
                assistant.push_audio(frame)

            elif "text" in data:
                msg_json = json.loads(data["text"])
                msg = WebsocketMessage(**msg_json)

                if msg.type == MessageType.SIGNAL:
                    if msg.content == "disconnect":
                        break
                    elif msg.content == "session_start":
                        try:
                            assistant.reset_session()
                            await websocket.send_text(
                                WebsocketMessage(
                                    type=MessageType.SIGNAL,
                                    content="session_ready",
                                    session_id=session_id,
                                ).model_dump_json()
                            )
                        except Exception as e:
                            logger.error(f"V2 session reset failed: {e}", exc_info=True)
                            await websocket.send_text(
                                WebsocketMessage(
                                    type=MessageType.SIGNAL,
                                    content="session_reset_failed",
                                    session_id=session_id,
                                    metadata={"error": str(e)},
                                ).model_dump_json()
                            )
                    elif msg.content == "session_end":
                        logger.info(f"V2 session ended by client: {session_id}")
                    elif msg.content == "ping":
                        await websocket.send_text(
                            WebsocketMessage(
                                type=MessageType.SIGNAL,
                                content="pong",
                                session_id=session_id,
                                metadata=msg.metadata.copy() if msg.metadata else {},
                            ).model_dump_json()
                        )
                elif msg.type == MessageType.INPUT:
                    assistant.process_input(msg.content)

    except WebSocketDisconnect:
        logger.info(f"WebSocket V2 disconnected: {session_id}")
    except RuntimeError as e:
        if "disconnect message has been received" in str(e):
            logger.info(f"WebSocket V2 disconnected: {session_id}")
        else:
            logger.error(f"WebSocket V2 error in {session_id}: {e}", exc_info=True)
    except Exception as e:
        logger.error(f"WebSocket V2 error in {session_id}: {e}", exc_info=True)
    finally:
        ws_connected = False
        await session_manager.close_session_async(session_id)
