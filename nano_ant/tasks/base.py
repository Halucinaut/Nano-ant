"""Unified task abstractions for internal and external optimization tasks."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any
import json

from ..judge import JudgeSkill


@dataclass
class EvalReport:
    """Structured evaluation result returned by a task context."""

    total_cases: int = 0
    successful_cases: int = 0
    success_rate: float = 0.0
    overall_score: float = 0.0
    case_results: list[dict[str, Any]] = field(default_factory=list)
    passed: bool = True
    summary: str = ""
    errors: list[str] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict)

    def to_test_results(self) -> dict[str, Any]:
        """Convert the report into the shape Judge already understands."""
        details = [
            f"Task Evaluation Summary: {self.summary or 'No summary'}",
            f"Total Cases: {self.total_cases}",
            f"Successful Cases: {self.successful_cases}",
            f"Success Rate: {self.success_rate:.2%}",
            f"Overall Score: {self.overall_score}",
        ]
        if self.errors:
            details.append(f"Errors: {json.dumps(self.errors, ensure_ascii=False)}")
        if self.case_results:
            details.append("Case Results:")
            for item in self.case_results[:10]:
                details.append(json.dumps(item, ensure_ascii=False))
        return {
            "passed": self.passed,
            "output": "\n".join(details),
            "errors": list(self.errors),
            "metadata": {
                "eval_report": self.to_dict(),
            },
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "meta": self.raw.get("meta", {}) if isinstance(self.raw, dict) else {},
            "summary": {
                "passed": self.passed,
                "overall_score": self.overall_score,
                "total_cases": self.total_cases,
                "successful_cases": self.successful_cases,
                "success_rate": self.success_rate,
                "text": self.summary,
            },
            "total_cases": self.total_cases,
            "successful_cases": self.successful_cases,
            "success_rate": self.success_rate,
            "overall_score": self.overall_score,
            "case_results": self.case_results,
            "passed": self.passed,
            "summary_text": self.summary,
            "errors": self.errors,
            "artifacts": self.raw.get("artifacts", []) if isinstance(self.raw, dict) else [],
            "raw": self.raw,
        }

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "EvalReport":
        summary_data = payload.get("summary", {}) if isinstance(payload.get("summary", {}), dict) else {}
        total_cases = int(
            payload.get("total_cases", summary_data.get("total_cases", payload.get("cases", 0))) or 0
        )
        successful_cases = int(
            payload.get("successful_cases", summary_data.get("successful_cases", payload.get("passed_cases", 0))) or 0
        )
        success_rate = payload.get("success_rate", summary_data.get("success_rate"))
        if success_rate is None:
            success_rate = (successful_cases / total_cases) if total_cases else 0.0
        overall_score = float(
            payload.get("overall_score", summary_data.get("overall_score", payload.get("score", success_rate * 100))) or 0.0
        )
        errors = [str(item) for item in payload.get("errors", []) if item]
        execution_error = str(payload.get("execution_error", "") or "")
        if execution_error:
            errors.append(execution_error)
        passed = bool(
            payload.get(
                "passed",
                summary_data.get("passed", not errors and successful_cases >= total_cases if total_cases else not errors),
            )
        )
        raw_summary = payload.get("summary", "")
        summary_text = str(raw_summary or "") if not isinstance(raw_summary, dict) else ""
        if not summary_text and isinstance(summary_data, dict):
            summary_text = str(summary_data.get("text", "") or "")
        return cls(
            total_cases=total_cases,
            successful_cases=successful_cases,
            success_rate=float(success_rate or 0.0),
            overall_score=overall_score,
            case_results=list(payload.get("case_results", payload.get("results", [])) or []),
            passed=passed,
            summary=summary_text,
            errors=errors,
            raw=payload,
        )


class TaskContext(ABC):
    """Unified task interface consumed by the orchestrator."""

    task_type: str = "generic"
    task_name: str = ""
    workspace_path: str = ""

    @abstractmethod
    def load_target(self) -> str:
        """Load the current optimization target."""

    @abstractmethod
    def save_target(self, content: str) -> None:
        """Persist an updated optimization target."""

    @abstractmethod
    def evaluate(self) -> EvalReport:
        """Run the task-specific evaluation."""

    @abstractmethod
    def get_judge_skill(self) -> JudgeSkill:
        """Return the task-specific judge skill."""

    @abstractmethod
    def build_user_goal(self) -> str:
        """Build the user-facing goal supplied to the orchestrator."""

    @abstractmethod
    def build_plan_context(self) -> str:
        """Build extra planning context for the plan role."""
