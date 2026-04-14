"""Leader Role - orchestrates the entire agent workflow."""

from __future__ import annotations

from typing import Any
import json

from .base import BaseRole, RoleOutput


class LeaderRole(BaseRole):
    """Leader role responsible for overall orchestration and decision making."""

    def __init__(self, llm_client, system_prompt: str, max_retries: int = 2):
        super().__init__("Leader", llm_client, system_prompt, max_retries)

    def _process_response(self, response: str, **kwargs: Any) -> RoleOutput:
        """Process leader response and extract decisions."""
        try:
            if not response or not response.strip():
                return RoleOutput(
                    success=True,
                    content="",
                    metadata={
                        "decision": {
                            "next_action": "continue",
                            "target_role": "plan",
                            "instructions": "Continue with the next iteration. Review previous results and create a refined plan.",
                            "strategy": "continue_current_trajectory",
                            "instructions_for_plan": "Continue with the next iteration. Review previous results and create a refined plan.",
                            "meta_state": {},
                        },
                        "next_action": "continue",
                        "target_role": "plan",
                        "instructions": "Continue with the next iteration. Review previous results and create a refined plan.",
                        "strategy": "continue_current_trajectory",
                        "instructions_for_plan": "Continue with the next iteration. Review previous results and create a refined plan.",
                        "meta_state": {},
                    },
                )

            if "```json" in response:
                json_start = response.find("```json") + 7
                json_end = response.find("```", json_start)
                json_str = response[json_start:json_end].strip()
            elif "{" in response and "}" in response:
                json_start = response.find("{")
                json_end = response.rfind("}") + 1
                json_str = response[json_start:json_end]
            else:
                json_str = "{}"

            decision = json.loads(json_str)

            if not decision.get("next_action"):
                decision["next_action"] = "continue"
            if not decision.get("target_role"):
                decision["target_role"] = "plan"
            if not decision.get("instructions"):
                decision["instructions"] = "Continue with the next iteration."
            if not decision.get("strategy"):
                decision["strategy"] = "continue_current_trajectory"
            if not decision.get("instructions_for_plan"):
                decision["instructions_for_plan"] = decision["instructions"]
            if not isinstance(decision.get("meta_state"), dict):
                decision["meta_state"] = {}

            return RoleOutput(
                success=True,
                content=response,
                metadata={
                    "decision": decision,
                    "next_action": decision.get("next_action", "continue"),
                    "target_role": decision.get("target_role", "plan"),
                    "instructions": decision.get("instructions", ""),
                    "strategy": decision.get("strategy", "continue_current_trajectory"),
                    "instructions_for_plan": decision.get("instructions_for_plan", ""),
                    "meta_state": decision.get("meta_state", {}),
                },
            )
        except json.JSONDecodeError:
            return RoleOutput(
                success=True,
                content=response,
                metadata={
                    "decision": {
                        "next_action": "continue",
                        "target_role": "plan",
                        "instructions": response,
                        "strategy": "continue_current_trajectory",
                        "instructions_for_plan": response,
                        "meta_state": {},
                    },
                    "next_action": "continue",
                    "target_role": "plan",
                    "instructions": response,
                    "strategy": "continue_current_trajectory",
                    "instructions_for_plan": response,
                    "meta_state": {},
                },
            )

    def analyze_state(
        self,
        iteration: int,
        leader_context: dict[str, Any],
        trigger_reason: str,
    ) -> RoleOutput:
        """Analyze current state and decide next action."""
        prompt = f"""[Current Iteration]: {iteration}

[Trigger Reason]:
{trigger_reason}

[Leader Context]:
{json.dumps(leader_context, ensure_ascii=False, indent=2)}

Please analyze the current state and provide your decision in JSON format:
{{
    "next_action": "continue" | "success" | "abort",
    "target_role": "plan" | "action" | "judge",
    "instructions": "specific instructions for the target role",
    "strategy": "short label for the current strategy",
    "instructions_for_plan": "specific planning guidance based on memory",
    "meta_state": {{
        "current_strategy": "normalized strategy label",
        "blocked_by": "optional blocker summary",
        "leader_notes": "short global note for future iterations"
    }},
    "reasoning": "brief explanation of your decision"
}}
"""
        return self.execute(prompt)
