"""Langfuse client — conditional initialization based on env vars.

Langfuse v4 instruments OpenAI via monkey-patching (``register_tracing``).
Call ``initialize_langfuse()`` once at startup — after that, every
``AsyncOpenAI`` call is automatically traced.
"""

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

_langfuse_instance: Any = None
_initialized = False
_tracing_registered = False


def is_langfuse_enabled() -> bool:
    """Check if Langfuse env vars are configured."""
    return bool(
        os.environ.get("LANGFUSE_PUBLIC_KEY")
        and os.environ.get("LANGFUSE_SECRET_KEY")
    )


def initialize_langfuse() -> Any:
    """Initialize Langfuse client and register OpenAI tracing.

    Safe to call multiple times — only initializes once.
    Returns the Langfuse client instance, or None if not configured.
    """
    global _langfuse_instance, _initialized, _tracing_registered

    if _initialized:
        return _langfuse_instance

    _initialized = True

    if not is_langfuse_enabled():
        logger.info("Langfuse not configured (missing LANGFUSE_PUBLIC_KEY/LANGFUSE_SECRET_KEY)")
        return None

    try:
        from langfuse import Langfuse
        from langfuse.openai import register_tracing

        _langfuse_instance = Langfuse(
            public_key=os.environ["LANGFUSE_PUBLIC_KEY"],
            secret_key=os.environ["LANGFUSE_SECRET_KEY"],
            host=os.environ.get("LANGFUSE_HOST", "http://localhost:3001"),
        )

        if not _tracing_registered:
            register_tracing()
            _tracing_registered = True
            logger.info("Langfuse OpenAI tracing registered")

        host = os.environ.get("LANGFUSE_HOST", "http://localhost:3001")
        logger.info("Langfuse initialized (host=%s)", host)
        return _langfuse_instance
    except Exception:
        logger.warning("Failed to initialize Langfuse", exc_info=True)
        _langfuse_instance = None
        return None


def get_langfuse() -> Any:
    """Return the shared Langfuse client, or None if not configured."""
    return initialize_langfuse()


def reset() -> None:
    """Reset initialization state (for testing)."""
    global _langfuse_instance, _initialized
    _langfuse_instance = None
    _initialized = False
