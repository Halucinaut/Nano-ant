"""Built-in tools for file and command execution."""

from __future__ import annotations

import os
import subprocess
from typing import Any

from .base import Tool, ToolResult
from .provider import BuiltinToolProvider


class WriteFileTool(Tool):
    name = "write_file"
    description = "Write full content to a file inside the workspace."
    risk_level = "write"
    input_schema = {
        "type": "object",
        "properties": {
            "path": {"type": "string"},
            "content": {"type": "string"},
        },
        "required": ["path", "content"],
    }
    result_schema = {
        "type": "object",
        "properties": {
            "success": {"type": "boolean"},
            "artifacts": {"type": "array", "items": {"type": "string"}},
        },
    }

    def __init__(self, workspace_path: str):
        self.workspace_path = workspace_path

    def execute(self, **kwargs: Any) -> ToolResult:
        path = str(kwargs.get("path", "") or "")
        content = str(kwargs.get("content", "") or "")
        if not path:
            return ToolResult(success=False, message="Missing path for write_file")

        full_path = os.path.join(self.workspace_path, path)
        directory = os.path.dirname(full_path)
        if directory:
            os.makedirs(directory, exist_ok=True)
        with open(full_path, "w", encoding="utf-8") as handle:
            handle.write(content)

        return ToolResult(
            success=True,
            tool_name=self.name,
            message="File written",
            target=path,
            output=content[:4000],
            files_modified=[path],
            artifacts=[path],
        )


class ReadFileTool(Tool):
    name = "read_file"
    description = "Read a file from the workspace."
    read_only = True
    risk_level = "read"
    input_schema = {
        "type": "object",
        "properties": {"path": {"type": "string"}},
        "required": ["path"],
    }

    def __init__(self, workspace_path: str):
        self.workspace_path = workspace_path

    def execute(self, **kwargs: Any) -> ToolResult:
        path = str(kwargs.get("path", "") or "")
        if not path:
            return ToolResult(success=False, message="Missing path for read_file")

        full_path = os.path.join(self.workspace_path, path)
        if not os.path.exists(full_path):
            return ToolResult(success=False, message="File not found", target=path)

        with open(full_path, "r", encoding="utf-8") as handle:
            content = handle.read()

        return ToolResult(
            success=True,
            tool_name=self.name,
            message="File read",
            target=path,
            output=content[:4000],
            artifacts=[path],
            metadata={"content": content[:4000]},
        )


class RunCommandTool(Tool):
    name = "run_command"
    description = "Execute a shell command in the workspace or sandbox."
    risk_level = "high_risk"
    input_schema = {
        "type": "object",
        "properties": {
            "command": {"type": "string"},
            "timeout": {"type": "integer"},
        },
        "required": ["command"],
    }

    def __init__(self, workspace_path: str, sandbox: Any = None):
        self.workspace_path = workspace_path
        self.sandbox = sandbox

    def execute(self, **kwargs: Any) -> ToolResult:
        command = str(kwargs.get("command", "") or "")
        timeout = kwargs.get("timeout")
        timeout_value = int(timeout) if isinstance(timeout, (int, float, str)) and str(timeout).strip() else None
        if not command:
            return ToolResult(success=False, message="Missing command for run_command")

        if self.sandbox is not None:
            result = self.sandbox.run_command(command, timeout=timeout_value)
            return ToolResult(
                success=result.success,
                tool_name=self.name,
                message="Command executed in sandbox" if result.success else "Command failed in sandbox",
                target=command,
                stdout=result.stdout,
                stderr=result.stderr,
                output=result.stdout[:4000],
                error=result.stderr[:4000],
                files_modified=result.files_modified,
                metadata={"return_code": result.return_code},
            )

        proc = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            cwd=self.workspace_path,
            timeout=timeout_value or 60,
        )
        return ToolResult(
            success=proc.returncode == 0,
            tool_name=self.name,
            message="Command executed" if proc.returncode == 0 else "Command failed",
            target=command,
            stdout=proc.stdout,
            stderr=proc.stderr,
            output=proc.stdout[:4000],
            error=proc.stderr[:4000],
            metadata={"return_code": proc.returncode},
        )


class SearchTextTool(Tool):
    name = "search_text"
    description = "Search for a text pattern across workspace files."
    read_only = True
    risk_level = "read"
    input_schema = {
        "type": "object",
        "properties": {
            "pattern": {"type": "string"},
            "path": {"type": "string"},
        },
        "required": ["pattern"],
    }

    def __init__(self, workspace_path: str):
        self.workspace_path = workspace_path

    def execute(self, **kwargs: Any) -> ToolResult:
        pattern = str(kwargs.get("pattern", "") or kwargs.get("query", "") or "")
        relative_path = str(kwargs.get("path", "") or "")
        if not pattern:
            return ToolResult(success=False, tool_name=self.name, message="Missing pattern for search_text")

        search_root = os.path.join(self.workspace_path, relative_path) if relative_path else self.workspace_path
        matches: list[dict[str, Any]] = []

        if not os.path.exists(search_root):
            return ToolResult(success=False, tool_name=self.name, message="Search root not found", target=relative_path)

        if os.path.isfile(search_root):
            candidates = [search_root]
        else:
            candidates = []
            for root, _, filenames in os.walk(search_root):
                for filename in filenames:
                    candidates.append(os.path.join(root, filename))

        for filepath in candidates:
            try:
                with open(filepath, "r", encoding="utf-8") as handle:
                    for line_no, line in enumerate(handle, start=1):
                        if pattern in line:
                            matches.append({
                                "path": os.path.relpath(filepath, self.workspace_path),
                                "line": line_no,
                                "content": line.rstrip()[:500],
                            })
            except (UnicodeDecodeError, OSError):
                continue

        return ToolResult(
            success=True,
            tool_name=self.name,
            message=f"Found {len(matches)} matches",
            target=relative_path or ".",
            output=str(len(matches)),
            artifacts=[item["path"] for item in matches[:20]],
            metadata={"matches": matches[:100]},
        )


class CustomTool(Tool):
    name = "custom_tool"
    description = "Record a custom tool action when no provider is configured."
    risk_level = "external"

    def execute(self, **kwargs: Any) -> ToolResult:
        tool_name = str(kwargs.get("tool", "") or "")
        target = str(kwargs.get("path", "") or kwargs.get("command", "") or tool_name)
        return ToolResult(
            success=True,
            tool_name=self.name,
            message="Recorded custom tool action with no built-in executor",
            target=target,
            metadata=kwargs.get("metadata", {}) if isinstance(kwargs.get("metadata", {}), dict) else {},
        )


def create_builtin_provider(workspace_path: str, sandbox: Any = None) -> BuiltinToolProvider:
    """Create the default built-in provider for Nano Ant."""
    provider = BuiltinToolProvider(name="builtin")
    provider.register_tool(WriteFileTool(workspace_path))
    provider.register_tool(ReadFileTool(workspace_path))
    provider.register_tool(SearchTextTool(workspace_path))
    provider.register_tool(RunCommandTool(workspace_path, sandbox=sandbox))
    provider.register_tool(CustomTool())
    return provider
