"""DashScope CosyVoice WebSocket client.

Implements the DashScope duplex-streaming protocol:
  run-task → continue-task → finish-task
with interleaved JSON events and binary audio frames.
"""

from __future__ import annotations

import json
import logging
import uuid
from collections.abc import AsyncIterator, Callable

import websockets

from tank_contracts.tts import AudioChunk

logger = logging.getLogger(__name__)

# Region → WebSocket URL mapping.
_WS_URLS = {
    "intl": "wss://dashscope-intl.aliyuncs.com/api-ws/v1/inference",
    "cn": "wss://dashscope.aliyuncs.com/api-ws/v1/inference",
}

DEFAULT_MODEL = "cosyvoice-v3-flash"
DEFAULT_VOICE = "longanyang"
DEFAULT_SAMPLE_RATE = 22050
CHANNELS = 1


class DashScopeError(RuntimeError):
    """Raised when the DashScope API returns a task-failed event."""


class DashScopeClient:
    """WebSocket client for DashScope CosyVoice TTS.

    Opens one WebSocket per synthesis call (same pattern as the ElevenLabs
    engine).  Requests raw PCM to avoid decode overhead in the pipeline.
    """

    def __init__(self, config: dict) -> None:
        self._api_key: str = config["dashscope_api_key"]
        self._model: str = config.get("dashscope_model", DEFAULT_MODEL)
        self._voice_en: str = config.get("dashscope_voice_en", DEFAULT_VOICE)
        self._voice_zh: str = config.get("dashscope_voice_zh", DEFAULT_VOICE)
        region = config.get("dashscope_region", "intl")
        self._ws_url: str = _WS_URLS.get(region, _WS_URLS["intl"])
        self._sample_rate: int = int(config.get("sample_rate", DEFAULT_SAMPLE_RATE))

    def voice_for_language(self, language: str) -> str:
        """Pick a voice name based on the detected language."""
        if language.startswith("zh") or language == "chinese":
            return self._voice_zh
        return self._voice_en

    async def stream(
        self,
        text: str,
        *,
        language: str = "auto",
        voice: str | None = None,
        is_interrupted: Callable[[], bool] | None = None,
    ) -> AsyncIterator[AudioChunk]:
        """Connect to DashScope, synthesise *text*, and yield PCM chunks."""
        resolved_voice = voice or self.voice_for_language(language)
        task_id = str(uuid.uuid4())

        headers = {"Authorization": f"bearer {self._api_key}"}

        async with websockets.connect(
            self._ws_url, additional_headers=headers
        ) as ws:
            # 1. run-task — start a new synthesis task
            await ws.send(json.dumps(self._run_task_msg(task_id, resolved_voice)))

            # Wait for task-started before sending text.
            await self._expect_event(ws, task_id, "task-started")

            # 2. continue-task — send the text to synthesise
            await ws.send(json.dumps(self._continue_task_msg(task_id, text)))

            # 3. finish-task — signal end of input
            await ws.send(json.dumps(self._finish_task_msg(task_id)))

            # 4. Receive audio frames + JSON events until task-finished.
            async for raw in ws:
                if is_interrupted and is_interrupted():
                    logger.info("DashScope: interrupted, closing WebSocket")
                    break

                if isinstance(raw, bytes):
                    yield AudioChunk(
                        data=raw,
                        sample_rate=self._sample_rate,
                        channels=CHANNELS,
                    )
                else:
                    event = json.loads(raw)
                    header = event.get("header", {})
                    event_type = header.get("event", "")

                    if event_type == "task-failed":
                        code = header.get("error_code", "Unknown")
                        msg = header.get("error_message", "Unknown error")
                        raise DashScopeError(
                            f"DashScope task failed: [{code}] {msg}"
                        )

                    if event_type == "task-finished":
                        break

    # ------------------------------------------------------------------
    # Message builders
    # ------------------------------------------------------------------

    def _run_task_msg(self, task_id: str, voice: str) -> dict:
        return {
            "header": {
                "action": "run-task",
                "task_id": task_id,
                "streaming": "duplex",
            },
            "payload": {
                "task_group": "audio",
                "task": "tts",
                "function": "SpeechSynthesizer",
                "model": self._model,
                "parameters": {
                    "text_type": "PlainText",
                    "voice": voice,
                    "format": "pcm",
                    "sample_rate": self._sample_rate,
                    "volume": 50,
                    "rate": 1.0,
                    "pitch": 1.0,
                },
                "input": {},
            },
        }

    @staticmethod
    def _continue_task_msg(task_id: str, text: str) -> dict:
        return {
            "header": {
                "action": "continue-task",
                "task_id": task_id,
                "streaming": "duplex",
            },
            "payload": {
                "input": {"text": text},
            },
        }

    @staticmethod
    def _finish_task_msg(task_id: str) -> dict:
        return {
            "header": {
                "action": "finish-task",
                "task_id": task_id,
                "streaming": "duplex",
            },
            "payload": {"input": {}},
        }

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    async def _expect_event(ws, task_id: str, expected: str) -> dict:
        """Read JSON messages until the expected event arrives.

        Binary frames received before the expected event are discarded
        (shouldn't happen, but guards against protocol quirks).
        """
        async for raw in ws:
            if isinstance(raw, bytes):
                continue
            event = json.loads(raw)
            header = event.get("header", {})
            if header.get("event") == "task-failed":
                code = header.get("error_code", "Unknown")
                msg = header.get("error_message", "Unknown error")
                raise DashScopeError(
                    f"DashScope task failed: [{code}] {msg}"
                )
            if header.get("event") == expected:
                return event
        raise DashScopeError(
            f"WebSocket closed before receiving '{expected}' for task {task_id}"
        )
