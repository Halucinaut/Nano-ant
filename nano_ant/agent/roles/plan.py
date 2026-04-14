"""Plan Role - creates and refines execution plans."""

from __future__ import annotations

from typing import Any

from ..action_models import normalize_actions
from .base import BaseRole, RoleOutput


class PlanRole(BaseRole):
    """Plan role responsible for creating and optimizing execution plans."""

    def __init__(self, llm_client, system_prompt: str, max_retries: int = 2):
        super().__init__("Plan", llm_client, system_prompt, max_retries)

    def _process_response(self, response: str, **kwargs: Any) -> RoleOutput:
        """Process plan response and extract structured plan."""
        if not response or not response.strip():
            return RoleOutput(
                success=True,
                content="",
                metadata={
                    "plan": {},
                    "planning_mode": "single_step",
                    "actions": [],
                    "iteration_goal": "",
                    "files_to_create": [],
                    "prompt_for_action": "Execute the next most useful actions needed to achieve the goal.",
                    "expected_outcome": "Make measurable progress toward the goal.",
                    "success_criteria": [],
                },
            )

        plan = self._extract_json_object(response)
        actions = normalize_actions(plan.get("actions", []))

        files_to_create = list(plan.get("files_to_create", []))
        if not files_to_create:
            for action in actions:
                if action.action_type in {"write_file", "edit_file"} and action.path:
                    files_to_create.append(action.path)
        files_to_create = list(dict.fromkeys(files_to_create))

        prompt_for_action = plan.get("prompt_for_action") or plan.get("prompt_for_coding") or (
            "Execute the highest-value actions for this iteration and return structured action results."
        )

        return RoleOutput(
            success=True,
            content=response,
            metadata={
                "plan": plan,
                "planning_mode": plan.get("planning_mode", "single_step"),
                "total_steps": plan.get("total_steps", 1),
                "current_step": plan.get("current_step", 1),
                "completed_steps": plan.get("completed_steps", []),
                "iteration_goal": plan.get("iteration_goal", plan.get("expected_outcome", "")),
                "actions": [action.to_dict() for action in actions],
                "files_to_create": files_to_create,
                "files_already_exist": plan.get("files_already_exist", []),
                "task_type": plan.get("task_type", ""),
                "judge_skill": plan.get("judge_skill", ""),
                "prompt_for_action": prompt_for_action,
                "expected_outcome": plan.get("expected_outcome", ""),
                "success_criteria": plan.get("success_criteria", []),
                "next_step_preview": plan.get("next_step_preview", ""),
            },
        )

    def create_plan(
        self,
        user_goal: str,
        workspace_info: str,
        feedback: str | None = None,
        plan_state: dict[str, Any] | None = None,
    ) -> RoleOutput:
        """Create or refine an execution plan."""
        plan_state_info = ""
        if plan_state and plan_state.get("planning_mode") == "multi_step":
            plan_state_info = f"""
[Current Plan State]:
- Planning Mode: multi_step
- Total Steps: {plan_state.get('total_steps', 1)}
- Completed Steps: {plan_state.get('completed_steps', [])}
- Current Step: {plan_state.get('current_step', 1)}

Continue from where you left off. Plan the NEXT step that hasn't been completed yet.
"""

        prompt = f"""[User Goal]:
{user_goal}

[Workspace Information]:
{workspace_info}

[Previous Feedback]:
{feedback if feedback else "None (first iteration)"}
{plan_state_info}

Analyze the task complexity:
- If the task requires <5 files: Use single_step mode
- If the task requires >=5 files: Use multi_step mode

Output in JSON format:
{{
    "planning_mode": "single_step" | "multi_step",
    "total_steps": 1-10,
    "current_step": 1-10,
    "completed_steps": [...],
    "iteration_goal": "What this iteration should focus on",
    "actions": [
        {{
            "action_type": "write_file" | "edit_file" | "run_command" | "read_file" | "custom_tool",
            "path": "optional file path",
            "command": "optional shell command",
            "purpose": "why this action matters",
            "expected_output": "what success should look like"
        }}
    ],
    "files_to_create": ["file1.py", ...],
    "files_already_exist": [...],
    "task_type": "optional task category like coding / qa / research / workflow",
    "judge_skill": "optional judge skill name to force for this task",
    "prompt_for_action": "Detailed prompt for current step actions",
    "expected_outcome": "What this step should achieve",
    "success_criteria": ["observable signal 1", "observable signal 2"],
    "next_step_preview": "What next step will focus on (if multi_step)"
}}
"""
        return self.execute(prompt)
