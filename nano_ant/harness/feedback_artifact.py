"""Structured feedback system for actionable improvements.

This module replaces text-based feedback with structured, actionable
feedback artifacts that enable precise, data-driven improvements.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional
from datetime import datetime
import uuid


class IssueType(Enum):
    """Types of issues that can be identified."""
    MISSING_IMPL = "missing_implementation"
    INCOMPLETE = "incomplete_implementation"
    BUG = "bug"
    QUALITY = "quality_issue"
    PERFORMANCE = "performance_issue"
    SECURITY = "security_issue"
    TEST_MISSING = "test_missing"
    DOCUMENTATION = "documentation_issue"
    STYLE = "style_issue"


class Severity(Enum):
    """Severity levels for issues."""
    CRITICAL = "critical"  # Blocks functionality, must fix
    MAJOR = "major"        # Significant impact, should fix
    MINOR = "minor"        # Nice to have, fix if time permits
    INFO = "info"          # Suggestion only


@dataclass
class FixAction:
    """An actionable fix suggestion.

    This represents a specific, concrete action that can be taken
to address an issue identified by the Judge.
    """
    # Target location
    target_file: str
    line_start: int = 0
    line_end: int = 0

    # Issue classification
    issue_type: IssueType = IssueType.QUALITY
    severity: Severity = Severity.MINOR

    # Description and guidance
    description: str = ""
    suggested_prompt: str = ""  # Specific prompt for Coding role

    # Additional context
    current_code: str = ""  # The problematic code
    expected_behavior: str = ""  # What it should do

    # Traceability
    trace_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])

    def to_planning_context(self) -> str:
        """Convert to a context string for the Plan role."""
        return f"""
