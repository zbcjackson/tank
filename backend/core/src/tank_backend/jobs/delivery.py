"""Delivery manager — routes job results to channels and file logs."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..channels.store import ChannelStore
    from ..config import AppConfig
    from ..context.store import ConversationStore
    from ..pipeline.bus import Bus
    from .models import JobDefinition

logger = logging.getLogger(__name__)

_DEFAULT_OUTPUT_DIR = "~/.tank/jobs/output"


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

    async def deliver(
        self,
        job: JobDefinition,
        run_id: str,
        text: str,
    ) -> str:
        """Deliver results via channels and file log. Returns output file path."""
        # Primary delivery: channels
        output_path = self._deliver_to_channels(job, run_id, text)

        # Audit trail: file log
        if job.delivery.log_output:
            log_path = self._save_text(job, run_id, text)
            if not output_path:
                output_path = log_path

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

        return str(output_path) if output_path else ""

    # ------------------------------------------------------------------
    # Channel delivery
    # ------------------------------------------------------------------

    def _deliver_to_channels(
        self, job: JobDefinition, run_id: str, text: str,
    ) -> str | None:
        """Deliver job output to configured channel slugs."""
        if not job.delivery.channels or not self._channel_store or not self._conversation_store:
            return None

        now_iso = datetime.now(timezone.utc).isoformat()
        last_path: str | None = None

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

                conversation.messages.append({
                    "role": "system",
                    "content": f"[Job: {job.name}] run {run_id} completed at {now_iso}",
                })
                conversation.messages.append({"role": "assistant", "content": text})
                self._conversation_store.save(conversation)
                logger.info("Delivered job '%s' to channel '%s'", job.name, slug)
            except Exception:
                logger.error("Failed to deliver to channel '%s'", slug, exc_info=True)

        return last_path

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
