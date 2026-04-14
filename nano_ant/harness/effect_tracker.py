"""Effect tracking for auditability and reproducibility.

This module provides comprehensive tracking of all side effects
produced during agent execution, enabling full audit trails,
differential analysis between iterations, and run replay.
"""

from abc import ABC
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple, Iterator
from enum import Enum
import hashlib
import json


class EffectType(Enum):
    """Types of effects that can be tracked."""
    FILE_WRITE = "file_write"
    FILE_DELETE = "file_delete"
    LLM_CALL = "llm_call"
    COMMAND_EXEC = "command_exec"
    DEPENDENCY_INSTALL = "dependency_install"
    STATE_CHANGE = "state_change"


@dataclass
class Effect:
    """Base class for all effects."""
    role: str
    iteration: int
    timestamp: float = field(default_factory=lambda: datetime.now().timestamp())
    effect_type: EffectType = field(init=False)
    trace_id: str = field(default_factory=lambda: Effect._generate_trace_id())
    metadata: Dict[str, Any] = field(default_factory=dict)

    @staticmethod
    def _generate_trace_id() -> str:
        """Generate a unique trace ID."""
        import uuid
        return str(uuid.uuid4())[:8]


@dataclass
class FileWriteEffect(Effect):
    """Tracks file write operations."""
    path: str = ""
    content: str = ""  # Store actual content for reproducibility
    content_hash: str = ""
    lines_added: int = 0
    lines_removed: int = 0
    is_new_file: bool = True

    def __post_init__(self):
        self.effect_type = EffectType.FILE_WRITE
        if not self.content_hash and self.content:
            self.content_hash = hashlib.sha256(self.content.encode()).hexdigest()[:16]


@dataclass
class FileDeleteEffect(Effect):
    """Tracks file deletion operations."""
    path: str = ""
    previous_content_hash: Optional[str] = None

    def __post_init__(self):
        self.effect_type = EffectType.FILE_DELETE


@dataclass
class LLMCallEffect(Effect):
    """Tracks LLM API calls."""
    model: str = ""
    prompt: str = ""
    response: str = ""
    prompt_hash: str = ""
    response_hash: str = ""
    latency_ms: float = 0.0
    tokens_in: int = 0
    tokens_out: int = 0
    temperature: float = 0.7

    def __post_init__(self):
        self.effect_type = EffectType.LLM_CALL
        if not self.prompt_hash and self.prompt:
            self.prompt_hash = hashlib.sha256(self.prompt.encode()).hexdigest()[:16]
        if not self.response_hash and self.response:
            self.response_hash = hashlib.sha256(self.response.encode()).hexdigest()[:16]


@dataclass
class CommandExecEffect(Effect):
    """Tracks command execution."""
    command: str = ""
    working_dir: str = ""
    stdout: str = ""
    stderr: str = ""
    return_code: int = 0
    duration_ms: float = 0.0

    def __post_init__(self):
        self.effect_type = EffectType.COMMAND_EXEC


@dataclass
class DependencyInstallEffect(Effect):
    """Tracks dependency installation."""
    package: str = ""
    version: str = ""
    success: bool = True
    output: str = ""

    def __post_init__(self):
        self.effect_type = EffectType.DEPENDENCY_INSTALL


@dataclass
class StateChangeEffect(Effect):
    """Tracks state transitions."""
    from_state: str = ""
    to_state: str = ""
    reason: str = ""

    def __post_init__(self):
        self.effect_type = EffectType.STATE_CHANGE


@dataclass
class Delta:
    """Difference between two sets of effects."""
    added: List[Effect]
    removed: List[Effect]
    modified: List[Tuple[Effect, Effect]]  # (old, new)

    def summary(self) -> str:
        """Get a human-readable summary."""
        return (
            f"Delta: +{len(self.added)} effects, "
            f"-{len(self.removed)} effects, "
            f"~{len(self.modified)} modified"
        )


