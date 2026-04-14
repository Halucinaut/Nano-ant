"""Context management for the agent."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
import json
import time

from ..harness.feedback_artifact import FeedbackArtifact


@dataclass
class IterationRecord:
    """Record of a single iteration."""

    iteration: int
    leader_output: dict[str, Any] = field(default_factory=dict)
    plan_output: dict[str, Any] = field(default_factory=dict)
    action_output: dict[str, Any] = field(default_factory=dict)
    coding_output: dict[str, Any] = field(default_factory=dict)
    judge_output: dict[str, Any] = field(default_factory=dict)
    feedback_artifact: dict[str, Any] = field(default_factory=dict)
    state_delta: dict[str, Any] = field(default_factory=dict)
    iteration_report: dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)


class Context:
    """Manages global context and conversation history for the agent."""

    def __init__(self, user_goal: str, workspace_path: str):
        self.user_goal = user_goal
        self.workspace_path = workspace_path
        self.iteration_history: list[IterationRecord] = []
        self.global_state: dict[str, Any] = {
            "total_iterations": 0,
            "best_score": 0,
            "best_iteration": -1,
            "no_improvement_count": 0,
            "status": "initialized",
        }
        self._start_time = time.time()

    def _summarize_iteration(self, record: IterationRecord) -> dict[str, Any]:
        """Build a compact iteration summary for strategy consumers."""
        plan_meta = record.plan_output.get("metadata", {})
        action_meta = record.action_output.get("metadata", {})
        judge_meta = record.judge_output.get("metadata", {})
        report = record.iteration_report if isinstance(record.iteration_report, dict) else {}

        return {
            "iteration": record.iteration,
            "plan_summary": plan_meta.get("iteration_goal", plan_meta.get("expected_outcome", "")),
            "action_summary": action_meta.get("summary", ""),
            "score": judge_meta.get("score", 0),
            "passed": judge_meta.get("passed", False),
            "key_issues": judge_meta.get("issues", [])[:5],
            "stop_recommendation": judge_meta.get("stop_recommendation", "continue"),
            "state_delta": report.get("state_delta", record.state_delta),
        }

    def add_iteration(self, record: IterationRecord) -> None:
        """Add an iteration record to history."""
        self.iteration_history.append(record)
        self.global_state["total_iterations"] = len(self.iteration_history)

    def get_last_iteration(self) -> IterationRecord | None:
        """Get the most recent iteration record."""
        return self.iteration_history[-1] if self.iteration_history else None

    def get_summary(self, last_n: int = 3) -> str:
        """Get a summary of recent iterations."""
        if not self.iteration_history:
            return "No iterations completed yet."

        recent = self.iteration_history[-last_n:]
        summary_parts = [f"[Goal]: {self.user_goal}"]
        summary_parts.append(f"[Total Iterations]: {len(self.iteration_history)}")
        summary_parts.append(f"[Best Score]: {self.global_state['best_score']} (iter {self.global_state['best_iteration']})")
        summary_parts.append("\n[Recent Iterations]:")

        for record in recent:
            judge_meta = record.judge_output.get("metadata", {})
            summary_parts.append(
                f"\n--- Iteration {record.iteration} ---\n"
                f"Status: {judge_meta.get('passed', False)}\n"
                f"Score: {judge_meta.get('score', 0)}\n"
                f"Feedback: {judge_meta.get('feedback', 'N/A')[:200]}"
            )

        return "\n".join(summary_parts)

    def get_recent_iteration_summaries(self, last_n: int = 3) -> list[dict[str, Any]]:
        """Return compact summaries of the most recent iterations."""
        if not self.iteration_history:
            return []
        return [self._summarize_iteration(record) for record in self.iteration_history[-last_n:]]

    def get_known_failure_patterns(self, last_n: int = 5) -> list[str]:
        """Extract repeated issue patterns from recent judge outputs."""
        issue_counts: dict[str, int] = {}
        for record in self.iteration_history[-last_n:]:
            issues = record.judge_output.get("metadata", {}).get("issues", [])
            for issue in issues:
                issue_counts[issue] = issue_counts.get(issue, 0) + 1

        repeated = [issue for issue, count in issue_counts.items() if count > 1]
        return repeated[:5]

    def get_best_attempt_summary(self) -> dict[str, Any]:
        """Return a compact summary of the best-scoring attempt so far."""
        best_iteration = self.global_state.get("best_iteration", -1)
        if best_iteration < 0:
            return {
                "best_iteration": -1,
                "best_score": self.global_state.get("best_score", 0),
                "summary": "",
                "remaining_gaps": [],
            }

        for record in self.iteration_history:
            if record.iteration == best_iteration:
                summary = self._summarize_iteration(record)
                return {
                    "best_iteration": best_iteration,
                    "best_score": self.global_state.get("best_score", 0),
                    "summary": summary.get("action_summary") or summary.get("plan_summary", ""),
                    "remaining_gaps": summary.get("key_issues", []),
                }

        return {
            "best_iteration": best_iteration,
            "best_score": self.global_state.get("best_score", 0),
            "summary": "",
            "remaining_gaps": [],
        }

    def build_leader_context(self, current_iteration: int, score_history: list[int] | None = None) -> dict[str, Any]:
        """Build a memory view tailored for the Leader role."""
        score_series = list(score_history or [])
        latest_feedback = self.global_state.get("latest_feedback_artifact")
        latest_feedback_summary = ""
        if latest_feedback:
            try:
                latest_feedback_summary = FeedbackArtifact.from_dict(latest_feedback).summary_for_context()
            except Exception:
                latest_feedback_summary = ""

        return {
            "goal": self.user_goal,
            "workspace_path": self.workspace_path,
            "current_iteration": current_iteration,
            "best_score": self.global_state.get("best_score", 0),
            "best_iteration": self.global_state.get("best_iteration", -1),
            "score_history": score_series,
            "recent_iterations": self.get_recent_iteration_summaries(),
            "latest_feedback_summary": latest_feedback_summary,
            "best_attempt": self.get_best_attempt_summary(),
            "known_failure_patterns": self.get_known_failure_patterns(),
            "current_strategy": self.global_state.get("leader_meta_state", {}).get("current_strategy", ""),
            "leader_notes": self.global_state.get("leader_meta_state", {}).get("leader_notes", ""),
            "constraints": self.global_state.get("constraints", []),
        }

    def update_best(self, score: int, iteration: int) -> bool:
        """Update best score if current is better. Returns True if improved."""
        if score > self.global_state["best_score"]:
            self.global_state["best_score"] = score
            self.global_state["best_iteration"] = iteration
            self.global_state["no_improvement_count"] = 0
            return True
        else:
            self.global_state["no_improvement_count"] += 1
            return False

    def get_last_report(self) -> dict[str, Any]:
        """Return the most recent iteration report."""
        if not self.iteration_history:
            return {}
        return self.iteration_history[-1].iteration_report

    def get_feedback_for_plan(self) -> str:
        """Get feedback summary for Plan role."""
        parts: list[str] = []

        task_plan_context = self.global_state.get("task_plan_context")
        if task_plan_context:
            parts.append("[Task Context]")
            parts.append(str(task_plan_context))

        leader_meta_state = self.global_state.get("leader_meta_state", {})
        leader_guidance = self.global_state.get("leader_guidance", {})
        if leader_meta_state or leader_guidance:
            lines = ["[Leader Strategy Guidance]"]
            current_strategy = leader_meta_state.get("current_strategy")
            if current_strategy:
                lines.append(f"- Current Strategy: {current_strategy}")
            blocked_by = leader_meta_state.get("blocked_by")
            if blocked_by:
                lines.append(f"- Blocked By: {blocked_by}")
            leader_notes = leader_meta_state.get("leader_notes")
            if leader_notes:
                lines.append(f"- Notes: {leader_notes}")
            instructions = leader_guidance.get("instructions_for_plan")
            if instructions:
                lines.append(f"- Instructions For Plan: {instructions}")
            parts.append("\n".join(lines))

        artifact_data = self.global_state.get("latest_feedback_artifact")
        if artifact_data:
            try:
                artifact = FeedbackArtifact.from_dict(artifact_data)
                parts.append(artifact.to_planning_feedback())
                action_instructions = artifact.to_action_instructions()
                if action_instructions:
                    parts.append("[Structured Fix Instructions]")
                    parts.extend(f"- {instruction}" for instruction in action_instructions[:5])
            except Exception:
                pass

        if not self.iteration_history:
            return "\n".join(parts)

        last = self.iteration_history[-1]
        last_report = self.get_last_report()
        judge_meta = last.judge_output.get("metadata", {})

        feedback_parts = [
            f"Last iteration (#{last.iteration}) result:",
            f"- Passed: {judge_meta.get('passed', False)}",
            f"- Score: {judge_meta.get('score', 0)}",
            f"- Feedback: {judge_meta.get('feedback', '')}",
        ]
        if last_report:
            feedback_parts.append(f"- Iteration Goal: {last_report.get('iteration_goal', '')}")
            feedback_parts.append(f"- Files Modified: {json.dumps(last_report.get('files_modified', []), ensure_ascii=False)}")

        issues = judge_meta.get("issues", [])
        if issues:
            feedback_parts.append(f"- Issues: {json.dumps(issues, ensure_ascii=False)}")

        parts.append("\n".join(feedback_parts))
        return "\n\n".join(part for part in parts if part)

    def to_dict(self) -> dict[str, Any]:
        """Serialize context to dictionary."""
        return {
            "user_goal": self.user_goal,
            "workspace_path": self.workspace_path,
            "global_state": self.global_state,
            "iteration_history": [
                {
                    "iteration": r.iteration,
                    "leader_output": r.leader_output,
                    "plan_output": r.plan_output,
                    "action_output": r.action_output,
                    "coding_output": r.coding_output,
                    "judge_output": r.judge_output,
                    "feedback_artifact": r.feedback_artifact,
                    "state_delta": r.state_delta,
                    "iteration_report": r.iteration_report,
                    "timestamp": r.timestamp,
                }
                for r in self.iteration_history
            ],
            "start_time": self._start_time,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Context":
        """Deserialize context from dictionary."""
        ctx = cls(data["user_goal"], data["workspace_path"])
        ctx.global_state = data["global_state"]
        ctx._start_time = data.get("start_time", time.time())

        for r_data in data.get("iteration_history", []):
            record = IterationRecord(
                iteration=r_data["iteration"],
                leader_output=r_data["leader_output"],
                plan_output=r_data["plan_output"],
                action_output=r_data.get("action_output", r_data.get("coding_output", {})),
                coding_output=r_data.get("coding_output", r_data.get("action_output", {})),
                judge_output=r_data["judge_output"],
                feedback_artifact=r_data.get("feedback_artifact", {}),
                state_delta=r_data.get("state_delta", {}),
                iteration_report=r_data.get("iteration_report", {}),
                timestamp=r_data["timestamp"],
            )
            ctx.iteration_history.append(record)

        return ctx

    def get_elapsed_time(self) -> float:
        """Get elapsed time in seconds."""
        return time.time() - self._start_time
