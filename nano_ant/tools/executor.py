"""Action execution against the tool layer."""

from __future__ import annotations

from typing import Any
import os

from ..agent.action_models import ActionObservation, normalize_actions
from .base import ToolResult
from .builtin import create_builtin_provider
from .registry import ToolRegistry


class ActionToolExecutor:
    """Execute action plans using registered tools."""

    def __init__(
        self,
        workspace_path: str,
        sandbox: Any = None,
        registry: ToolRegistry | None = None,
        external_providers: list[Any] | None = None,
    ):
        self.workspace_path = workspace_path
        self.sandbox = sandbox
        self.registry = registry or ToolRegistry()

        builtin_provider = create_builtin_provider(workspace_path, sandbox=sandbox)
        self.registry.register_provider(builtin_provider)
        for provider in external_providers or []:
            self.registry.register_provider(provider)

    def _result_to_observation(self, action_type: str, result: ToolResult) -> ActionObservation:
        return ActionObservation(
            action_type=action_type,
            success=result.success,
            target=result.target,
            message=result.message,
            stdout=result.stdout,
            stderr=result.stderr,
            files_modified=result.files_modified,
            artifacts=result.artifacts,
            metadata={
                **result.metadata,
                "tool_name": result.tool_name,
                "provider_name": result.provider_name,
                "output": result.output,
                "error": result.error,
            },
        )

    def _resolve_tool_call(self, action: Any) -> tuple[str, str | None, dict[str, Any]]:
        provider_name = None
        if isinstance(action.metadata, dict):
            provider_name = str(action.metadata.get("provider", "") or "") or None

        tool_name = action.tool or action.action_type or "custom_tool"
        arguments = dict(action.metadata) if isinstance(action.metadata, dict) else {}

        if action.action_type in {"write_file", "edit_file"}:
            tool_name = "write_file"
            arguments.update({"path": action.path, "content": action.content})
        elif action.action_type == "read_file":
            tool_name = "read_file"
            arguments.update({"path": action.path})
        elif action.action_type == "run_command":
            tool_name = "run_command"
            arguments.update({"command": action.command})
        elif action.action_type == "search_text":
            tool_name = "search_text"
            arguments.setdefault("path", action.path)
            arguments.setdefault("pattern", action.content or action.expected_output or action.purpose)
        else:
            arguments.setdefault("tool", action.tool)
            arguments.setdefault("path", action.path)
            arguments.setdefault("command", action.command)
            arguments.setdefault("content", action.content)

        if "::" in tool_name and not provider_name:
            provider_name, tool_name = tool_name.split("::", 1)

        return tool_name, provider_name, arguments

    def _candidate_block_keys(self, path: str) -> list[str]:
        if not path:
            return []
        candidates = [path]
        if os.path.isabs(path):
            candidates.append(os.path.relpath(path, self.workspace_path))
        else:
            candidates.append(os.path.abspath(os.path.join(self.workspace_path, path)))
        return list(dict.fromkeys(candidates))

    def execute(self, action_dicts: list[dict[str, Any]], code_blocks: list[dict[str, Any]] | None = None) -> tuple[list[dict[str, Any]], list[str]]:
        """Execute action dictionaries and return observations plus modified files."""
        actions = normalize_actions(action_dicts)
        blocks = code_blocks or []
        block_map: dict[str, str] = {}
        for block in blocks:
            filename = block.get("filename")
            if not filename:
                continue
            code = block.get("code", "")
            for key in self._candidate_block_keys(str(filename)):
                block_map[key] = code

        observations: list[dict[str, Any]] = []
        files_modified: list[str] = []
        consumed_block_paths: set[str] = set()

        for action in actions:
            if action.action_type in {"write_file", "edit_file"}:
                content = action.content
                matched_key = ""
                if not content:
                    for key in self._candidate_block_keys(action.path):
                        if key in block_map:
                            content = block_map[key]
                            matched_key = key
                            break
                if action.path and content:
                    action.content = content
                    if matched_key:
                        consumed_block_paths.update(self._candidate_block_keys(action.path))
                else:
                    result = ToolResult(False, tool_name="write_file", message="Missing file path or content for file action", target=action.path)
                    observations.append(self._result_to_observation(action.action_type, result).to_dict())
                    continue

            tool_name, provider_name, arguments = self._resolve_tool_call(action)
            result = self.registry.execute(tool_name, arguments=arguments, provider_name=provider_name)

            obs = self._result_to_observation(action.action_type, result)
            observations.append(obs.to_dict())
            files_modified.extend(result.files_modified)

        for path, content in block_map.items():
            if path in consumed_block_paths:
                continue
            result = self.registry.execute("write_file", arguments={"path": path, "content": content})
            observations.append(self._result_to_observation("write_file", result).to_dict())
            files_modified.extend(result.files_modified)

        return observations, list(dict.fromkeys(files_modified))

    def export_tool_manifest(self) -> list[dict[str, Any]]:
        """Export the current tool surface in MCP-style format."""
        return self.registry.export_mcp_manifest()