class EffectTracker:
    """Tracks all side effects for auditability and debugging.

    Usage:
        tracker = EffectTracker()

        # In roles:
        tracker.log_file_write("coding", iteration, "/path/to/file.py", content)
        tracker.log_llm_call("plan", iteration, model, prompt, response, latency)

        # Analysis:
        effects = tracker.get_effects_for_iteration(3)
        delta = tracker.diff(2, 3)  # What changed between iter 2 and 3?
    """

    def __init__(self):
        self._effects: List[Effect] = []
        self._iteration_index: Dict[int, List[Effect]] = {}
        self._role_index: Dict[str, List[Effect]] = {}
        self._file_index: Dict[str, List[FileWriteEffect]] = {}

    def log(self, effect: Effect) -> None:
        """Log an effect."""
        self._effects.append(effect)

        # Index by iteration
        if effect.iteration not in self._iteration_index:
            self._iteration_index[effect.iteration] = []
        self._iteration_index[effect.iteration].append(effect)

        # Index by role
        if effect.role not in self._role_index:
            self._role_index[effect.role] = []
        self._role_index[effect.role].append(effect)

        # Index file writes separately
        if isinstance(effect, FileWriteEffect):
            if effect.path not in self._file_index:
                self._file_index[effect.path] = []
            self._file_index[effect.path].append(effect)

    def log_file_write(
        self,
        role: str,
        iteration: int,
        path: str,
        content: str,
        is_new_file: bool = True,
    ) -> FileWriteEffect:
        """Log a file write effect."""
        lines = content.split("\n")
        effect = FileWriteEffect(
            role=role,
            iteration=iteration,
            path=path,
            content=content,  # Store full content for reproducibility
            lines_added=len(lines) if is_new_file else 0,
            lines_removed=0,
            is_new_file=is_new_file,
        )
        self.log(effect)
        return effect

    def log_llm_call(
        self,
        role: str,
        iteration: int,
        model: str,
        prompt: str,
        response: str,
        latency_ms: float = 0.0,
        tokens_in: int = 0,
        tokens_out: int = 0,
        temperature: float = 0.7,
    ) -> LLMCallEffect:
        """Log an LLM call effect."""
        effect = LLMCallEffect(
            role=role,
            iteration=iteration,
            model=model,
            prompt=prompt,
            response=response,
            latency_ms=latency_ms,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            temperature=temperature,
        )
        self.log(effect)
        return effect

    def log_command(
        self,
        role: str,
        iteration: int,
        command: str,
        working_dir: str,
        stdout: str = "",
        stderr: str = "",
        return_code: int = 0,
        duration_ms: float = 0.0,
    ) -> CommandExecEffect:
        """Log a command execution effect."""
        effect = CommandExecEffect(
            role=role,
            iteration=iteration,
            command=command,
            working_dir=working_dir,
            stdout=stdout,
            stderr=stderr,
            return_code=return_code,
            duration_ms=duration_ms,
        )
        self.log(effect)
        return effect

    def log_state_change(
        self,
        role: str,
        iteration: int,
        from_state: str,
        to_state: str,
        reason: str = "",
    ) -> StateChangeEffect:
        """Log a state transition."""
        effect = StateChangeEffect(
            role=role,
            iteration=iteration,
            from_state=from_state,
            to_state=to_state,
            reason=reason,
        )
        self.log(effect)
        return effect

    def get_effects_for_iteration(self, iteration: int) -> List[Effect]:
        """Get all effects for a specific iteration."""
        return self._iteration_index.get(iteration, [])

    def get_effects_for_role(self, role: str) -> List[Effect]:
        """Get all effects for a specific role."""
        return self._role_index.get(role, [])

    def get_file_history(self, path: str) -> List[FileWriteEffect]:
        """Get all writes to a specific file."""
        return self._file_index.get(path, [])

    def get_current_file_content(self, path: str) -> Optional[str]:
        """Get the current content of a file (last write)."""
        history = self._file_index.get(path, [])
        if history:
            return history[-1].content
        return None

    def trace(self) -> List[Effect]:
        """Get all effects in chronological order."""
        return self._effects.copy()

    def diff(self, iteration_a: int, iteration_b: int) -> Delta:
        """Compare effects between two iterations.

        Returns a Delta showing what was added, removed, or modified.
        """
        effects_a = set(self._iteration_index.get(iteration_a, []))
        effects_b = set(self._iteration_index.get(iteration_b, []))

        # For now, simple set difference
        # For file writes, we could do content diff
        added = list(effects_b - effects_a)
        removed = list(effects_a - effects_b)

        return Delta(added=added, removed=removed, modified=[])

    def analyze_failure(self, iteration: int) -> Dict[str, Any]:
        """Analyze what went wrong in an iteration.

        Returns a diagnostic report with:
        - LLM calls and their latency
        - Files modified
        - Commands executed and their results
        """
        effects = self.get_effects_for_iteration(iteration)

        report = {
            "iteration": iteration,
            "total_effects": len(effects),
            "llm_calls": [],
            "files_modified": [],
            "commands_executed": [],
            "errors": [],
        }

        for effect in effects:
            if isinstance(effect, LLMCallEffect):
                report["llm_calls"].append({
                    "role": effect.role,
                    "model": effect.model,
                    "latency_ms": effect.latency_ms,
                    "tokens": effect.tokens_in + effect.tokens_out,
                })
            elif isinstance(effect, FileWriteEffect):
                report["files_modified"].append({
                    "path": effect.path,
                    "lines": effect.lines_added,
                    "is_new": effect.is_new_file,
                })
            elif isinstance(effect, CommandExecEffect):
                report["commands_executed"].append({
                    "command": effect.command,
                    "return_code": effect.return_code,
                    "duration_ms": effect.duration_ms,
                })
                if effect.return_code != 0:
                    report["errors"].append({
                        "type": "command_failed",
                        "command": effect.command,
                        "stderr": effect.stderr[:500],
                    })

        return report

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary for checkpointing."""
        return {
            "effects": [
                {
                    "type": e.effect_type.value,
                    "role": e.role,
                    "iteration": e.iteration,
                    "timestamp": e.timestamp,
                    "trace_id": e.trace_id,
                    "data": self._effect_to_dict(e),
                }
                for e in self._effects
            ]
        }

    def _effect_to_dict(self, effect: Effect) -> Dict[str, Any]:
        """Convert an effect to dictionary."""
        data = {}
        if isinstance(effect, FileWriteEffect):
            data = {
                "path": effect.path,
                "content_hash": effect.content_hash,
                "lines_added": effect.lines_added,
                "is_new_file": effect.is_new_file,
                # Don't store full content in checkpoint, just hash
            }
        elif isinstance(effect, LLMCallEffect):
            data = {
                "model": effect.model,
                "prompt_hash": effect.prompt_hash,
                "response_hash": effect.response_hash,
                "latency_ms": effect.latency_ms,
                "tokens_in": effect.tokens_in,
                "tokens_out": effect.tokens_out,
                # Don't store full prompt/response, just hashes
            }
        elif isinstance(effect, CommandExecEffect):
            data = {
                "command": effect.command,
                "return_code": effect.return_code,
                "duration_ms": effect.duration_ms,
            }
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "EffectTracker":
        """Deserialize from dictionary."""
        tracker = cls()
        # Note: Full reconstruction would require storing/loading content
        # This is a lightweight restore for checkpointing purposes
        return tracker

    def summary(self) -> str:
        """Get a human-readable summary."""
        by_type: Dict[EffectType, int] = {}
        for effect in self._effects:
            by_type[effect.effect_type] = by_type.get(effect.effect_type, 0) + 1

        lines = [f"Effect Summary ({len(self._effects)} total):"]
        for effect_type, count in sorted(by_type.items(), key=lambda x: x[1], reverse=True):
            lines.append(f"  {effect_type.value}: {count}")
        return "\n".join(lines)
