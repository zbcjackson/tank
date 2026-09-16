"""Desktop control layer — executor capability interface for agents."""

from .executor import (
    BashResult,
    BatchResult,
    BatchStep,
    DesktopExecutor,
    Screenshot,
    create_desktop_executor,
)

__all__ = [
    "BashResult",
    "BatchResult",
    "BatchStep",
    "DesktopExecutor",
    "Screenshot",
    "create_desktop_executor",
]
