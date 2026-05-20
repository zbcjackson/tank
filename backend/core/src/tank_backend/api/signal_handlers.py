"""WebSocket signal handlers — command pattern for incoming signals.

Each handler is registered via ``@register("signal_name")`` and dispatched
by :func:`dispatch` from the WebSocket router.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING

from .schemas import MessageType, WebsocketMessage

if TYPE_CHECKING:
    from ..core.assistant import Assistant

logger = logging.getLogger(__name__)

# Handler signature: (assistant, msg, session_id, send_fn) → None
SendFn = Callable[[WebsocketMessage], Awaitable[None]]
SignalHandler = Callable[["Assistant", WebsocketMessage, str, SendFn], Awaitable[None]]

_handlers: dict[str, SignalHandler] = {}


class DisconnectSignal(Exception):
    """Raised by the disconnect handler to break the receive loop."""


def register(signal_name: str) -> Callable[[SignalHandler], SignalHandler]:
    """Decorator to register a signal handler."""

    def decorator(fn: SignalHandler) -> SignalHandler:
        _handlers[signal_name] = fn
        return fn

    return decorator


async def dispatch(
    signal: str,
    assistant: Assistant,
    msg: WebsocketMessage,
    session_id: str,
    send_fn: SendFn,
) -> bool:
    """Dispatch a signal to its handler. Returns True if handled."""
    handler = _handlers.get(signal)
    if handler is None:
        return False
    await handler(assistant, msg, session_id, send_fn)
    return True


# ---------------------------------------------------------------------------
# Signal handlers
# ---------------------------------------------------------------------------


@register("disconnect")
async def handle_disconnect(
    assistant: Assistant,
    msg: WebsocketMessage,
    session_id: str,
    send_fn: SendFn,
) -> None:
    raise DisconnectSignal()


@register("wake")
async def handle_wake(
    assistant: Assistant,
    msg: WebsocketMessage,
    session_id: str,
    send_fn: SendFn,
) -> None:
    try:
        assistant.compact_session()
        await send_fn(
            WebsocketMessage(
                type=MessageType.SIGNAL,
                content="conversation_ready",
                session_id=session_id,
            )
        )
    except Exception as e:
        logger.error("Session compact failed: %s", e, exc_info=True)
        await send_fn(
            WebsocketMessage(
                type=MessageType.SIGNAL,
                content="session_reset_failed",
                session_id=session_id,
                metadata={"error": str(e)},
            )
        )


@register("idle")
async def handle_idle(
    assistant: Assistant,
    msg: WebsocketMessage,
    session_id: str,
    send_fn: SendFn,
) -> None:
    logger.info("Client idle: %s", session_id)


@register("interrupt")
async def handle_interrupt(
    assistant: Assistant,
    msg: WebsocketMessage,
    session_id: str,
    send_fn: SendFn,
) -> None:
    logger.info("Client interrupt: %s", session_id)
    assistant.interrupt()


@register("end_of_utterance")
async def handle_end_of_utterance(
    assistant: Assistant,
    msg: WebsocketMessage,
    session_id: str,
    send_fn: SendFn,
) -> None:
    """Client signals push-to-talk send — force-finalize the current utterance.

    Bypasses VAD silence detection so streaming ASR sessions don't wait
    for trailing silence (and time out). The frontend pauses the mic
    after sending this signal.
    """
    logger.info("Client end_of_utterance: %s", session_id)
    assistant.end_utterance()


@register("ping")
async def handle_ping(
    assistant: Assistant,
    msg: WebsocketMessage,
    session_id: str,
    send_fn: SendFn,
) -> None:
    await send_fn(
        WebsocketMessage(
            type=MessageType.SIGNAL,
            content="pong",
            session_id=session_id,
            metadata=msg.metadata.copy() if msg.metadata else {},
        )
    )


@register("resume_conversation")
async def handle_resume_conversation(
    assistant: Assistant,
    msg: WebsocketMessage,
    session_id: str,
    send_fn: SendFn,
) -> None:
    cid = (msg.metadata or {}).get("conversation_id", "")
    if not cid:
        await send_fn(
            WebsocketMessage(
                type=MessageType.SIGNAL,
                content="conversation_resume_failed",
                session_id=session_id,
                metadata={"error": "missing conversation_id"},
            )
        )
        return
    success = assistant.resume_conversation(cid)
    status = "conversation_resumed" if success else "conversation_resume_failed"

    # Track channel context for audio fan-out
    from . import deps
    channel_slug: str | None = None
    if success:
        ch_store = deps.app_context().channel_store
        if ch_store is not None:
            channel = ch_store.get_by_conversation_id(cid)
            if channel is not None:
                channel_slug = channel.slug
    deps.connection_manager().set_session_channel(session_id, channel_slug)

    await send_fn(
        WebsocketMessage(
            type=MessageType.SIGNAL,
            content=status,
            session_id=session_id,
            metadata={"conversation_id": cid},
        )
    )


@register("new_conversation")
async def handle_new_conversation(
    assistant: Assistant,
    msg: WebsocketMessage,
    session_id: str,
    send_fn: SendFn,
) -> None:
    new_cid = assistant.new_conversation()
    from . import deps
    deps.connection_manager().set_session_channel(session_id, None)
    await send_fn(
        WebsocketMessage(
            type=MessageType.SIGNAL,
            content="conversation_created",
            session_id=session_id,
            metadata={"conversation_id": new_cid},
        )
    )


@register("subscribe_channels")
async def handle_subscribe_channels(
    assistant: Assistant,
    msg: WebsocketMessage,
    session_id: str,
    send_fn: SendFn,
) -> None:
    slugs = (msg.metadata or {}).get("channels", [])
    if not slugs or not isinstance(slugs, list):
        return
    from . import deps
    deps.subscription_manager().subscribe(session_id, slugs)
    await send_fn(
        WebsocketMessage(
            type=MessageType.SIGNAL,
            content="channels_subscribed",
            session_id=session_id,
            metadata={"channels": slugs},
        )
    )


@register("unsubscribe_channels")
async def handle_unsubscribe_channels(
    assistant: Assistant,
    msg: WebsocketMessage,
    session_id: str,
    send_fn: SendFn,
) -> None:
    slugs = (msg.metadata or {}).get("channels", [])
    if not slugs or not isinstance(slugs, list):
        return
    from . import deps
    deps.subscription_manager().unsubscribe(session_id, slugs)
    await send_fn(
        WebsocketMessage(
            type=MessageType.SIGNAL,
            content="channels_unsubscribed",
            session_id=session_id,
            metadata={"channels": slugs},
        )
    )


@register("stop_channel_audio")
async def handle_stop_channel_audio(
    assistant: Assistant,
    msg: WebsocketMessage,
    session_id: str,
    send_fn: SendFn,
) -> None:
    """Interrupt in-progress channel audio.

    If `channel_slug` is provided in metadata, only that channel is stopped.
    Otherwise all channels this session is subscribed to are stopped.
    """
    from . import deps
    service = deps.channel_audio_service()
    if service is None:
        return
    meta = msg.metadata or {}
    slug = meta.get("channel_slug")
    if isinstance(slug, str) and slug:
        service.interrupt(slug)
    else:
        # Stop every channel this session is currently subscribed to
        for s in deps.subscription_manager().get_subscriptions(session_id):
            service.interrupt(s)
