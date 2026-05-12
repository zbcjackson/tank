"""Factory helpers for connector plugins.

Every connector plugin ships a ``create_connector(spec)`` factory that
the Tank runtime invokes with a dict like::

    {
        "instance": "my-bot",
        "config":   {"bot_token": "xoxb-...", ...},
    }

The three plugins in-tree today (Telegram, Slack, Discord) all do the
same ~15 lines of validation before they hand arguments to their
platform-specific ``__init__``. Those 15 lines are the prime candidate
for consolidation — not because the logic is hard, but because each
plugin phrases the error messages slightly differently, which makes
debugging a mis-configured deployment harder than it should be.

``validate_spec`` and ``require_string_field`` replace that inlined
work with a shared, uniformly-formatted validation path. Plugin
factories shrink to the platform-specific decisions (which fields to
require, how to assemble the final ``__init__`` call).
"""

from __future__ import annotations


def validate_spec(spec: dict, *, plugin_name: str) -> tuple[str, dict]:
    """Split a factory ``spec`` into ``(instance_name, config)``.

    The Tank runtime always hands connector factories a dict with
    ``instance`` and ``config`` keys; this function extracts them with
    validation and returns a normalised pair.

    Returns:
        A ``(instance_name, cfg)`` tuple. ``instance_name`` defaults to
        ``""`` when the key is absent — plugin factories can fall back
        to a sensible default (e.g. the platform name) before handing
        the value to their ``Connector`` subclass.

    Raises:
        ValueError: When ``spec["config"]`` exists and isn't a mapping.
            The error message includes ``plugin_name`` and the observed
            instance name so operators can grep their config for the
            offending block. ``None`` and ``{}`` are both accepted and
            treated as an empty config.
    """
    instance_name = spec.get("instance", "")
    raw_cfg = spec.get("config")

    # ``None`` and ``{}`` are both "no config" — return an empty dict
    # so downstream ``require_string_field`` calls raise the proper
    # "missing field" error rather than a cryptic attribute-lookup one.
    if raw_cfg is None:
        return instance_name, {}

    if not isinstance(raw_cfg, dict):
        raise ValueError(
            f"{plugin_name} '{instance_name}': 'config' must be a mapping, "
            f"got {type(raw_cfg).__name__}"
        )

    return instance_name, raw_cfg


def require_string_field(
    cfg: dict,
    field: str,
    *,
    plugin_name: str,
    instance_name: str,
    env_var: str | None = None,
) -> str:
    """Extract a required non-empty string field from a config dict.

    Raises a :class:`ValueError` with a consistent, operator-friendly
    message when the field is missing, wrong-typed, or whitespace-only.
    If ``env_var`` is provided it's included in the error message as a
    hint pointing operators at the environment-variable convention the
    Tank plugins follow (``${VAR_NAME}`` interpolation in ``config.yaml``).

    Example error message::

        connector-slack 'my-bot': 'config.bot_token' is required
        (set SLACK_BOT_TOKEN in your environment and reference it as
        ${SLACK_BOT_TOKEN} in config.yaml)

    Returns:
        The trimmed-whitespace-but-otherwise-untouched string value.
        Callers get back exactly what the operator wrote, just verified
        to be non-empty.
    """
    value = cfg.get(field)
    if not isinstance(value, str) or not value.strip():
        hint = ""
        if env_var is not None:
            hint = (
                f" (set {env_var} in your environment and reference it as "
                f"${{{env_var}}} in config.yaml)"
            )
        raise ValueError(
            f"{plugin_name} '{instance_name}': 'config.{field}' is required"
            + hint
        )
    return value


__all__ = [
    "require_string_field",
    "validate_spec",
]
