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
            "config":   {"bot_token": "..."},
        }
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

    return TelegramConnector(
        instance_name=instance_name or "telegram",
        bot_token=bot_token,
    )


__all__ = ["TelegramConnector", "create_connector"]
