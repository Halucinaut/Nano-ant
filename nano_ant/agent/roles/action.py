"""Action Role - handles general task execution planning outputs."""

from __future__ import annotations

from typing import Any

from ..action_models import ActionStep, normalize_actions
from .base import BaseRole, RoleOutput


class ActionRole(BaseRole):
    """Action role responsible for producing executable task actions."""

    def __init__(
        self,
        llm_client,
        system_prompt: str,
        workspace_path: str,
        max_retries: int = 2,
        action_backend: str = "llm",
        claude_code_path: str = "claude",
    ):
        super().__init__("Action", llm_client, system_prompt, max_retries)
        self.workspace_path = workspace_path
        self.action_backend = action_backend
        self.claude_code_path = claude_code_path

    def _process_response(self, response: str, **kwargs: Any) -> RoleOutput:
        """Process action response and extract structured actions."""
        payload = self._extract_json_object(response)
        code_blocks = [
            block for block in self._extract_code_blocks(response)
            if block.get("filename") or block.get("language") != "json"
        ]

        raw_actions = payload.get("actions", [])
        actions = normalize_actions(raw_actions)

        if not actions:
            actions = self._derive_actions_from_response(code_blocks, response)

        test_commands = payload.get("test_commands", [])
        if not test_commands:
            test_commands = self._extract_shell_commands(response, prefixes=("pytest", "python -m", "npm test", "go test", "cargo test"))

        dependency_commands = self._extract_shell_commands(response, prefixes=("pip install", "uv pip install", "npm install"))

        files_modified = []
        for action in actions:
            if action.path:
                files_modified.append(action.path)
        for block in code_blocks:
            if block.get("filename"):
                files_modified.append(block["filename"])

        return RoleOutput(
            success=True,
            content=response,
            metadata={
                "summary": payload.get("summary", ""),
                "actions": [action.to_dict() for action in actions],
                "code_blocks": code_blocks,
                "files_modified": list(dict.fromkeys(files_modified)),
                "test_commands": test_commands,
                "dependency_commands": dependency_commands,
                "expected_outcome": payload.get("expected_outcome", ""),
            },
        )

    def _derive_actions_from_response(self, code_blocks: list[dict[str, str]], response: str) -> list[ActionStep]:
        """Fallback action derivation for non-JSON outputs."""
        actions: list[ActionStep] = []
        for block in code_blocks:
            filename = block.get("filename")
            if filename:
                actions.append(ActionStep(
                    action_type="write_file",
                    path=filename,
                    content=block.get("code", ""),
                    purpose="Write generated file content",
                ))

        for command in self._extract_shell_commands(response, prefixes=("python ", "pytest", "npm ", "go ", "cargo ", "bash ")):
            actions.append(ActionStep(
                action_type="run_command",
                command=command,
                purpose="Run suggested verification or task command",
            ))

        return actions

    def _extract_code_blocks(self, response: str) -> list[dict[str, str]]:
        """Extract code blocks from the response."""
        blocks = []
        lines = response.split("\n")
        i = 0
        pending_filename = None

        while i < len(lines):
            line = lines[i]
            stripped = line.strip()

            if stripped.startswith("# filename:") or stripped.startswith("# file:"):
                pending_filename = stripped.split(":", 1)[1].strip()
                i += 1
                continue

            if stripped.startswith("```"):
                lang = stripped[3:].strip()
                code_lines = []
                i += 1
                filename = pending_filename
                pending_filename = None

                while i < len(lines) and not lines[i].strip().startswith("```"):
                    inner = lines[i].strip()
                    if inner.startswith("# filename:") or inner.startswith("# file:"):
                        filename = inner.split(":", 1)[1].strip()
                    code_lines.append(lines[i])
                    i += 1

                blocks.append({
                    "language": lang,
                    "filename": self._clean_filename(filename) if filename else None,
                    "code": self._remove_filename_comments("\n".join(code_lines)),
                })
            i += 1

        return blocks

    def _clean_filename(self, filename: str) -> str:
        filename = filename.strip("./")
        for prefix in ["workspace/", "workspace\\"]:
            if filename.startswith(prefix):
                return filename[len(prefix):]
        return filename

    def _remove_filename_comments(self, code: str) -> str:
        lines = code.split("\n")
        filtered = [line for line in lines if not line.strip().startswith("# filename:") and not line.strip().startswith("# file:")]
        return "\n".join(filtered)

    def _extract_shell_commands(self, response: str, prefixes: tuple[str, ...]) -> list[str]:
        commands = []
        for line in response.split("\n"):
            stripped = line.strip()
            if any(stripped.startswith(prefix) for prefix in prefixes):
                commands.append(stripped)
        return list(dict.fromkeys(commands))

    def execute_plan(
        self,
        task_prompt: str,
        relevant_files: dict[str, str] | None = None,
        planned_actions: list[dict[str, Any]] | None = None,
    ) -> RoleOutput:
        """Generate executable actions for the current iteration."""
        context_parts = [f"[Workspace]: {self.workspace_path}"]

        if planned_actions:
            context_parts.append("\n[Planned Actions]:")
            for action in planned_actions:
                context_parts.append(str(action))

        if relevant_files:
            context_parts.append("\n[Relevant Files]:")
            for filename, content in relevant_files.items():
                context_parts.append(f"\n--- {filename} ---\n{content}\n")

        prompt = f"""{task_prompt}

Return a JSON object in the response with this shape:
{{
  "summary": "what you are doing this iteration",
  "actions": [
    {{
      "action_type": "write_file" | "edit_file" | "run_command" | "read_file" | "custom_tool",
      "path": "optional/file/path",
      "command": "optional shell command",
      "purpose": "why this action matters",
      "expected_output": "what success should look like"
    }}
  ],
  "expected_outcome": "what this iteration should achieve",
  "test_commands": ["optional verification commands"]
}}

If you need to write files, include full file contents in fenced code blocks and annotate them with:
# filename: path/to/file.py
"""
        return self.execute(prompt, context="\n".join(context_parts))