[Fix Required - {self.severity.value.upper()}]
File: {self.target_file}
Lines: {self.line_start}-{self.line_end}
Issue: {self.description}
Suggested Action: {self.suggested_prompt}
"""

    def to_coding_prompt(self) -> str:
        """Convert to a specific prompt for the legacy Coding role."""
        prompt = f"Fix the following issue in {self.target_file}"
        if self.line_start > 0:
            prompt += f" (around line {self.line_start})"
        prompt += f":\n\n{self.description}\n"

        if self.current_code:
            prompt += f"\nCurrent code:\n```\n{self.current_code[:500]}\n```\n"

        if self.expected_behavior:
            prompt += f"\nExpected behavior: {self.expected_behavior}\n"

        return prompt

    def to_action_prompt(self) -> str:
        """Convert to a specific prompt for the Action role."""
        return self.to_coding_prompt()


@dataclass
class MetricScore:
    """A scored metric with explanation."""
    name: str
    score: float  # 0-100
    weight: float  # Importance weight
    explanation: str = ""

    @property
    def weighted_score(self) -> float:
        return self.score * self.weight


@dataclass
class FeedbackArtifact:
    """Structured feedback from Judge to other roles.

    This replaces free-text feedback with a structured artifact that contains:
    - Binary pass/fail decision
    - Numeric score with breakdown
    - List of specific, actionable fixes
    - Confidence level in the assessment
    - Full traceability

    Usage:
        artifact = FeedbackArtifact(
            passed=False,
            score=65,
            fix_actions=[
                FixAction(
                    target_file="main.py",
                    issue_type=IssueType.MISSING_IMPL,
                    severity=Severity.CRITICAL,
                    description="Function 'calculate' has empty body with just 'pass'",
                    suggested_prompt="Implement the calculate function with proper logic"
                )
            ]
        )

        # In Plan role:
        for action in artifact.fix_actions:
            if action.severity == Severity.CRITICAL:
                plan.add_priority_fix(action)
    """

    # Core decision
    passed: bool = False
    score: int = 0  # 0-100

    # Confidence in assessment (0-1)
    confidence: float = 0.8

    # Human-readable summary
    summary: str = ""

    # Structured metrics breakdown
    metrics: List[MetricScore] = field(default_factory=list)

    # Actionable fixes
    fix_actions: List[FixAction] = field(default_factory=list)

    # Additional context
    iteration: int = 0
    trace_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    timestamp: float = field(default_factory=lambda: datetime.now().timestamp())

    # Raw data for debugging
    raw_evaluation: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        """Validate and normalize the artifact."""
        self.score = max(0, min(100, self.score))
        self.confidence = max(0.0, min(1.0, self.confidence))

        # Ensure passed is consistent with score
        if self.score < 80:
            self.passed = False

    @property
    def critical_issues(self) -> List[FixAction]:
        """Get only critical issues."""
        return [a for a in self.fix_actions if a.severity == Severity.CRITICAL]

    @property
    def major_issues(self) -> List[FixAction]:
        """Get major issues."""
        return [a for a in self.fix_actions if a.severity == Severity.MAJOR]

    @property
    def has_critical_issues(self) -> bool:
        """Check if there are any critical issues."""
        return any(a.severity == Severity.CRITICAL for a in self.fix_actions)

    @property
    def weighted_score(self) -> float:
        """Calculate weighted score from metrics."""
        if not self.metrics:
            return self.score
        total_weight = sum(m.weight for m in self.metrics)
        if total_weight == 0:
            return self.score
        return sum(m.weighted_score for m in self.metrics) / total_weight

    def get_actions_by_severity(self, severity: Severity) -> List[FixAction]:
        """Get fix actions filtered by severity."""
        return [a for a in self.fix_actions if a.severity == severity]

    def get_actions_by_type(self, issue_type: IssueType) -> List[FixAction]:
        """Get fix actions filtered by issue type."""
        return [a for a in self.fix_actions if a.issue_type == issue_type]

    def to_planning_feedback(self) -> str:
        """Convert to a feedback string for the Plan role."""
        lines = [
            f"[Judge Feedback - Iteration {self.iteration}]",
            f"Passed: {self.passed}",
            f"Score: {self.score}/100",
            f"Confidence: {self.confidence:.0%}",
            "",
            "Summary:",
            self.summary,
            "",
        ]

        if self.critical_issues:
            lines.append("CRITICAL ISSUES (must fix):")
            for action in self.critical_issues:
                lines.append(f"  - [{action.issue_type.value}] {action.description}")
            lines.append("")

        if self.major_issues:
            lines.append("Major issues:")
            for action in self.major_issues:
                lines.append(f"  - {action.description}")
            lines.append("")

        return "\n".join(lines)

    def to_coding_instructions(self) -> List[str]:
        """Generate specific legacy coding instructions for each fix action."""
        instructions = []

        # Sort by severity
        sorted_actions = sorted(
            self.fix_actions,
            key=lambda a: ({
                Severity.CRITICAL: 0,
                Severity.MAJOR: 1,
                Severity.MINOR: 2,
                Severity.INFO: 3,
            }[a.severity], a.target_file)
        )

        for action in sorted_actions:
            instructions.append(action.to_coding_prompt())

        return instructions

    def to_action_instructions(self) -> List[str]:
        """Generate specific action instructions for each fix action."""
        return [action.to_action_prompt() for action in sorted(
            self.fix_actions,
            key=lambda a: ({
                Severity.CRITICAL: 0,
                Severity.MAJOR: 1,
                Severity.MINOR: 2,
                Severity.INFO: 3,
            }[a.severity], a.target_file)
        )]

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary for checkpointing."""
        return {
            "passed": self.passed,
            "score": self.score,
            "confidence": self.confidence,
            "summary": self.summary,
            "metrics": [
                {
                    "name": m.name,
                    "score": m.score,
                    "weight": m.weight,
                    "explanation": m.explanation,
                }
                for m in self.metrics
            ],
            "fix_actions": [
                {
                    "target_file": a.target_file,
                    "line_start": a.line_start,
                    "line_end": a.line_end,
                    "issue_type": a.issue_type.value,
                    "severity": a.severity.value,
                    "description": a.description,
                    "suggested_prompt": a.suggested_prompt,
                    "trace_id": a.trace_id,
                }
                for a in self.fix_actions
            ],
            "iteration": self.iteration,
            "trace_id": self.trace_id,
            "timestamp": self.timestamp,
            "raw_evaluation": self.raw_evaluation,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "FeedbackArtifact":
        """Deserialize from dictionary."""
        metrics = [
            MetricScore(
                name=m["name"],
                score=m["score"],
                weight=m["weight"],
                explanation=m.get("explanation", ""),
            )
            for m in data.get("metrics", [])
        ]

        fix_actions = [
            FixAction(
                target_file=a["target_file"],
                line_start=a.get("line_start", 0),
                line_end=a.get("line_end", 0),
                issue_type=IssueType(a["issue_type"]),
                severity=Severity(a["severity"]),
                description=a["description"],
                suggested_prompt=a.get("suggested_prompt", ""),
                trace_id=a.get("trace_id", ""),
            )
            for a in data.get("fix_actions", [])
        ]

        return cls(
            passed=data.get("passed", False),
            score=data.get("score", 0),
            confidence=data.get("confidence", 0.8),
            summary=data.get("summary", ""),
            metrics=metrics,
            fix_actions=fix_actions,
            iteration=data.get("iteration", 0),
            trace_id=data.get("trace_id", ""),
            timestamp=data.get("timestamp", 0),
            raw_evaluation=data.get("raw_evaluation", {}) if isinstance(data.get("raw_evaluation", {}), dict) else {},
        )

    def summary_for_context(self) -> str:
        """Get a brief summary for context window efficiency."""
        issue_counts = {}
        for action in self.fix_actions:
            key = f"{action.severity.value}_{action.issue_type.value}"
            issue_counts[key] = issue_counts.get(key, 0) + 1

        parts = [
            f"Score: {self.score}/100",
            f"Passed: {self.passed}",
        ]

        if self.critical_issues:
            parts.append(f"Critical: {len(self.critical_issues)}")
        if self.major_issues:
            parts.append(f"Major: {len(self.major_issues)}")

        return " | ".join(parts)


# Factory functions for common feedback patterns

def create_success_feedback(score: int = 95, summary: str = "") -> FeedbackArtifact:
    """Create a success feedback artifact."""
    return FeedbackArtifact(
        passed=True,
        score=score,
        confidence=0.95,
        summary=summary or "Implementation meets all requirements.",
    )


def create_failure_feedback(
    score: int = 50,
    summary: str = "",
    critical_issues: Optional[List[FixAction]] = None,
) -> FeedbackArtifact:
    """Create a failure feedback artifact."""
    return FeedbackArtifact(
        passed=False,
        score=score,
        confidence=0.85,
        summary=summary or "Implementation has issues that need to be addressed.",
        fix_actions=critical_issues or [],
    )


def create_empty_implementation_feedback(
    file: str,
    function_name: str,
    line: int = 0,
) -> FeedbackArtifact:
    """Create feedback for empty implementation (pass/...)."""
    return FeedbackArtifact(
        passed=False,
        score=40,
        confidence=0.99,
        summary=f"Function '{function_name}' in {file} has empty implementation.",
        fix_actions=[
            FixAction(
                target_file=file,
                line_start=line,
                issue_type=IssueType.MISSING_IMPL,
                severity=Severity.CRITICAL,
                description=f"Function '{function_name}' contains only 'pass' or '...'",
                suggested_prompt=f"Implement the complete logic for function '{function_name}'. "
                               f"Do NOT use 'pass' or '...'. Write the actual implementation.",
            )
        ],
    )


def create_missing_file_feedback(
    required_files: List[str],
    found_files: List[str],
) -> FeedbackArtifact:
    """Create feedback for missing required files."""
    missing = set(required_files) - set(found_files)

    return FeedbackArtifact(
        passed=False,
        score=30,
        confidence=0.95,
        summary=f"Missing required files: {', '.join(missing)}",
        fix_actions=[
            FixAction(
                target_file=f,
                issue_type=IssueType.MISSING_IMPL,
                severity=Severity.CRITICAL,
                description=f"Required file '{f}' was not created",
                suggested_prompt=f"Create the file '{f}' with complete implementation.",
            )
            for f in missing
        ],
    )
