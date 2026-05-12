"""Telegram connector plugin for Tank."""

from __future__ import annotations

from tank_contracts.connector_sdk import require_string_field, validate_spec

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
    instance_name, cfg = validate_spec(spec, plugin_name="connector-telegram")

    bot_token = require_string_field(
        cfg, "bot_token",
        plugin_name="connector-telegram",
        instance_name=instance_name,
        env_var="TELEGRAM_BOT_TOKEN",
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
