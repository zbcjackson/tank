"""Feishu / Lark connector plugin for Tank."""

from __future__ import annotations

from tank_contracts.connector_sdk import require_string_field, validate_spec

from .connector import FeishuConnector


def create_connector(spec: dict) -> FeishuConnector:
    """Instantiate a :class:`FeishuConnector` from a config.yaml entry.

    Required fields:

    - ``app_id`` — Feishu app's App ID (cli_xxx). Set via ``${FEISHU_APP_ID}``
      in config.yaml.
    - ``app_secret`` — App Secret from "Credentials & Basic Info".

    Optional fields:

    - ``admin_external_ids`` — list of ``feishu:user:<open_id>`` strings
      authorised to resolve REQUIRE_APPROVAL prompts (handled by the
      shared :class:`ConnectorManager`, not this factory).

    The factory rejects missing fields with a ``ValueError`` whose
    message points operators at the right environment variable. The
    same validation shape Telegram/Slack/Discord use.
    """
    instance_name, cfg = validate_spec(spec, plugin_name="connector-feishu")

    app_id = require_string_field(
        cfg, "app_id",
        plugin_name="connector-feishu",
        instance_name=instance_name,
        env_var="FEISHU_APP_ID",
    )
    app_secret = require_string_field(
        cfg, "app_secret",
        plugin_name="connector-feishu",
        instance_name=instance_name,
        env_var="FEISHU_APP_SECRET",
    )

    return FeishuConnector(
        instance_name=instance_name or "feishu",
        app_id=app_id,
        app_secret=app_secret,
    )


__all__ = ["FeishuConnector", "create_connector"]
