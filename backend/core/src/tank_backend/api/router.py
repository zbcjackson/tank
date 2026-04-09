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
from .manager import SessionManager
from .schemas import MessageType, WebsocketMessage

logger = logging.getLogger("ApiRouter")

router = APIRouter()
session_manager = SessionManager()


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

    assistant, is_new = await session_manager.get_or_create_assistant(session_id)

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
                pcm_data = np.frombuffer(data["bytes"], dtype=np.int16).astype(np.float32) / 32768.0
                frame = AudioFrame(pcm=pcm_data, sample_rate=16000, timestamp_s=time.time())
                assistant.push_audio(frame)

            elif "text" in data:
                msg_json = json.loads(data["text"])
                msg = WebsocketMessage(**msg_json)

                if msg.type == MessageType.SIGNAL:
                    if msg.content == "disconnect":
                        break
                    elif msg.content == "wake":
                        try:
                            assistant.compact_session()
                            await websocket.send_text(
                                WebsocketMessage(
                                    type=MessageType.SIGNAL,
                                    content="conversation_ready",
                                    session_id=session_id,
                                ).model_dump_json()
                            )
                        except Exception as e:
                            logger.error(f"Session compact failed: {e}", exc_info=True)
                            await websocket.send_text(
                                WebsocketMessage(
                                    type=MessageType.SIGNAL,
                                    content="session_reset_failed",
                                    session_id=session_id,
                                    metadata={"error": str(e)},
                                ).model_dump_json()
                            )
                    elif msg.content == "idle":
                        logger.info(f"Client idle: {session_id}")
                    elif msg.content == "interrupt":
                        logger.info(f"Client interrupt: {session_id}")
                        assistant.interrupt()
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
                elif msg.type == MessageType.APPROVAL_RESPONSE:
                    approval_id = msg.metadata.get("approval_id", "")
                    approved = msg.metadata.get("approved", False)
                    reason = msg.metadata.get("reason", "")
                    approval_mgr = assistant.approval_manager
                    if approval_mgr and approval_id:
                        approval_mgr.resolve(approval_id, approved=approved, reason=reason)
                    else:
                        logger.warning(
                            "Approval response ignored: mgr=%s id=%s",
                            approval_mgr is not None, approval_id,
                        )

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
        # Decrement refcount. Idle timer only starts when no WS remains.
        session_manager.detach_websocket(session_id)
        logger.info(f"WebSocket disconnected: {session_id}")
