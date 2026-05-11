"""Telegram connector plugin for Tank."""

from __future__ import annotations

from .connector import TelegramConnector


def create_connector(spec: dict) -> TelegramConnector:
    """Instantiate a :class:`TelegramConnector` from a config.yaml entry.

    ``spec`` is the per-instance dict that the plugin registry hands to
    the factory. It matches the shape built by
    :func:`tank_backend.api.server._init_connectors`::

        {
            "instance": <instance name, e.g. "my-telegram-bot">,
            "config":   {
                "bot_token": "...",
                "voice_in": true,   # optional; default true
                "voice_out": true,  # optional; default true
            },
        }

    ``voice_in`` / ``voice_out`` are wired through to the connector's
    capabilities and handler registration. Disabling either doesn't
    affect ASR/TTS availability in AppContext — it just means this
    particular connector instance won't touch voice, which is useful
    for operators who want a text-only Telegram bot even though the
    rest of Tank has voice configured.
    """
    instance_name = spec.get("instance", "")
    cfg = spec.get("config", {}) or {}

    if not isinstance(cfg, dict):
        raise ValueError(
            f"connector-telegram '{instance_name}': 'config' must be a mapping"
        )

    bot_token = cfg.get("bot_token")
    if not isinstance(bot_token, str) or not bot_token.strip():
        raise ValueError(
            f"connector-telegram '{instance_name}': 'config.bot_token' is "
            "required (set TELEGRAM_BOT_TOKEN in your environment and "
            "reference it as ${TELEGRAM_BOT_TOKEN} in config.yaml)"
        )

    voice_in = bool(cfg.get("voice_in", True))
    voice_out = bool(cfg.get("voice_out", True))

    return TelegramConnector(
        instance_name=instance_name or "telegram",
        bot_token=bot_token,
        voice_in=voice_in,
        voice_out=voice_out,
    )


__all__ = ["TelegramConnector", "create_connector"]
