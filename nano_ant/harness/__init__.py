"""Harness Engineering module for Nano Ant.

This module provides core harness capabilities including:
- Effect tracking for auditability and reproducibility
- Structured feedback artifacts for actionable improvements
- Declarative workflow state machines
- Real-time telemetry and observability
- Resource pooling for performance
"""

from .effect_tracker import EffectTracker, Effect, FileWriteEffect, LLMCallEffect
from .feedback_artifact import FeedbackArtifact, FixAction, IssueType, Severity
from .workflow_state_machine import (
    WorkflowStateMachine,
    StateTransition,
    ConditionalTransition,
    TerminalState,
    IterationResult,
)

__all__ = [
    # Effect Tracking
    "EffectTracker",
    "Effect",
    "FileWriteEffect",
    "LLMCallEffect",
    # Feedback System
    "FeedbackArtifact",
    "FixAction",
    "IssueType",
    "Severity",
    # Workflow
    "WorkflowStateMachine",
    "StateTransition",
    "ConditionalTransition",
    "TerminalState",
    "IterationResult",
]
