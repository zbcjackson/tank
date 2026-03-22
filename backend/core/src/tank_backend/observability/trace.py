"""Trace ID generation for linking pipeline metrics to Langfuse traces."""

import uuid


def generate_trace_id(session_id: str) -> str:
    """Generate a unique trace ID for a conversation turn.

    Format: ``{session_id}_{short_uuid}`` — human-readable and unique.
    """
    return f"{session_id}_{uuid.uuid4().hex[:8]}"
