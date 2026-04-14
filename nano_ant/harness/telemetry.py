"""Real-time telemetry and observability for the agent system.

This module provides probes and telemetry collection for monitoring
agent execution in real-time, enabling early detection of issues
and short-circuiting of failing trajectories.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set
from datetime import datetime
import time


class EventLevel(Enum):
    """Severity levels for telemetry events."""
    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


@dataclass
class TelemetryEvent:
    """A telemetry event."""
    level: EventLevel
    event_type: str
    message: str
    timestamp: float = field(default_factory=time.time)
    source: str = ""  # Role or component that generated the event
    iteration: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "level": self.level.value,
            "event_type": self.event_type,
            "message": self.message,
            "timestamp": self.timestamp,
            "source": self.source,
            "iteration": self.iteration,
            "metadata": self.metadata,
        }


# Event factory functions

def debug_event(event_type: str, message: str, **kwargs) -> TelemetryEvent:
    return TelemetryEvent(EventLevel.DEBUG, event_type, message, metadata=kwargs)


def info_event(event_type: str, message: str, **kwargs) -> TelemetryEvent:
    return TelemetryEvent(EventLevel.INFO, event_type, message, metadata=kwargs)


def warning_event(event_type: str, message: str, **kwargs) -> TelemetryEvent:
    return TelemetryEvent(EventLevel.WARNING, event_type, message, metadata=kwargs)


def error_event(event_type: str, message: str, **kwargs) -> TelemetryEvent:
    return TelemetryEvent(EventLevel.ERROR, event_type, message, metadata=kwargs)


def critical_event(event_type: str, message: str, **kwargs) -> TelemetryEvent:
    return TelemetryEvent(EventLevel.CRITICAL, event_type, message, metadata=kwargs)


class Probe(ABC):
    """Abstract base class for telemetry probes."""

    @abstractmethod
    def check(self, data: Any) -> Optional[TelemetryEvent]:
        """Check data and return an event if an issue is detected."""
        pass


class PlanComplexityProbe(Probe):
    """Probe that checks if a plan is too complex."""

    def __init__(self, max_files: int = 10, max_steps: int = 5):
        self.max_files = max_files
        self.max_steps = max_steps

    def check(self, plan_data: Dict[str, Any]) -> Optional[TelemetryEvent]:
        files = plan_data.get("files_to_create", [])
        steps = plan_data.get("total_steps", 1)
        mode = plan_data.get("planning_mode", "single_step")

        if len(files) > self.max_files:
            return warning_event(
                "high_complexity",
                f"Plan has {len(files)} files, consider breaking into smaller tasks",
                files_count=len(files),
                max_files=self.max_files,
            )

        if steps > self.max_steps:
            return warning_event(
                "many_steps",
                f"Multi-step plan has {steps} steps, may take long to complete",
                steps=steps,
            )

        return None


class CodeQualityProbe(Probe):
    """Probe that checks code quality issues."""

    FORBIDDEN_PATTERNS = ["pass", "...", "TODO", "FIXME", "XXX"]

    def check(self, code: str) -> List[TelemetryEvent]:
        events = []
        lines = code.split("\n")

        for i, line in enumerate(lines, 1):
            stripped = line.strip()

            # Check for empty implementations
            if stripped == "pass" or stripped == "...":
                events.append(error_event(
                    "empty_implementation",
                    f"Line {i}: Empty implementation detected ({stripped})",
                    line=i,
                    pattern=stripped,
                ))

            # Check for TODO/FIXME
            for pattern in ["TODO", "FIXME", "XXX"]:
                if pattern in stripped:
                    events.append(warning_event(
                        "incomplete_marker",
                        f"Line {i}: Found {pattern} marker",
                        line=i,
                        pattern=pattern,
                    ))

        # Check for basic syntax issues
        open_parens = code.count("(") - code.count(")")
        open_brackets = code.count("[") - code.count("]")
        open_braces = code.count("{") - code.count("}")

        if open_parens != 0:
            events.append(error_event(
                "syntax_error",
                f"Unbalanced parentheses: {open_parens} unclosed",
                unclosed=open_parens,
            ))

        if open_brackets != 0:
            events.append(error_event(
                "syntax_error",
                f"Unbalanced brackets: {open_brackets} unclosed",
                unclosed=open_brackets,
            ))

        if open_braces != 0:
            events.append(error_event(
                "syntax_error",
                f"Unbalanced braces: {open_braces} unclosed",
                unclosed=open_braces,
            ))

        return events


class TestResultProbe(Probe):
    """Probe that analyzes test results."""

    def check(self, test_results: Dict[str, Any]) -> List[TelemetryEvent]:
        events = []

        if not test_results.get("passed", False):
            errors = test_results.get("errors", [])
            events.append(error_event(
                "test_failure",
                f"Tests failed with {len(errors)} error(s)",
                errors=errors,
            ))

            # Check for specific error patterns
            output = test_results.get("output", "")
            if "ImportError" in output:
                events.append(warning_event(
                    "missing_dependency",
                    "Import error detected, may need to install dependencies",
                ))
            if "SyntaxError" in output:
                events.append(critical_event(
                    "syntax_error",
                    "Syntax error in generated code",
                ))

        return events


class IterationTelemetry:
    """Real-time telemetry collector for agent iterations.

    This class collects events from various probes during execution
    and provides short-circuit logic to abort failing trajectories early.

    Usage:
        telemetry = IterationTelemetry()

        # In orchestrator:
        events = telemetry.on_plan_created(plan_output)
        for event in events:
            if event.level == EventLevel.CRITICAL:
                logger.error(f"Critical issue: {event.message}")

        if telemetry.should_short_circuit(iteration_history):
            logger.info("Short-circuiting due to repeated failures")
            break
    """

    def __init__(
        self,
        short_circuit_threshold: int = 3,
        score_threshold: int = 30,
    ):
        self.short_circuit_threshold = short_circuit_threshold
        self.score_threshold = score_threshold
        self._events: List[TelemetryEvent] = []
        self._probes: Dict[str, Probe] = {
            "plan_complexity": PlanComplexityProbe(),
            "code_quality": CodeQualityProbe(),
            "test_result": TestResultProbe(),
        }
        self._handler: Optional[Callable[[TelemetryEvent], None]] = None

    def set_event_handler(self, handler: Callable[[TelemetryEvent], None]) -> None:
        """Set a handler for telemetry events."""
        self._handler = handler

    def emit(self, event: TelemetryEvent) -> None:
        """Emit a telemetry event."""
        self._events.append(event)
        if self._handler:
            self._handler(event)

    def on_iteration_start(self, iteration: int) -> None:
        """Called at the start of each iteration."""
        self.emit(info_event(
            "iteration_start",
            f"Starting iteration {iteration}",
            iteration=iteration,
        ))

    def on_plan_created(
        self,
        iteration: int,
        plan_data: Dict[str, Any],
    ) -> List[TelemetryEvent]:
        """Analyze a plan and return any issues."""
        events = []

        # Run plan complexity probe
        probe = self._probes.get("plan_complexity")
        if probe:
            event = probe.check(plan_data)
            if event:
                event.iteration = iteration
                event.source = "plan"
                events.append(event)
                self.emit(event)

        # Emit info about plan
        mode = plan_data.get("planning_mode", "single_step")
        files = len(plan_data.get("files_to_create", []))
        self.emit(info_event(
            "plan_created",
            f"Plan created: {mode} mode, {files} files",
            iteration=iteration,
            planning_mode=mode,
            files_count=files,
        ))

        return events

    def on_action_generated(
        self,
        iteration: int,
        action_output: str,
        role: str = "action",
    ) -> List[TelemetryEvent]:
        """Analyze generated action output and return any issues."""
        events = []

        # Run code quality probe
        probe = self._probes.get("code_quality")
        if probe:
            quality_events = probe.check(action_output)
            for event in quality_events:
                event.iteration = iteration
                event.source = role
                events.append(event)
                self.emit(event)

        # Emit summary
        if not any(e.level in (EventLevel.ERROR, EventLevel.CRITICAL) for e in events):
            lines = len(action_output.split("\n"))
            self.emit(info_event(
                "action_generated",
                f"Action output generated: {lines} lines",
                iteration=iteration,
                lines=lines,
            ))

        return events

    def on_code_generated(
        self,
        iteration: int,
        code: str,
        role: str = "coding",
    ) -> List[TelemetryEvent]:
        """Backward-compatible alias for older callers."""
        return self.on_action_generated(iteration, code, role)

    def on_tests_executed(
        self,
        iteration: int,
        test_results: Dict[str, Any],
    ) -> List[TelemetryEvent]:
        """Analyze test results and return any issues."""
        events = []

        # Run test result probe
        probe = self._probes.get("test_result")
        if probe:
            test_events = probe.check(test_results)
            for event in test_events:
                event.iteration = iteration
                event.source = "test"
                events.append(event)
                self.emit(event)

        # Emit summary if no errors
        if test_results.get("passed", False):
            self.emit(info_event(
                "tests_passed",
                "All tests passed",
                iteration=iteration,
            ))

        return events

    def on_judge_evaluation(
        self,
        iteration: int,
        passed: bool,
        score: int,
        feedback: str,
    ) -> None:
        """Record judge evaluation."""
        level = EventLevel.INFO if passed else EventLevel.WARNING
        self.emit(TelemetryEvent(
            level=level,
            event_type="judge_evaluation",
            message=f"Judge: {'passed' if passed else 'failed'} with score {score}",
            iteration=iteration,
            source="judge",
            metadata={"passed": passed, "score": score, "feedback_preview": feedback[:200]},
        ))

    def should_short_circuit(
        self,
        iteration: int,
        score_history: List[int],
    ) -> tuple[bool, str]:
        """Determine if we should short-circuit this trajectory.

        Returns (should_stop, reason) tuple.
        """
        # Check for consecutive low scores
        if len(score_history) >= self.short_circuit_threshold:
            recent_scores = score_history[-self.short_circuit_threshold:]
            if all(s < self.score_threshold for s in recent_scores):
                reason = (
                    f"Short-circuiting: {self.short_circuit_threshold} consecutive "
                    f"scores below {self.score_threshold}"
                )
                self.emit(warning_event(
                    "short_circuit",
                    reason,
                    iteration=iteration,
                    recent_scores=recent_scores,
                ))
                return True, reason

        # Check for score degradation
        if len(score_history) >= 4:
            # Check if scores are consistently going down
            recent = score_history[-4:]
            if all(recent[i] > recent[i+1] for i in range(len(recent)-1)):
                reason = "Short-circuiting: Scores consistently degrading"
                self.emit(warning_event(
                    "degrading_performance",
                    reason,
                    iteration=iteration,
                    scores=recent,
                ))
                return True, reason

        return False, ""

    def get_events(
        self,
        level: Optional[EventLevel] = None,
        iteration: Optional[int] = None,
    ) -> List[TelemetryEvent]:
        """Get events with optional filtering."""
        events = self._events

        if level:
            events = [e for e in events if e.level == level]

        if iteration is not None:
            events = [e for e in events if e.iteration == iteration]

        return events

    def get_error_count(self, iteration: Optional[int] = None) -> int:
        """Count errors, optionally filtered by iteration."""
        events = self.get_events(level=EventLevel.ERROR, iteration=iteration)
        return len(events)

    def get_warning_count(self, iteration: Optional[int] = None) -> int:
        """Count warnings, optionally filtered by iteration."""
        events = self.get_events(level=EventLevel.WARNING, iteration=iteration)
        return len(events)

    def summary(self) -> Dict[str, Any]:
        """Get a summary of all telemetry."""
        by_level: Dict[str, int] = {}
        by_type: Dict[str, int] = {}

        for event in self._events:
            level_key = event.level.value
            by_level[level_key] = by_level.get(level_key, 0) + 1

            by_type[event.event_type] = by_type.get(event.event_type, 0) + 1

        return {
            "total_events": len(self._events),
            "by_level": by_level,
            "by_type": by_type,
            "error_count": self.get_error_count(),
            "warning_count": self.get_warning_count(),
        }

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "events": [e.to_dict() for e in self._events],
            "summary": self.summary(),
        }

    def clear(self) -> None:
        """Clear all events."""
        self._events.clear()
