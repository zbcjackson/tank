"""Sub-agent benchmark framework.

Measures how well a sub-agent (definition + model profile + its toolset)
completes real tasks on the host, judged only by side effects. The first
suite is ``computer_use`` (desktop GUI tasks); the framework is
suite-agnostic by design — future suites add task YAMLs, future drivers
can measure other seams (see benchmarks README, "Evolution").
"""

from .report import TrialRecord, aggregate, wilson_interval
from .task import (
    BenchTask,
    SuiteConfig,
    TaskError,
    current_platform,
    load_suite,
    load_suite_tasks,
    load_task,
)

__all__ = [
    "BenchTask",
    "SuiteConfig",
    "TaskError",
    "TrialRecord",
    "aggregate",
    "current_platform",
    "load_suite",
    "load_suite_tasks",
    "load_task",
    "wilson_interval",
]
