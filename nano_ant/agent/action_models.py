"""Shared action and observation models for Nano Ant."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ActionStep:
    """A single action the runtime can execute or reason about."""

    action_type: str
    path: str = ""
    command: str = ""
    tool: str = ""
    content: str = ""
    purpose: str = ""
    expected_output: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "action_type": self.action_type,
            "path": self.path,
            "command": self.command,
            "tool": self.tool,
            "content": self.content,
            "purpose": self.purpose,
            "expected_output": self.expected_output,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ActionStep":
        return cls(
            action_type=str(data.get("action_type", data.get("type", "custom_tool"))),
            path=str(data.get("path", data.get("target", "")) or ""),
            command=str(data.get("command", "") or ""),
            tool=str(data.get("tool", "") or ""),
            content=str(data.get("content", "") or ""),
            purpose=str(data.get("purpose", data.get("description", "")) or ""),
            expected_output=str(data.get("expected_output", "") or ""),
            metadata=data.get("metadata", {}) if isinstance(data.get("metadata", {}), dict) else {},
        )


@dataclass
class ActionObservation:
    """Structured result of an executed action."""

    action_type: str
    success: bool
    target: str = ""
    message: str = ""
    stdout: str = ""
    stderr: str = ""
    files_modified: list[str] = field(default_factory=list)
    artifacts: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "action_type": self.action_type,
            "success": self.success,
            "target": self.target,
            "message": self.message,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "files_modified": self.files_modified,
            "artifacts": self.artifacts,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ActionObservation":
        return cls(
            action_type=str(data.get("action_type", "unknown")),
            success=bool(data.get("success", False)),
            target=str(data.get("target", "") or ""),
            message=str(data.get("message", "") or ""),
            stdout=str(data.get("stdout", "") or ""),
            stderr=str(data.get("stderr", "") or ""),
            files_modified=list(data.get("files_modified", []) or []),
            artifacts=list(data.get("artifacts", []) or []),
            metadata=data.get("metadata", {}) if isinstance(data.get("metadata", {}), dict) else {},
        )


def normalize_actions(raw_actions: list[dict[str, Any]] | None) -> list[ActionStep]:
    """Convert raw dictionaries to ActionStep objects."""
    if not raw_actions:
        return []
    return [ActionStep.from_dict(item) for item in raw_actions if isinstance(item, dict)]
