"""Delivery manager — routes job results to channels and file logs."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..api.manager import ConnectionManager
    from ..channels.store import ChannelStore
    from ..config import AppConfig
    from ..context.store import ConversationStore
    from ..pipeline.bus import Bus
    from .models import JobDefinition

logger = logging.getLogger(__name__)

_DEFAULT_OUTPUT_DIR = "~/.tank/jobs/output"

# Type alias for the messages appended to a channel conversation.
ChannelMessage = dict[str, str]  # {"role": "...", "content": "..."}


@dataclass
class _DeliveryResult:
    """Internal result from channel delivery."""

    output_path: str | None = None
    channel_messages: dict[str, list[ChannelMessage]] = field(
        default_factory=dict,
    )


class DeliveryManager:
    """Deliver job results to channels and file logs."""

    def __init__(
        self,
        output_dir: str | Path = _DEFAULT_OUTPUT_DIR,
        app_config: AppConfig | None = None,
        bus: Bus | None = None,
        channel_store: ChannelStore | None = None,
        conversation_store: ConversationStore | None = None,
    ) -> None:
        self._output_dir = Path(output_dir).expanduser().resolve()
        self._app_config = app_config
        self._bus = bus
        self._channel_store = channel_store
        self._conversation_store = conversation_store
        self._connection_manager: ConnectionManager | None = None

    def set_connection_manager(self, mgr: ConnectionManager) -> None:
        """Set the ConnectionManager for broadcast (called after server init)."""
        self._connection_manager = mgr

    async def deliver(
        self,
        job: JobDefinition,
        run_id: str,
        text: str,
    ) -> str:
        """Deliver results via channels and file log. Returns output file path."""
        # Primary delivery: channels
        result = self._deliver_to_channels(job, run_id, text)
        output_path = result.output_path

        # Audit trail: file log
        if job.delivery.log_output:
            log_path = self._save_text(job, run_id, text)
            if not output_path:
                output_path = str(log_path)

        if self._bus is not None:
            from ..pipeline.bus import BusMessage

            self._bus.post(BusMessage(
                type="job_delivery",
                source="delivery_manager",
                payload={
                    "job_id": job.id,
                    "job_name": job.name,
                    "run_id": run_id,
                    "output_path": str(output_path) if output_path else "",
                    "channels": list(job.delivery.channels),
                },
            ))

        # Broadcast channel notifications to all connected WebSocket sessions
        await self._notify_channels(job, run_id, result.channel_messages)

        return str(output_path) if output_path else ""

    # ------------------------------------------------------------------
    # Channel delivery
    # ------------------------------------------------------------------

    def _deliver_to_channels(
        self, job: JobDefinition, run_id: str, text: str,
    ) -> _DeliveryResult:
        """Deliver job output to configured channel slugs."""
        result = _DeliveryResult()
        if not job.delivery.channels or not self._channel_store or not self._conversation_store:
            return result

        now_iso = datetime.now(timezone.utc).isoformat()

        for slug in job.delivery.channels:
            try:
                channel = self._channel_store.get_or_create(
                    slug, name=job.name,
                    conversation_store=self._conversation_store,
                )
                conversation = self._conversation_store.load(channel.conversation_id)
                if conversation is None:
                    logger.warning(
                        "Conversation %s not found for channel '%s'",
                        channel.conversation_id, slug,
                    )
                    continue

                sys_msg = {
                    "role": "system",
                    "content": f"[Job: {job.name}] run {run_id} completed at {now_iso}",
                }
                asst_msg = {"role": "assistant", "content": text}
                conversation.messages.append(sys_msg)
                conversation.messages.append(asst_msg)
                self._conversation_store.save(conversation)
                result.channel_messages[slug] = [sys_msg, asst_msg]
                logger.info("Delivered job '%s' to channel '%s'", job.name, slug)
            except Exception:
                logger.error("Failed to deliver to channel '%s'", slug, exc_info=True)

        return result

    async def _notify_channels(
        self,
        job: JobDefinition,
        run_id: str,
        channel_messages: dict[str, list[dict[str, str]]],
    ) -> None:
        """Broadcast channel_notification to all connected WebSocket sessions."""
        if self._connection_manager is None or not channel_messages:
            return

        from ..api.schemas import MessageType, WebsocketMessage

        for slug, messages in channel_messages.items():
            channel = self._channel_store.get(slug) if self._channel_store else None
            preview = ""
            for m in messages:
                if m["role"] == "assistant":
                    content = m["content"]
                    preview = content[:200] + "..." if len(content) > 200 else content
                    break

            msg = WebsocketMessage(
                type=MessageType.CHANNEL_NOTIFICATION,
                content="",
                metadata={
                    "channel_slug": slug,
                    "channel_name": channel.name if channel else slug,
                    "event_type": "job_delivery",
                    "job_name": job.name,
                    "run_id": run_id,
                    "messages": messages,
                    "message_preview": preview,
                },
            )
            try:
                await self._connection_manager.broadcast(msg.model_dump_json())
            except Exception:
                logger.debug("Failed to broadcast channel notification for '%s'", slug)

    # ------------------------------------------------------------------
    # Text delivery (audit trail)
    # ------------------------------------------------------------------

    def _save_text(self, job: JobDefinition, run_id: str, text: str) -> Path:
        """Save output to a markdown file. Returns the file path."""
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H%M%S")
        job_dir = self._output_dir / _sanitize_dirname(job.name)
        job_dir.mkdir(parents=True, exist_ok=True)
        path = job_dir / f"{ts}.md"

        header = (
            f"# {job.name}\n\n"
            f"Run: {run_id}  \n"
            f"Time: {datetime.now(timezone.utc).isoformat()}  \n"
            f"Channels: {', '.join(job.delivery.channels) or 'none'}  \n\n---\n\n"
        )
        path.write_text(header + text, encoding="utf-8")
        logger.info("Saved job output: %s", path)
        return path


def _sanitize_dirname(name: str) -> str:
    """Convert a job name to a safe directory name."""
    import re

    safe = re.sub(r"[^\w\-.]", "_", name.strip().lower())
    return safe[:64] or "unnamed"
