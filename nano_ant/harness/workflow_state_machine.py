"""Declarative workflow state machine for agent orchestration.

This module replaces the imperative Leader role with a declarative
state machine that defines workflow transitions based on conditions.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Type, Union
from datetime import datetime


class WorkflowState(Enum):
    """Standard workflow states."""
    INITIALIZED = "initialized"
    PLANNING = "planning"
    CODING = "coding"
    JUDGING = "judging"
    COMPLETED = "completed"
    FAILED = "failed"
    ABORTED = "aborted"


@dataclass
class IterationResult:
    """Result of an iteration for state machine decision making."""
    iteration: int
    state: str
    judge_passed: bool = False
    judge_score: int = 0
    retry_count: int = 0
    consecutive_failures: int = 0
    error: Optional[str] = None
    metadata: Dict[str, Any] = None

    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}


class Transition(ABC):
    """Abstract base class for state transitions."""

    @abstractmethod
    def get_next_state(self, result: IterationResult) -> Optional[str]:
        """Determine the next state based on iteration result."""
        pass

    @abstractmethod
    def get_handler(self) -> Optional[Type]:
        """Get the handler class for this transition."""
        pass


@dataclass
class StateTransition(Transition):
    """A simple state transition to a fixed next state."""
    to_state: str
    handler: Optional[Type] = None
    on_transition: Optional[Callable[[IterationResult], None]] = None

    def get_next_state(self, result: IterationResult) -> Optional[str]:
        if self.on_transition:
            self.on_transition(result)
        return self.to_state

    def get_handler(self) -> Optional[Type]:
        return self.handler


@dataclass
class ConditionalTransition(Transition):
    """A conditional transition with multiple possible targets."""
    conditions: List[tuple]  # List of (condition_func, target_state, handler)
    default_state: Optional[str] = None
    default_handler: Optional[Type] = None

    def get_next_state(self, result: IterationResult) -> Optional[str]:
        for condition, target_state, _ in self.conditions:
            if condition(result):
                return target_state
        return self.default_state

    def get_handler(self) -> Optional[Type]:
        for condition, _, handler in self.conditions:
            if condition(result := IterationResult(0, "")):  # Dummy check
                return handler
        return self.default_handler

    def get_handler_for_state(self, state: str) -> Optional[Type]:
        """Get handler for a specific state."""
        for condition, target_state, handler in self.conditions:
            if target_state == state:
                return handler
        return self.default_handler


@dataclass
class TerminalState(Transition):
    """A terminal state with no outgoing transitions."""
    handler: Optional[Type] = None

    def get_next_state(self, result: IterationResult) -> Optional[str]:
        return None

    def get_handler(self) -> Optional[Type]:
        return self.handler


class WorkflowStateMachine:
    """Declarative state machine for agent workflow orchestration.

    This replaces the imperative Leader role with a declarative
    definition of the workflow. Transitions are based on conditions
    evaluated against iteration results.

    Usage:
        # Define workflow declaratively
        workflow = WorkflowStateMachine({
            'initialized': StateTransition(to='planning', handler=PlanRole),
            'planning': StateTransition(to='coding', handler=CodingRole),
            'coding': StateTransition(to='judging', handler=JudgeRole),
            'judging': ConditionalTransition([
                (lambda r: r.judge_passed, 'completed', None),
                (lambda r: r.retry_count < 3, 'planning', PlanRole),
                (lambda r: True, 'failed', None),
            ]),
            'completed': TerminalState(),
            'failed': TerminalState(),
        })

        # Run workflow
        current_state = 'initialized'
        while not workflow.is_terminal(current_state):
            handler = workflow.get_handler(current_state)
            result = handler.execute(...)
            current_state = workflow.transition(current_state, result)
    """

    # Default workflow configuration
    DEFAULT_FLOW: Dict[str, Transition] = {
        WorkflowState.INITIALIZED.value: StateTransition(
            to_state=WorkflowState.PLANNING.value,
        ),
        WorkflowState.PLANNING.value: StateTransition(
            to_state=WorkflowState.CODING.value,
        ),
        WorkflowState.CODING.value: StateTransition(
            to_state=WorkflowState.JUDGING.value,
        ),
        WorkflowState.JUDGING.value: ConditionalTransition([
            # If passed, complete
            (lambda r: r.judge_passed, WorkflowState.COMPLETED.value, None),
            # If failed but retries left, replan
            (lambda r: not r.judge_passed and r.retry_count < 3,
             WorkflowState.PLANNING.value, None),
            # Otherwise, fail
            (lambda r: True, WorkflowState.FAILED.value, None),
        ]),
        WorkflowState.COMPLETED.value: TerminalState(),
        WorkflowState.FAILED.value: TerminalState(),
    }

    def __init__(
        self,
        transitions: Optional[Dict[str, Transition]] = None,
        max_iterations: int = 10,
        early_stop_score_threshold: int = 80,
    ):
        self.transitions = transitions or self.DEFAULT_FLOW.copy()
        self.max_iterations = max_iterations
        self.early_stop_score_threshold = early_stop_score_threshold
        self._state_history: List[tuple] = []  # (state, timestamp)
        self._transition_count: Dict[str, int] = {}

    def transition(self, current_state: str, result: IterationResult) -> str:
        """Determine the next state based on current state and result."""
        transition = self.transitions.get(current_state)

        if transition is None:
            raise ValueError(f"No transition defined for state: {current_state}")

        next_state = transition.get_next_state(result)

        if next_state is None:
            # Terminal state
            return current_state

        # Record transition
        self._state_history.append((current_state, datetime.now().timestamp()))
        self._transition_count[f"{current_state}->{next_state}"] = (
            self._transition_count.get(f"{current_state}->{next_state}", 0) + 1
        )

        return next_state

    def get_handler(self, state: str) -> Optional[Type]:
        """Get the handler class for a state."""
        transition = self.transitions.get(state)
        if transition:
            return transition.get_handler()
        return None

    def is_terminal(self, state: str) -> bool:
        """Check if a state is terminal."""
        transition = self.transitions.get(state)
        return isinstance(transition, TerminalState)

    def should_continue(self, state: str, result: IterationResult) -> bool:
        """Determine if the workflow should continue."""
        # Check terminal state
        if self.is_terminal(state):
            return False

        # Check max iterations
        if result.iteration >= self.max_iterations:
            return False

        # Check for early success
        if result.judge_passed and result.judge_score >= self.early_stop_score_threshold:
            return False

        return True

    def get_state_history(self) -> List[tuple]:
        """Get the history of state transitions."""
        return self._state_history.copy()

    def get_loop_count(self, state_a: str, state_b: str) -> int:
        """Count how many times we've transitioned between two states.

        Useful for detecting loops like planning -> coding -> judging -> planning.
        """
        key = f"{state_a}->{state_b}"
        return self._transition_count.get(key, 0)

    def detect_loop(self, loop_states: List[str]) -> int:
        """Detect if we're stuck in a loop.

        Returns the number of complete loop iterations detected.
        """
        if len(self._state_history) < len(loop_states):
            return 0

        # Check if the last N transitions match the loop pattern
        recent_states = [s for s, _ in self._state_history[-len(loop_states):]]

        if recent_states == loop_states:
            # Count how many times this loop has occurred
            loop_key = "->".join(loop_states)
            return self._transition_count.get(loop_key, 0) // len(loop_states)

        return 0

    def add_state(
        self,
        state: str,
        transition: Transition,
    ) -> None:
        """Add a new state to the workflow."""
        self.transitions[state] = transition

    def modify_transition(
        self,
        from_state: str,
        new_transition: Transition,
    ) -> None:
        """Modify an existing transition."""
        self.transitions[from_state] = new_transition

    def to_dict(self) -> Dict[str, Any]:
        """Serialize workflow configuration."""
        return {
            "max_iterations": self.max_iterations,
            "early_stop_score_threshold": self.early_stop_score_threshold,
            "state_history": self._state_history,
            "transition_count": self._transition_count,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "WorkflowStateMachine":
        """Deserialize workflow configuration."""
        machine = cls(
            max_iterations=data.get("max_iterations", 10),
            early_stop_score_threshold=data.get("early_stop_score_threshold", 80),
        )
        machine._state_history = data.get("state_history", [])
        machine._transition_count = data.get("transition_count", {})
        return machine


# Predefined workflow patterns

class WorkflowPatterns:
    """Common workflow patterns for different scenarios."""

    @staticmethod
    def simple_retry(max_retries: int = 3) -> WorkflowStateMachine:
        """Simple workflow with retry logic."""
        return WorkflowStateMachine({
            WorkflowState.INITIALIZED.value: StateTransition(
                to=WorkflowState.PLANNING.value
            ),
            WorkflowState.PLANNING.value: StateTransition(
                to=WorkflowState.CODING.value
            ),
            WorkflowState.CODING.value: StateTransition(
                to=WorkflowState.JUDGING.value
            ),
            WorkflowState.JUDGING.value: ConditionalTransition([
                (lambda r: r.judge_passed, WorkflowState.COMPLETED.value, None),
                (lambda r: r.retry_count < max_retries, WorkflowState.CODING.value, None),
                (lambda r: True, WorkflowState.FAILED.value, None),
            ]),
            WorkflowState.COMPLETED.value: TerminalState(),
            WorkflowState.FAILED.value: TerminalState(),
        })

    @staticmethod
    def replan_on_failure(max_replans: int = 2) -> WorkflowStateMachine:
        """Workflow that replans when coding fails."""
        return WorkflowStateMachine({
            WorkflowState.INITIALIZED.value: StateTransition(
                to=WorkflowState.PLANNING.value
            ),
            WorkflowState.PLANNING.value: StateTransition(
                to=WorkflowState.CODING.value
            ),
            WorkflowState.CODING.value: StateTransition(
                to=WorkflowState.JUDGING.value
            ),
            WorkflowState.JUDGING.value: ConditionalTransition([
                (lambda r: r.judge_passed, WorkflowState.COMPLETED.value, None),
                (lambda r: r.retry_count < max_replans * 2, WorkflowState.PLANNING.value, None),
                (lambda r: True, WorkflowState.FAILED.value, None),
            ]),
            WorkflowState.COMPLETED.value: TerminalState(),
            WorkflowState.FAILED.value: TerminalState(),
        })

    @staticmethod
    def with_validation() -> WorkflowStateMachine:
        """Workflow with explicit validation step."""
        return WorkflowStateMachine({
            WorkflowState.INITIALIZED.value: StateTransition(
                to=WorkflowState.PLANNING.value
            ),
            WorkflowState.PLANNING.value: StateTransition(
                to=WorkflowState.CODING.value
            ),
            WorkflowState.CODING.value: StateTransition(
                to='validating'
            ),
            'validating': StateTransition(
                to=WorkflowState.JUDGING.value
            ),
            WorkflowState.JUDGING.value: ConditionalTransition([
                (lambda r: r.judge_passed, WorkflowState.COMPLETED.value, None),
                (lambda r: r.retry_count < 3, WorkflowState.PLANNING.value, None),
                (lambda r: True, WorkflowState.FAILED.value, None),
            ]),
            WorkflowState.COMPLETED.value: TerminalState(),
            WorkflowState.FAILED.value: TerminalState(),
        })
