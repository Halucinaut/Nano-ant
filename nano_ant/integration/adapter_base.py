"""External adapter abstractions."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from ..tasks.base import EvalReport


class ExternalAdapter(ABC):
    """Abstract adapter used to bridge external projects into Nano Ant."""

    @abstractmethod
    def load_resource(self, resource_id: str) -> str:
        """Load an external resource."""

    @abstractmethod
    def save_resource(self, resource_id: str, content: str) -> None:
        """Persist content into an external resource."""

    @abstractmethod
    def execute(self, resource_content: str, context: dict[str, Any]) -> dict[str, Any]:
        """Run the external project's execution logic."""

    @abstractmethod
    def evaluate(self, execution_result: dict[str, Any]) -> EvalReport:
        """Convert external execution output into an evaluation report."""
