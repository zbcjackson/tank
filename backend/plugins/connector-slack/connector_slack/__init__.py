"""Slack connector plugin for Tank."""

from __future__ import annotations

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
    instance_name = spec.get("instance", "")
    cfg = spec.get("config", {}) or {}

    if not isinstance(cfg, dict):
        raise ValueError(
            f"connector-slack '{instance_name}': 'config' must be a mapping"
        )

    bot_token = cfg.get("bot_token")
    if not isinstance(bot_token, str) or not bot_token.strip():
        raise ValueError(
            f"connector-slack '{instance_name}': 'config.bot_token' is "
            "required (set SLACK_BOT_TOKEN in your environment and "
            "reference it as ${SLACK_BOT_TOKEN} in config.yaml)"
        )

    app_token = cfg.get("app_token")
    if not isinstance(app_token, str) or not app_token.strip():
        raise ValueError(
            f"connector-slack '{instance_name}': 'config.app_token' is "
            "required (set SLACK_APP_TOKEN in your environment and "
            "reference it as ${SLACK_APP_TOKEN} in config.yaml)"
        )

    mention_only = bool(cfg.get("mention_only", False))

    return SlackConnector(
        instance_name=instance_name or "slack",
        bot_token=bot_token,
        app_token=app_token,
        mention_only=mention_only,
    )


__all__ = ["SlackConnector", "create_connector"]
