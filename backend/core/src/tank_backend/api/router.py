"""WebSocket router for real-time interaction."""

from __future__ import annotations

import asyncio
import json
import logging
import time

import numpy as np
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from ..audio.input.types import AudioFrame
from ..audio.output.types import AudioChunk
from ..core.events import DisplayMessage, SignalMessage, UIMessage, UpdateType
from .schemas import MessageType, WebsocketMessage
from .signal_handlers import DisconnectSignal
from .signal_handlers import dispatch as dispatch_signal

logger = logging.getLogger("ApiRouter")

router = APIRouter()

# connection_manager is set by server.py after creation
connection_manager = None


def set_connection_manager(mgr):
    """Called by server.py to inject the shared ConnectionManager."""
    global connection_manager  # noqa: PLW0603
    connection_manager = mgr


def _resolve_user_name(user_id: str | None) -> str:
    """Resolve a user_id from WebSocket metadata to a display name for Brain."""
    if not user_id or connection_manager is None:
        return "Guest"
    recognizer = connection_manager.get_voiceprint_recognizer()
    if recognizer is None or not recognizer.enabled:
        return "Guest"
    speaker = recognizer.repository.get_speaker(user_id)
    return speaker.name if speaker else "Guest"


def _ui_msg_to_ws_msg(msg: UIMessage, session_id: str) -> WebsocketMessage | None:
    """Convert a UIMessage to a WebsocketMessage."""
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
            elif msg.update_type == UpdateType.APPROVAL:
                approval_id = msg.metadata.get("approval_id", "")
                if approval_id:
                    step_id = f"{msg.msg_id}_approval_{approval_id}"
            ws_msg.metadata["step_id"] = step_id
        return ws_msg
    logger.warning(f"Unknown UI message type: {type(msg)}")
    return None


@router.websocket("/ws/{session_id}")
async def websocket_endpoint(websocket: WebSocket, session_id: str):
    """Pipeline-based WebSocket endpoint using Assistant."""
    await websocket.accept()
    logger.info(f"WebSocket connected: {session_id}")

    ws_connected = True
    loop = asyncio.get_running_loop()

    assistant, is_new = await connection_manager.get_or_create_assistant(session_id)

    # Load persisted conversation history for this session
    assistant.set_session_id(session_id)

    if not is_new:
        logger.info(f"WebSocket reattached to existing session: {session_id}")

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
                logger.debug(f"Send error: {e}")

        asyncio.run_coroutine_threadsafe(_send(), loop)

    # Atomic swap on reattach to avoid a window with no callbacks;
    # append on new session.
    if is_new:
        assistant.subscribe_ui(on_ui_message)
    else:
        assistant.set_ui_callback(on_ui_message)

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
                logger.debug(f"Audio send error: {e}")

        asyncio.run_coroutine_threadsafe(_send_chunk(), loop)

    assistant.set_playback_callback(on_playback_chunk)

    # Helper for signal handlers to send messages
    async def send_ws_msg(msg: WebsocketMessage) -> None:
        if ws_connected:
            try:
                await websocket.send_text(msg.model_dump_json())
            except Exception as e:
                logger.debug(f"Send error: {e}")

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
                    handled = await dispatch_signal(
                        msg.content, assistant, msg, session_id, send_ws_msg,
                    )
                    if not handled:
                        logger.warning("Unknown signal: %s", msg.content)

                elif msg.type == MessageType.INPUT:
                    user_id = msg.metadata.get("user_id")
                    user_name = _resolve_user_name(user_id)
                    assistant.process_input(msg.content, user=user_name)
                elif msg.type == MessageType.APPROVAL_RESPONSE:
                    approval_id = msg.metadata.get("approval_id", "")
                    approved = msg.metadata.get("approved", False)
                    reason = msg.metadata.get("reason", "")
                    approval_mgr = assistant.approval_manager
                    if approval_mgr and approval_id:
                        approval_mgr.resolve(
                            approval_id, approved=approved, reason=reason
                        )
                    else:
                        logger.warning(
                            "Approval response ignored: mgr=%s id=%s",
                            approval_mgr is not None,
                            approval_id,
                        )

    except (WebSocketDisconnect, DisconnectSignal):
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
        # Decrement refcount. Idle timer only starts when no WS remains.
        connection_manager.detach_websocket(session_id)
        logger.info(f"WebSocket disconnected: {session_id}")
