"""Public runner API for Nano Ant."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any

try:
    import yaml
except ModuleNotFoundError:  # pragma: no cover - optional until config file loading is used.
    yaml = None

from .agent.orchestrator import Orchestrator
from .config import resolve_env_placeholders
from .template_mode import merge_template_skill


ROLE_NAMES = ("leader", "plan", "action", "judge")


@dataclass
class TaskRequest:
    """Public request object for running a task."""

    goal: str
    workspace: str | None = None
    resume: int | None = None
    max_iterations: int | None = None
    judge_skill: str | None = None
    llm: dict[str, Any] = field(default_factory=dict)
    task_context: Any = None


@dataclass
class TaskResult:
    """Public result object returned by the runner."""

    status: str
    iterations: int
    best_score: int
    checkpoint_path: str
    workspace: str
    last_iteration_report: dict[str, Any] = field(default_factory=dict)
    final_feedback: str = ""
    artifacts: list[str] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_run_result(
        cls,
        run_result: dict[str, Any],
        workspace: str,
        last_iteration_report: dict[str, Any] | None = None,
        final_feedback: str = "",
        artifacts: list[str] | None = None,
    ) -> "TaskResult":
        return cls(
            status=str(run_result.get("status", "unknown")),
            iterations=int(run_result.get("iterations", 0)),
            best_score=int(run_result.get("best_score", 0)),
            checkpoint_path=str(run_result.get("checkpoint_path", "")),
            workspace=workspace,
            last_iteration_report=last_iteration_report or {},
            final_feedback=final_feedback,
            artifacts=artifacts or [],
            raw=run_result,
        )


class NanoAntRunner:
    """Public facade for configuring and running Nano Ant tasks."""

    def __init__(self, config_data: dict[str, Any], prompts: dict[str, str] | None = None):
        self.config_data = deepcopy(config_data)
        self.prompts = dict(prompts or {})

    @classmethod
    def from_config_file(cls, config_path: str) -> "NanoAntRunner":
        if yaml is None:
            raise RuntimeError("PyYAML is required to load configuration files.")
        with open(config_path, "r", encoding="utf-8") as handle:
            config_data = resolve_env_placeholders(yaml.safe_load(handle) or {})
        prompts = Orchestrator._load_prompts(config_data, config_path=config_path)
        return cls(config_data=config_data, prompts=prompts)

    @classmethod
    def from_config_dict(cls, config_data: dict[str, Any], prompts: dict[str, str] | None = None) -> "NanoAntRunner":
        resolved = resolve_env_placeholders(config_data)
        prompt_data = prompts or Orchestrator._load_prompts(resolved)
        return cls(config_data=resolved, prompts=prompt_data)

    def _ensure_llm_shape(self, config_data: dict[str, Any]) -> dict[str, Any]:
        llm_data = config_data.setdefault("llm", {})
        llm_data.setdefault("default", {})
        llm_data.setdefault("roles", {})
        return llm_data

    def _apply_task_overrides(self, request: TaskRequest) -> dict[str, Any]:
        config_data = deepcopy(self.config_data)

        if request.workspace:
            config_data.setdefault("workspace", {})["path"] = request.workspace

        if request.max_iterations is not None:
            config_data.setdefault("agent", {})["max_iterations"] = request.max_iterations

        if request.judge_skill:
            config_data.setdefault("judge", {})["default_skill"] = request.judge_skill

        if request.llm:
            llm_data = self._ensure_llm_shape(config_data)
            requested_llm = request.llm

            if requested_llm.get("backend"):
                llm_data["backend"] = requested_llm["backend"]

            default_override = requested_llm.get("default", {})
            if isinstance(default_override, dict):
                llm_data["default"].update({
                    key: value
                    for key, value in default_override.items()
                    if value not in (None, "")
                })

            roles_override = requested_llm.get("roles", {})
            if isinstance(roles_override, dict):
                for role_name, role_override in roles_override.items():
                    if role_name not in ROLE_NAMES or not isinstance(role_override, dict):
                        continue
                    llm_data["roles"].setdefault(role_name, {})
                    llm_data["roles"][role_name].update({
                        key: value
                        for key, value in role_override.items()
                        if value not in (None, "")
                    })

        return merge_template_skill(config_data, request.workspace)

    def build_orchestrator(self, request: TaskRequest) -> Orchestrator:
        """Build an orchestrator for the given task request."""
        config_data = self._apply_task_overrides(request)
        return Orchestrator.from_config_dict(config_data, prompts=self.prompts)

    def run(self, request: TaskRequest) -> TaskResult:
        """Run a task request through the orchestrator."""
        orchestrator = self.build_orchestrator(request)
        run_result = orchestrator.run(
            user_goal=request.goal,
            resume=request.resume,
            task_context=request.task_context,
        )

        workspace = orchestrator.config.workspace_path
        last_iteration_report = {}
        final_feedback = ""
        artifacts: list[str] = []
        if orchestrator.context is not None:
            last_iteration_report = orchestrator.context.global_state.get("last_iteration_report", {})
            final_feedback = orchestrator.get_final_feedback() if hasattr(orchestrator, "get_final_feedback") else ""
            for record in orchestrator.context.iteration_history[-3:]:
                files_modified = record.action_output.get("metadata", {}).get("files_modified", [])
                artifacts.extend(files_modified)

        return TaskResult.from_run_result(
            run_result=run_result,
            workspace=workspace,
            last_iteration_report=last_iteration_report,
            final_feedback=final_feedback,
            artifacts=list(dict.fromkeys(artifacts)),
        )
