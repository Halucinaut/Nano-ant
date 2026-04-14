"""Provider implementations for built-in and external tools."""

from __future__ import annotations

from typing import Any

from .base import Tool, ToolProvider, ToolResult, ToolSpec


class BuiltinToolProvider(ToolProvider):
    """Provider wrapper for in-process tools."""

    def __init__(self, name: str = "builtin") -> None:
        self.name = name
        self._tools: dict[str, Tool] = {}

    def register_tool(self, tool: Tool) -> None:
        self._tools[tool.name] = tool

    def get_tool(self, tool_name: str) -> Tool | None:
        return self._tools.get(tool_name)

    def has_tool(self, tool_name: str) -> bool:
        return tool_name in self._tools

    def list_tools(self) -> list[ToolSpec]:
        return [tool.get_spec(provider_name=self.name) for tool in self._tools.values()]

    def execute(self, tool_name: str, arguments: dict[str, Any]) -> ToolResult:
        tool = self.get_tool(tool_name)
        if tool is None:
            return ToolResult(
                success=False,
                tool_name=tool_name,
                provider_name=self.name,
                message=f"Tool '{tool_name}' not found",
                error=f"Tool '{tool_name}' not found",
            )
        result = tool.execute(**arguments)
        result.tool_name = result.tool_name or tool_name
        result.provider_name = result.provider_name or self.name
        return result


class MCPToolClientProtocol:
    """Protocol-like adapter for external MCP-compatible clients."""

    def list_tools(self) -> list[dict[str, Any]]:  # pragma: no cover - adapter interface
        raise NotImplementedError

    def call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:  # pragma: no cover - adapter interface
        raise NotImplementedError


class MCPToolProvider(ToolProvider):
    """Adapter that exposes an external MCP-compatible client as a provider."""

    def __init__(self, name: str, client: MCPToolClientProtocol) -> None:
        self.name = name
        self.client = client

    def list_tools(self) -> list[ToolSpec]:
        specs: list[ToolSpec] = []
        for item in self.client.list_tools():
            if not isinstance(item, dict):
                continue
            annotations = item.get("annotations", {}) if isinstance(item.get("annotations", {}), dict) else {}
            specs.append(ToolSpec(
                name=str(item.get("name", "")),
                description=str(item.get("description", "") or ""),
                input_schema=item.get("inputSchema", {}) if isinstance(item.get("inputSchema", {}), dict) else {},
                result_schema=item.get("resultSchema", {}) if isinstance(item.get("resultSchema", {}), dict) else {},
                read_only=bool(annotations.get("readOnlyHint", False)),
                risk_level=str(annotations.get("riskLevel", "external") or "external"),
                provider_name=self.name,
            ))
        return specs

    def execute(self, tool_name: str, arguments: dict[str, Any]) -> ToolResult:
        response = self.client.call_tool(tool_name, arguments)
        if not isinstance(response, dict):
            return ToolResult(
                success=False,
                tool_name=tool_name,
                provider_name=self.name,
                message="Invalid MCP tool response",
                error="Invalid MCP tool response",
            )
        return ToolResult(
            success=bool(response.get("success", True)),
            tool_name=tool_name,
            provider_name=self.name,
            message=str(response.get("message", "") or ""),
            target=str(response.get("target", "") or tool_name),
            stdout=str(response.get("stdout", "") or ""),
            stderr=str(response.get("stderr", "") or ""),
            output=str(response.get("output", "") or ""),
            error=str(response.get("error", "") or ""),
            files_modified=list(response.get("files_modified", []) or []),
            artifacts=list(response.get("artifacts", []) or []),
            metadata=response.get("metadata", {}) if isinstance(response.get("metadata", {}), dict) else {},
        )
