"""Delivery manager — routes job results to text files, audio, and webhooks."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..config import AppConfig
    from ..pipeline.bus import Bus
    from .models import JobDefinition

logger = logging.getLogger(__name__)

_DEFAULT_OUTPUT_DIR = "~/.tank/jobs/output"


class DeliveryManager:
    """Deliver job results via configured channels."""

    def __init__(
        self,
        output_dir: str | Path = _DEFAULT_OUTPUT_DIR,
        app_config: AppConfig | None = None,
        bus: Bus | None = None,
    ) -> None:
        self._output_dir = Path(output_dir).expanduser().resolve()
        self._app_config = app_config
        self._bus = bus
        self._audio_queue: list[tuple[JobDefinition, str]] = []

    async def deliver(
        self,
        job: JobDefinition,
        run_id: str,
        text: str,
    ) -> str:
        """Deliver results via all configured channels. Returns output file path."""
        output_path = self._save_text(job, run_id, text)

        if job.delivery.audio:
            await self._deliver_audio(job, text)

        if job.delivery.webhook_url:
            await self._deliver_webhook(job, run_id, text)

        if self._bus is not None:
            from ..pipeline.bus import BusMessage

            self._bus.post(BusMessage(
                type="job_delivery",
                source="delivery_manager",
                payload={
                    "job_id": job.id,
                    "job_name": job.name,
                    "run_id": run_id,
                    "output_path": str(output_path),
                    "channels": self._active_channels(job),
                },
            ))

        return str(output_path)

    def drain_audio_queue(self) -> list[tuple[JobDefinition, str]]:
        """Pop all queued audio deliveries (called when session goes idle)."""
        items = list(self._audio_queue)
        self._audio_queue.clear()
        return items

    # ------------------------------------------------------------------
    # Text delivery
    # ------------------------------------------------------------------

    def _save_text(self, job: JobDefinition, run_id: str, text: str) -> Path:
        """Save output to a markdown file. Returns the file path."""
        if job.delivery.text_path:
            path = Path(job.delivery.text_path).expanduser().resolve()
        else:
            ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H%M%S")
            job_dir = self._output_dir / _sanitize_dirname(job.name)
            job_dir.mkdir(parents=True, exist_ok=True)
            path = job_dir / f"{ts}.md"

        path.parent.mkdir(parents=True, exist_ok=True)

        header = (
            f"# {job.name}\n\n"
            f"Run: {run_id}  \n"
            f"Time: {datetime.now(timezone.utc).isoformat()}  \n\n---\n\n"
        )
        path.write_text(header + text, encoding="utf-8")
        logger.info("Saved job output: %s", path)
        return path

    # ------------------------------------------------------------------
    # Audio delivery
    # ------------------------------------------------------------------

    async def _deliver_audio(self, job: JobDefinition, text: str) -> None:
        """Speak the result through TTS + playback, respecting conflict resolution."""
        # Audio delivery is best-effort — queue if we can't play now
        # The actual TTS pipeline integration requires the Assistant's audio
        # infrastructure. For Phase 1, we queue the audio and let the
        # scheduler/assistant drain it when appropriate.
        self._audio_queue.append((job, text))
        logger.info(
            "Queued audio delivery for job '%s' (priority=%s, queue_size=%d)",
            job.name, job.delivery.audio_priority, len(self._audio_queue),
        )

    # ------------------------------------------------------------------
    # Webhook delivery
    # ------------------------------------------------------------------

    async def _deliver_webhook(
        self, job: JobDefinition, run_id: str, text: str,
    ) -> None:
        """POST results to the configured webhook URL."""
        url = job.delivery.webhook_url
        if not url:
            return

        import httpx

        payload = {
            "job_id": job.id,
            "job_name": job.name,
            "run_id": run_id,
            "status": "succeeded",
            "output": text,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        headers = dict(job.delivery.webhook_headers)
        headers.setdefault("Content-Type", "application/json")

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(url, json=payload, headers=headers)
                resp.raise_for_status()
                logger.info("Webhook delivered for job '%s': %d", job.name, resp.status_code)
        except Exception:
            logger.error("Webhook delivery failed for job '%s'", job.name, exc_info=True)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _active_channels(job: JobDefinition) -> list[str]:
        channels = ["text"]
        if job.delivery.audio:
            channels.append("audio")
        if job.delivery.webhook_url:
            channels.append("webhook")
        return channels


def _sanitize_dirname(name: str) -> str:
    """Convert a job name to a safe directory name."""
    import re

    safe = re.sub(r"[^\w\-.]", "_", name.strip().lower())
    return safe[:64] or "unnamed"
