"""Registry for built-in and external tools."""

from __future__ import annotations

from typing import Any

from .base import Tool, ToolProvider, ToolResult, ToolSpec
from .provider import BuiltinToolProvider


class ToolRegistry:
    """Small in-memory registry of runtime tools and providers."""

    def __init__(self) -> None:
        self._providers: dict[str, ToolProvider] = {}
        self._tool_to_provider: dict[str, str] = {}
        self.register_provider(BuiltinToolProvider())

    def register_provider(self, provider: ToolProvider) -> None:
        self._providers[provider.name] = provider
        for spec in provider.list_tools():
            self._tool_to_provider[spec.name] = provider.name

    def register(self, tool: Tool, provider_name: str = "builtin") -> None:
        provider = self._providers.get(provider_name)
        if provider is None:
            provider = BuiltinToolProvider(provider_name)
            self.register_provider(provider)
        if not isinstance(provider, BuiltinToolProvider):
            raise ValueError(f"Provider '{provider_name}' does not accept in-process tools")
        provider.register_tool(tool)
        self._tool_to_provider[tool.name] = provider.name

    def has(self, name: str) -> bool:
        return name in self._tool_to_provider

    def get_provider(self, provider_name: str) -> ToolProvider | None:
        return self._providers.get(provider_name)

    def get_provider_for_tool(self, tool_name: str) -> ToolProvider | None:
        provider_name = self._tool_to_provider.get(tool_name)
        if provider_name is None:
            return None
        return self.get_provider(provider_name)

    def get(self, name: str) -> Tool | None:
        provider = self.get_provider_for_tool(name)
        if isinstance(provider, BuiltinToolProvider):
            return provider.get_tool(name)
        return None

    def resolve(self, tool_name: str, provider_name: str | None = None) -> tuple[ToolProvider | None, ToolSpec | None]:
        provider = self.get_provider(provider_name) if provider_name else self.get_provider_for_tool(tool_name)
        if provider is None:
            return None, None
        for spec in provider.list_tools():
            if spec.name == tool_name:
                return provider, spec
        return provider, None

    def execute(self, tool_name: str, arguments: dict[str, Any], provider_name: str | None = None) -> ToolResult:
        provider, _ = self.resolve(tool_name, provider_name=provider_name)
        if provider is None:
            return ToolResult(
                success=False,
                tool_name=tool_name,
                provider_name=provider_name or "",
                message=f"Tool '{tool_name}' is not registered",
                error=f"Tool '{tool_name}' is not registered",
            )
        result = provider.execute(tool_name, arguments)
        result.tool_name = result.tool_name or tool_name
        result.provider_name = result.provider_name or provider.name
        return result

    def list_tools(self) -> list[str]:
        return sorted(self._tool_to_provider.keys())

    def list_tool_specs(self) -> list[ToolSpec]:
        specs: list[ToolSpec] = []
        for provider in self._providers.values():
            specs.extend(provider.list_tools())
        return sorted(specs, key=lambda item: (item.provider_name, item.name))

    def export_mcp_manifest(self) -> list[dict[str, Any]]:
        return [spec.to_mcp_tool() for spec in self.list_tool_specs()]
