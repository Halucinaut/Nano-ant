"""Skill registry for task-specific judge behavior."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class JudgeSkill:
    """Task-specific audit rubric used by Judge."""

    name: str
    description: str
    audit_focus: list[str] = field(default_factory=list)
    rubric: list[str] = field(default_factory=list)
    required_checks: list[str] = field(default_factory=list)
    pass_threshold: int = 80
    confidence_hint: str = "normal"
    applies_to: list[str] = field(default_factory=list)

    def matches(self, user_goal: str, task_type: str = "") -> bool:
        haystack = f"{task_type} {user_goal}".lower()
        for needle in self.applies_to:
            if needle.lower() in haystack:
                return True
        return False

    def to_prompt_context(self) -> str:
        lines = [
            f"[Judge Skill: {self.name}]",
            self.description,
            f"Pass Threshold: {self.pass_threshold}",
            f"Confidence Hint: {self.confidence_hint}",
        ]
        if self.audit_focus:
            lines.append("Audit Focus:")
            lines.extend(f"- {item}" for item in self.audit_focus)
        if self.rubric:
            lines.append("Rubric:")
            lines.extend(f"- {item}" for item in self.rubric)
        if self.required_checks:
            lines.append("Required Checks:")
            lines.extend(f"- {item}" for item in self.required_checks)
        return "\n".join(lines)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "JudgeSkill":
        return cls(
            name=str(data.get("name", "default")),
            description=str(data.get("description", "") or ""),
            audit_focus=list(data.get("audit_focus", []) or []),
            rubric=list(data.get("rubric", []) or []),
            required_checks=list(data.get("required_checks", []) or []),
            pass_threshold=int(data.get("pass_threshold", 80) or 80),
            confidence_hint=str(data.get("confidence_hint", "normal") or "normal"),
            applies_to=list(data.get("applies_to", []) or []),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "audit_focus": self.audit_focus,
            "rubric": self.rubric,
            "required_checks": self.required_checks,
            "pass_threshold": self.pass_threshold,
            "confidence_hint": self.confidence_hint,
            "applies_to": self.applies_to,
        }


class JudgeSkillRegistry:
    """Registry and resolver for Judge skills."""

    def __init__(self, skills: list[JudgeSkill] | None = None, default_skill_name: str = "default") -> None:
        self.default_skill_name = default_skill_name
        self._skills: dict[str, JudgeSkill] = {}
        for skill in skills or []:
            self.register(skill)
        if default_skill_name not in self._skills:
            self.register(JudgeSkill(
                name=default_skill_name,
                description="General-purpose task evaluation skill.",
                audit_focus=[
                    "goal completion",
                    "action correctness",
                    "artifact completeness",
                    "execution reliability",
                ],
                rubric=[
                    "Reward concrete progress toward the goal.",
                    "Penalize failed actions, missing outputs, and unverifiable claims.",
                    "Keep feedback actionable for the next iteration.",
                ],
                required_checks=[
                    "Verify that the claimed artifacts exist or were modified.",
                    "Verify that failed commands or observations are reflected in the score.",
                ],
                pass_threshold=80,
            ))

    def register(self, skill: JudgeSkill) -> None:
        self._skills[skill.name] = skill

    def get(self, name: str | None) -> JudgeSkill:
        if name and name in self._skills:
            return self._skills[name]
        return self._skills[self.default_skill_name]

    def resolve(self, user_goal: str, explicit_name: str | None = None, task_type: str = "") -> JudgeSkill:
        if explicit_name:
            return self.get(explicit_name)
        for skill in self._skills.values():
            if skill.name == self.default_skill_name:
                continue
            if skill.matches(user_goal=user_goal, task_type=task_type):
                return skill
        return self.get(self.default_skill_name)

    def to_dict(self) -> dict[str, Any]:
        return {
            "default_skill": self.default_skill_name,
            "skills": [skill.to_dict() for skill in self._skills.values()],
        }

    @classmethod
    def from_config(cls, config_data: dict[str, Any]) -> "JudgeSkillRegistry":
        judge_data = config_data.get("judge", {}) if isinstance(config_data.get("judge", {}), dict) else {}
        skills_data = judge_data.get("skills", []) or []
        default_skill = str(judge_data.get("default_skill", "default") or "default")
        skills = [JudgeSkill.from_dict(item) for item in skills_data if isinstance(item, dict)]
        return cls(skills=skills, default_skill_name=default_skill)
