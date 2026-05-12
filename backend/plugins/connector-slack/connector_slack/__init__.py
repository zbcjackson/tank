"""Slack connector plugin for Tank."""

from __future__ import annotations

from tank_contracts.connector_sdk import require_string_field, validate_spec

from .connector import SlackConnector


def create_connector(spec: dict) -> SlackConnector:
    """Instantiate a :class:`SlackConnector` from a config.yaml entry.

    ``spec`` is the per-instance dict the plugin registry hands to the
    factory. Matches the shape built by
    :func:`tank_backend.api.server._init_connectors`::

        {
            "instance": <instance name, e.g. "my-slack-bot">,
            "config":   {
                "bot_token": "xoxb-...",
                "app_token": "xapp-...",
                "mention_only": false,  # optional; default false
                # allowlist, unauthorized_reply — handled by ConnectorManager,
                # not this factory.
            },
        }

    Both tokens are required — the bot token authorises Web API calls,
    the app token authorises the Socket Mode WebSocket. Missing either
    raises :class:`ValueError` with a message that points operators at
    the right environment variable to set.

    ``mention_only`` (default ``false``) makes the bot ignore channel
    messages that don't mention it. DMs always get through regardless.
    """
    instance_name, cfg = validate_spec(spec, plugin_name="connector-slack")

    bot_token = require_string_field(
        cfg, "bot_token",
        plugin_name="connector-slack",
        instance_name=instance_name,
        env_var="SLACK_BOT_TOKEN",
    )
    app_token = require_string_field(
        cfg, "app_token",
        plugin_name="connector-slack",
        instance_name=instance_name,
        env_var="SLACK_APP_TOKEN",
    )
    mention_only = bool(cfg.get("mention_only", False))

    return SlackConnector(
        instance_name=instance_name or "slack",
        bot_token=bot_token,
        app_token=app_token,
        mention_only=mention_only,
    )


__all__ = ["SlackConnector", "create_connector"]
