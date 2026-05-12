"""Discord connector plugin for Tank."""

from __future__ import annotations

from tank_contracts.connector_sdk import require_string_field, validate_spec

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
    instance_name, cfg = validate_spec(spec, plugin_name="connector-discord")

    bot_token = require_string_field(
        cfg, "bot_token",
        plugin_name="connector-discord",
        instance_name=instance_name,
        env_var="DISCORD_BOT_TOKEN",
    )

    return DiscordConnector(
        instance_name=instance_name or "discord",
        bot_token=bot_token,
    )


__all__ = ["DiscordConnector", "create_connector"]
