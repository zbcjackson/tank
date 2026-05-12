"""Discord connector plugin for Tank."""

from __future__ import annotations

from .connector import DiscordConnector


def create_connector(spec: dict) -> DiscordConnector:
    """Instantiate a :class:`DiscordConnector` from a config.yaml entry.

    ``spec`` is the per-instance dict the plugin registry hands to the
    factory. Matches the shape built by
    :func:`tank_backend.api.server._init_connectors`::

        {
            "instance": <instance name, e.g. "my-discord-bot">,
            "config":   {
                "bot_token": "...",
                # allowlist, unauthorized_reply — handled by
                # ConnectorManager, not this factory.
            },
        }

    Discord's single-token model makes this factory simpler than Slack's
    (no app_token). Missing ``bot_token`` raises :class:`ValueError`
    with a message pointing operators at the right environment
    variable.
    """
    instance_name = spec.get("instance", "")
    cfg = spec.get("config", {}) or {}

    if not isinstance(cfg, dict):
        raise ValueError(
            f"connector-discord '{instance_name}': 'config' must be a mapping"
        )

    bot_token = cfg.get("bot_token")
    if not isinstance(bot_token, str) or not bot_token.strip():
        raise ValueError(
            f"connector-discord '{instance_name}': 'config.bot_token' is "
            "required (set DISCORD_BOT_TOKEN in your environment and "
            "reference it as ${DISCORD_BOT_TOKEN} in config.yaml)"
        )

    return DiscordConnector(
        instance_name=instance_name or "discord",
        bot_token=bot_token,
    )


__all__ = ["DiscordConnector", "create_connector"]
