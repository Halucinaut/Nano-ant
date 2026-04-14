"""External task wrapper for integrating existing projects."""

from __future__ import annotations

from dataclasses import dataclass, field
import json
import os
from typing import Any

try:
    import yaml
except ModuleNotFoundError:  # pragma: no cover - optional until external tasks are loaded.
    yaml = None

from ..config import resolve_env_placeholders
from ..judge import JudgeSkill
from ..tasks.base import EvalReport, TaskContext
from .adapter_base import ExternalAdapter
from .adapters import GenericFileAdapter


def _require_yaml() -> None:
    if yaml is None:
        raise RuntimeError("PyYAML is required to load external tasks.")


def _read_yaml(path: str) -> dict[str, Any]:
    _require_yaml()
    with open(path, "r", encoding="utf-8") as handle:
        data = resolve_env_placeholders(yaml.safe_load(handle) or {})
    if not isinstance(data, dict):
        raise ValueError(f"Expected YAML object in {path}")
    return data


def _default_workspace_path(integration_dir: str, resource_id: str) -> str:
    safe_resource = resource_id.replace("\\", "_").replace("/", "_").replace(":", "_")
    return os.path.join(integration_dir, ".nano_ant_external", safe_resource)


@dataclass
class ExternalTask(TaskContext):
    """Task wrapper for external projects with existing workflows."""

    project_path: str
    resource_id: str
    adapter: ExternalAdapter
    judge_skill: JudgeSkill
    task_name: str = ""
    task_type: str = "external"
    workspace_path: str = ""
    config: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.workspace_path:
            self.workspace_path = self.project_path
        if not self.task_name:
            self.task_name = self.resource_id

    def load_target(self) -> str:
        return self.adapter.load_resource(self.resource_id)

    def save_target(self, content: str) -> None:
        self.adapter.save_resource(self.resource_id, content)

    def evaluate(self) -> EvalReport:
        target = self.load_target()
        execution_result = self.adapter.execute(target, self.config.get("execution_context", {}))
        return self.adapter.evaluate(execution_result)

    def get_judge_skill(self) -> JudgeSkill:
        return self.judge_skill

    def build_user_goal(self) -> str:
        project_name = str(self.config.get("project", {}).get("name", os.path.basename(self.project_path)) or os.path.basename(self.project_path))
        return "\n".join([
            f"You are optimizing an external project resource inside `{project_name}`.",
            f"Resource ID: `{self.resource_id}`.",
            "Respect the external project's existing execution and evaluation workflow.",
            "Use the adapter-backed evaluation results as the main optimization signal.",
        ])

    def build_plan_context(self) -> str:
        preview = self.load_target()[:1200]
        return "\n".join([
            "[External Task]",
            f"- Project Path: {self.project_path}",
            f"- Resource ID: {self.resource_id}",
            f"- Judge Skill: {self.judge_skill.name}",
            "",
            "[Resource Preview]",
            preview,
        ])

    @classmethod
    def from_config(cls, config_path: str, resource_id: str | None = None) -> "ExternalTask":
        config_data = _read_yaml(config_path)
        project_data = config_data.get("project", {}) if isinstance(config_data.get("project", {}), dict) else {}
        adapter_data = config_data.get("adapter", {}) if isinstance(config_data.get("adapter", {}), dict) else {}
        resources = config_data.get("resources", []) or []

        selected_resource = None
        for item in resources:
            if not isinstance(item, dict):
                continue
            if resource_id is None or str(item.get("id", "")) == resource_id:
                selected_resource = item
                break
        if not selected_resource:
            raise ValueError("No matching resource found in external task config.")

        integration_dir = os.path.dirname(os.path.abspath(config_path))
        project_path = str(project_data.get("path", os.path.dirname(integration_dir)) or os.path.dirname(integration_dir))

        adapter_type = str(adapter_data.get("type", "generic_file") or "generic_file")
        if adapter_type not in {"generic_file", "external", "zao_workflow"}:
            raise ValueError(f"Unsupported adapter type: {adapter_type}")

        resources_dir = str(adapter_data.get("resources_dir", "") or "")
        default_extension = str(adapter_data.get("default_extension", "") or "")
        adapter = GenericFileAdapter(
            project_path=project_path,
            resources_dir=resources_dir,
            default_extension=default_extension,
            execute_command=str(adapter_data.get("execute_command", "") or ""),
            evaluate_command=str(adapter_data.get("evaluate_command", "") or ""),
            evaluation_report_path=str(adapter_data.get("evaluation_report_path", "") or ""),
        )

        skill_path = selected_resource.get("skill")
        if not skill_path:
            raise ValueError("External task resource must specify a judge skill path.")
        skill_abs_path = skill_path if os.path.isabs(skill_path) else os.path.join(integration_dir, str(skill_path))
        judge_skill = JudgeSkill.from_dict(_read_yaml(skill_abs_path))

        workspace_path = str(
            project_data.get("workspace_path")
            or config_data.get("workspace_path")
            or _default_workspace_path(integration_dir, str(selected_resource.get("id", "")))
        )

        execution_context = {
            "execute_timeout": int(adapter_data.get("execute_timeout", 300) or 300),
        }
        config = {
            "project": project_data,
            "adapter": adapter_data,
            "resource": selected_resource,
            "execution_context": execution_context,
        }
        return cls(
            project_path=project_path,
            resource_id=str(selected_resource.get("id", "")),
            adapter=adapter,
            judge_skill=judge_skill,
            task_name=str(selected_resource.get("name", selected_resource.get("id", "")) or selected_resource.get("id", "")),
            workspace_path=workspace_path,
            config=config,
        )
