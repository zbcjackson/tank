"""WeChat connector plugin for Tank."""

from __future__ import annotations

from pathlib import Path

from tank_contracts.connector_sdk import require_string_field, validate_spec

from .connector import WeChatConnector


def create_connector(spec: dict) -> WeChatConnector:
    """Instantiate a :class:`WeChatConnector` from a config.yaml entry.

    ``spec`` is the per-instance dict that the plugin registry hands to
    the factory::

        {
            "instance": "my-wechat",
            "config": {
                "account_id": "...",
                "token": "...",
                "base_url": "https://ilinkai.weixin.qq.com",  # optional
                "cdn_base_url": "https://novac2c.cdn.weixin.qq.com/c2c",  # optional
                "group_policy": "disabled",  # optional
                "group_allowlist": [],  # optional
                "voice_in": true,  # optional
                "voice_out": true,  # optional
                "state_dir": "~/.tank/wechat/my-wechat",  # optional
            },
        }
    """
    instance_name, cfg = validate_spec(spec, plugin_name="connector-wechat")

    account_id = require_string_field(
        cfg, "account_id",
        plugin_name="connector-wechat",
        instance_name=instance_name,
        env_var="WECHAT_ACCOUNT_ID",
    )
    token = require_string_field(
        cfg, "token",
        plugin_name="connector-wechat",
        instance_name=instance_name,
        env_var="WECHAT_TOKEN",
    )

    base_url = cfg.get("base_url", "https://ilinkai.weixin.qq.com")
    cdn_base_url = cfg.get("cdn_base_url", "https://novac2c.cdn.weixin.qq.com/c2c")
    group_policy = cfg.get("group_policy", "disabled")
    group_allowlist = cfg.get("group_allowlist") or []
    voice_in = bool(cfg.get("voice_in", True))
    voice_out = bool(cfg.get("voice_out", True))

    state_dir = cfg.get("state_dir", "")
    if not state_dir:
        state_dir = str(Path.home() / ".tank" / "wechat" / (instance_name or "default"))

    return WeChatConnector(
        instance_name=instance_name or "wechat",
        account_id=account_id,
        token=token,
        state_dir=state_dir,
        base_url=base_url,
        cdn_base_url=cdn_base_url,
        group_policy=group_policy,
        group_allowlist=group_allowlist,
        voice_in=voice_in,
        voice_out=voice_out,
    )


__all__ = ["WeChatConnector", "create_connector"]
