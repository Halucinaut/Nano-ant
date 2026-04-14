"""Base tool abstractions."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ToolResult:
    """Normalized tool execution result."""

    success: bool
    tool_name: str = ""
    provider_name: str = "builtin"
    message: str = ""
    target: str = ""
    stdout: str = ""
    stderr: str = ""
    output: str = ""
    error: str = ""
    files_modified: list[str] = field(default_factory=list)
    artifacts: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ToolSpec:
    """Portable tool description compatible with MCP-style registries."""

    name: str
    description: str = ""
    input_schema: dict[str, Any] = field(default_factory=dict)
    result_schema: dict[str, Any] = field(default_factory=dict)
    read_only: bool = False
    risk_level: str = "write"
    provider_name: str = "builtin"

    def to_mcp_tool(self) -> dict[str, Any]:
        """Export as an MCP-style tool manifest."""
        return {
            "name": self.name,
            "description": self.description,
            "inputSchema": self.input_schema,
            "annotations": {
                "readOnlyHint": self.read_only,
                "riskLevel": self.risk_level,
                "provider": self.provider_name,
            },
            "resultSchema": self.result_schema,
        }


class Tool(ABC):
    """Abstract executable tool."""

    name: str = ""
    description: str = ""
    read_only: bool = False
    risk_level: str = "write"
    input_schema: dict[str, Any] = {}
    result_schema: dict[str, Any] = {}

    def get_spec(self, provider_name: str = "builtin") -> ToolSpec:
        """Build a portable description for this tool."""
        return ToolSpec(
            name=self.name,
            description=self.description,
            input_schema=dict(self.input_schema),
            result_schema=dict(self.result_schema),
            read_only=self.read_only,
            risk_level=self.risk_level,
            provider_name=provider_name,
        )

    @abstractmethod
    def execute(self, **kwargs: Any) -> ToolResult:
        """Execute the tool."""
        raise NotImplementedError


class ToolProvider(ABC):
    """Abstract provider capable of serving one or more tools."""

    name: str = ""

    @abstractmethod
    def list_tools(self) -> list[ToolSpec]:
        """Return tool specifications exposed by this provider."""
        raise NotImplementedError

    @abstractmethod
    def execute(self, tool_name: str, arguments: dict[str, Any]) -> ToolResult:
        """Execute a tool call through this provider."""
        raise NotImplementedError
