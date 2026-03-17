"""Runtime context holding the shared interrupt signal."""

from __future__ import annotations

import threading
from dataclasses import dataclass


@dataclass
class RuntimeContext:
    """Shared runtime objects owned by Assistant.

    After the QueueWorker→Processor migration, only interrupt_event remains.
    """

    interrupt_event: threading.Event

    @classmethod
    def create(cls) -> RuntimeContext:
        return cls(interrupt_event=threading.Event())
