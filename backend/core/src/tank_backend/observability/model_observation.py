"""Optional model spans; observability failures never change a model result."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager, suppress
from contextvars import ContextVar
from typing import Any

from .langfuse_client import get_langfuse

call_metadata: ContextVar[dict[str, str] | None] = ContextVar("model_call_metadata", default=None)


@contextmanager
def model_observation(name: str, model: str) -> Iterator[Callable[..., None]]:
    manager: Any = None
    span: Any = None
    try:
        client = get_langfuse()
        if client is not None:
            manager = client.start_as_current_observation(
                name=name, as_type="generation", model=model, metadata=call_metadata.get()
            )
            span = manager.__enter__()
    except Exception:
        manager = None

    def update(**fields: object) -> None:
        if span is None:
            return
        try:
            usage = {
                k: fields[k] for k in ("input_tokens", "output_tokens") if fields.get(k) is not None
            }
            attributes: dict[str, object] = {
                "output": {k: v for k, v in fields.items() if k not in usage}
            }
            if usage:
                attributes["usage_details"] = usage
            if "error" in fields:
                attributes.update(level="ERROR", status_message=str(fields["error"]))
            span.update(**attributes)
        except Exception:
            pass

    try:
        yield update
    except BaseException as exc:
        update(error=type(exc).__name__)
        raise
    finally:
        if manager is not None:
            with suppress(Exception):
                manager.__exit__(None, None, None)
