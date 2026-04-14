"""Nano Ant - a lightweight iterative harness agent framework."""

__version__ = "0.3.0"

from .runner import NanoAntRunner, TaskRequest, TaskResult
from .tasks import DefaultEvalRunner, EvalReport, InternalTask, ProjectTask, TaskContext, detect_project_task
from .integration import ExternalAdapter, ExternalTask

__all__ = [
    "NanoAntRunner",
    "TaskRequest",
    "TaskResult",
    "TaskContext",
    "EvalReport",
    "DefaultEvalRunner",
    "InternalTask",
    "ProjectTask",
    "detect_project_task",
    "ExternalAdapter",
    "ExternalTask",
    "__version__",
]
