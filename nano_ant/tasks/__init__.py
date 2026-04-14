"""Task abstractions for Nano Ant."""

from .base import EvalReport, TaskContext
from .default_eval_runner import DefaultEvalRunner
from .internal_task import InternalTask
from .project_task import ProjectTask, detect_project_task

__all__ = ["EvalReport", "TaskContext", "DefaultEvalRunner", "InternalTask", "ProjectTask", "detect_project_task"]
