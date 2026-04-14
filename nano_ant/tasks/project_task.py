"""Unified project task loaded from an ant.yaml task directory."""

from __future__ import annotations

from dataclasses import dataclass, field
import glob
import json
import os
import subprocess
from typing import Any

try:
    import yaml
except ModuleNotFoundError:  # pragma: no cover
    yaml = None

from ..config import resolve_env_placeholders
from ..judge import JudgeSkill
from .base import EvalReport, TaskContext
from .default_eval_runner import DefaultEvalRunner


def _require_yaml() -> None:
    if yaml is None:
        raise RuntimeError("PyYAML is required to load project tasks.")


def _read_yaml(path: str) -> dict[str, Any]:
    _require_yaml()
    with open(path, "r", encoding="utf-8") as handle:
        data = resolve_env_placeholders(yaml.safe_load(handle) or {})
    if not isinstance(data, dict):
        raise ValueError(f"Expected YAML object in {path}")
    return data


def _safe_name(value: str) -> str:
    return value.replace("\\", "_").replace("/", "_").replace(":", "_").replace(" ", "_")


@dataclass
class ProjectTask(TaskContext):
    """Unified task directory backed by ant.yaml."""

    project_dir: str = ""
    config_path: str = ""
    config: dict[str, Any] = field(default_factory=dict)
    task_name: str = ""
    task_type: str = ""
    workspace_path: str = ""
    target_path: str = ""
    target_sync_path: str = ""
    judge_skill_path: str = ""
    run_command: str = ""
    run_result_json: str = ""
    evaluation_target_llm_path: str = ""
    cases_path: str = ""
    goal_text: str = ""
    context_files: list[str] = field(default_factory=list)
    checkpoint_path: str = ""
    runtime_log_dir: str = ""

    def load_target(self) -> str:
        self._ensure_prompt_use_seeded()
        with open(self.target_path, "r", encoding="utf-8") as handle:
            return handle.read()

    def save_target(self, content: str) -> None:
        os.makedirs(os.path.dirname(self.target_path), exist_ok=True)
        with open(self.target_path, "w", encoding="utf-8") as handle:
            handle.write(content)

    def _ensure_prompt_use_seeded(self) -> None:
        if os.path.exists(self.target_path):
            return
        if not self.target_sync_path or not os.path.exists(self.target_sync_path):
            return
        os.makedirs(os.path.dirname(self.target_path), exist_ok=True)
        with open(self.target_sync_path, "r", encoding="utf-8") as source:
            content = source.read()
        with open(self.target_path, "w", encoding="utf-8") as target:
            target.write(content)

    def get_judge_skill(self) -> JudgeSkill:
        return JudgeSkill.from_dict(_read_yaml(self.judge_skill_path))

    def load_cases(self) -> list[dict[str, Any]]:
        if not self.cases_path or not os.path.exists(self.cases_path):
            return []
        with open(self.cases_path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
        return [item for item in data if isinstance(item, dict)] if isinstance(data, list) else []

    def _load_target_llm_config(self) -> dict[str, Any]:
        default_http_config = {
            "backend": "http",
            "model": "Qwen3-30B-A3B",
            "base_url": "",
            "api_key": "",
            "temperature": 0.2,
            "max_tokens": 800,
            "system_prompt": "",
        }
        if not self.evaluation_target_llm_path or not os.path.exists(self.evaluation_target_llm_path):
            return default_http_config
        return _read_yaml(self.evaluation_target_llm_path)

    def _sync_prompt_before_run(self) -> None:
        if not self.target_sync_path:
            return
        self._ensure_prompt_use_seeded()
        os.makedirs(os.path.dirname(self.target_sync_path), exist_ok=True)
        with open(self.target_path, "r", encoding="utf-8") as source:
            content = source.read()
        with open(self.target_sync_path, "w", encoding="utf-8") as target:
            target.write(content)

    def _load_result_payload(self) -> dict[str, Any]:
        if not self.run_result_json:
            return {}
        matches = glob.glob(self.run_result_json)
        if not matches:
            raise FileNotFoundError(f"Missing run result JSON: {self.run_result_json}")
        result_path = max(matches, key=os.path.getmtime)
        with open(result_path, "r", encoding="utf-8") as handle:
            payload = json.load(handle)
        if isinstance(payload, dict):
            return payload
        if isinstance(payload, list):
            total_cases = len(payload)
            successful_cases = sum(1 for item in payload if isinstance(item, dict) and item.get("success"))
            success_rate = (successful_cases / total_cases) if total_cases else 0.0
            case_results = []
            for item in payload:
                if not isinstance(item, dict):
                    continue
                case_results.append({
                    "name": str(item.get("title", item.get("id", "unnamed"))),
                    "success": bool(item.get("success", False)),
                    "score": 100 if item.get("success", False) else 0,
                    "actual": item.get("result", item),
                    "raw": item,
                })
            return {
                "meta": {
                    "task_name": self.task_name,
                    "resource_path": self.target_sync_path or self.target_path,
                    "evaluator": self.run_command,
                    "result_path": result_path,
                },
                "summary": {
                    "passed": bool(total_cases and successful_cases == total_cases),
                    "overall_score": round(success_rate * 100, 2),
                    "total_cases": total_cases,
                    "successful_cases": successful_cases,
                    "success_rate": success_rate,
                    "text": f"{successful_cases}/{total_cases} cases passed",
                },
                "case_results": case_results,
                "errors": [],
                "artifacts": [{"type": "run_result", "path": result_path}],
                "raw_results": payload,
            }
        raise ValueError(f"Unsupported run result JSON payload type: {type(payload).__name__}")

    def _evaluate_with_command(self) -> EvalReport:
        cwd = self.project_dir
        self._sync_prompt_before_run()
        result = subprocess.run(
            self.run_command,
            shell=True,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=600,
            check=False,
        )
        payload: dict[str, Any] = {}
        if self.run_result_json:
            try:
                payload = self._load_result_payload()
            except Exception as exc:
                payload = {
                    "meta": {
                        "task_name": self.task_name,
                        "resource_path": self.target_sync_path or self.target_path,
                        "evaluator": self.run_command,
                    },
                    "summary": {
                        "passed": False,
                        "overall_score": 0.0,
                        "total_cases": 0,
                        "successful_cases": 0,
                        "success_rate": 0.0,
                        "text": f"Run finished but result JSON was not found or invalid: {self.run_result_json}",
                    },
                    "case_results": [],
                    "errors": [str(exc)],
                    "artifacts": [],
                }
        elif result.stdout.strip():
            try:
                payload = json.loads(result.stdout)
            except json.JSONDecodeError:
                payload = {
                    "summary": {"passed": False, "overall_score": 0, "total_cases": 0, "successful_cases": 0, "success_rate": 0.0},
                    "errors": [result.stderr.strip() or "Evaluator did not emit JSON output"],
                    "case_results": [],
                }
        report = EvalReport.from_payload(payload)
        if result.returncode != 0 and not report.errors:
            report.errors.append(result.stderr.strip() or "Run command failed")
            report.passed = False
        if not report.summary:
            report.summary = "Project evaluation completed."
        return report

    def evaluate(self) -> EvalReport:
        if self.run_command:
            return self._evaluate_with_command()

        cases = self.load_cases()
        runner = DefaultEvalRunner(self._load_target_llm_config())
        return runner.evaluate(target_content=self.load_target(), cases=cases)

    def build_user_goal(self) -> str:
        if self.goal_text:
            return self.goal_text
        return "\n".join([
            f"You are optimizing a project task: {self.task_name}.",
            f"Task type: {self.task_type}.",
            f"Target file: `{self.target_path}`.",
            "Use the configured evaluation flow as the ground truth signal.",
        ])

    def build_plan_context(self) -> str:
        preview = self.load_target()[:1600]
        skill = self.get_judge_skill()
        lines = [
            "[Project Task]",
            f"- Name: {self.task_name}",
            f"- Type: {self.task_type}",
            f"- Project Dir: {self.project_dir}",
            f"- Target: {self.target_path}",
            f"- Sync To: {self.target_sync_path or '(none)'}",
            f"- Judge Skill: {skill.name}",
            f"- Run Command: {self.run_command or '(builtin default evaluator)'}",
        ]
        if self.context_files:
            lines.append(f"- Context Files: {json.dumps(self.context_files, ensure_ascii=False)}")
        lines.extend(["", "[Target Preview]", preview])

        for path in self.context_files[:5]:
            abs_path = self._resolve(path)
            if not os.path.exists(abs_path):
                continue
            with open(abs_path, "r", encoding="utf-8") as handle:
                content = handle.read()[:1200]
            lines.extend(["", f"[Context: {path}]", content])
        return "\n".join(lines)

    def _resolve(self, path_value: str, base_dir: str | None = None) -> str:
        if os.path.isabs(path_value):
            return path_value
        return os.path.abspath(os.path.join(base_dir or self.project_dir, path_value))

    @classmethod
    def from_dir(cls, project_dir: str) -> "ProjectTask":
        project_dir = os.path.abspath(project_dir)
        config_path = os.path.join(project_dir, "ant.yaml")
        if not os.path.exists(config_path):
            raise ValueError(f"ant.yaml not found in {project_dir}")

        config = _read_yaml(config_path)
        task_name = str(config.get("name", os.path.basename(project_dir)) or os.path.basename(project_dir))
        task_type = str(config.get("type", config.get("mode", "project")) or "project")
        goal_text = str(config.get("goal", "") or "")

        target_data = config.get("target", {}) if isinstance(config.get("target", {}), dict) else {}
        target_path = str(target_data.get("path", "") or "")
        if not target_path:
            raise ValueError("ant.yaml requires target.path")
        target_abs_path = os.path.abspath(os.path.join(project_dir, target_path)) if not os.path.isabs(target_path) else target_path
        target_sync_to = str(target_data.get("sync_to", "") or target_data.get("apply_to", "") or "")
        target_sync_abs_path = ""
        if target_sync_to:
            target_sync_abs_path = os.path.abspath(os.path.join(project_dir, target_sync_to)) if not os.path.isabs(target_sync_to) else target_sync_to

        judge_data = config.get("judge", {}) if isinstance(config.get("judge", {}), dict) else {}
        judge_skill = str(judge_data.get("skill", "judge_skill.yaml") or "judge_skill.yaml")
        judge_skill_path = os.path.abspath(os.path.join(project_dir, judge_skill)) if not os.path.isabs(judge_skill) else judge_skill

        run_data = config.get("run", {}) if isinstance(config.get("run", {}), dict) else {}
        evaluation_data = config.get("evaluation", {}) if isinstance(config.get("evaluation", {}), dict) else {}
        report_data = evaluation_data.get("report", {}) if isinstance(evaluation_data.get("report", {}), dict) else {}
        default_eval_data = evaluation_data.get("default", {}) if isinstance(evaluation_data.get("default", {}), dict) else {}

        run_command = str(run_data.get("command", "") or evaluation_data.get("command", "") or "")
        result_json = str(run_data.get("result_json", "") or report_data.get("path", "") or "")
        run_result_json = ""
        if result_json:
            run_result_json = os.path.abspath(os.path.join(project_dir, result_json)) if not os.path.isabs(result_json) else result_json

        target_llm = str(default_eval_data.get("target_llm", "") or "")
        evaluation_target_llm_path = ""
        if target_llm:
            evaluation_target_llm_path = os.path.abspath(os.path.join(project_dir, target_llm)) if not os.path.isabs(target_llm) else target_llm

        cases_path = str(default_eval_data.get("cases", "") or "")
        cases_abs_path = ""
        if cases_path:
            cases_abs_path = os.path.abspath(os.path.join(project_dir, cases_path)) if not os.path.isabs(cases_path) else cases_path

        context_data = config.get("context", {}) if isinstance(config.get("context", {}), dict) else {}
        context_files = [str(item) for item in context_data.get("files", []) if item]

        workspace_abs_path = project_dir
        checkpoint_abs_path = os.path.join(project_dir, "checkpoints")
        runtime_log_dir = os.path.join(project_dir, ".nano_ant_runs")

        return cls(
            project_dir=project_dir,
            config_path=config_path,
            config=config,
            task_name=task_name,
            task_type=task_type,
            workspace_path=workspace_abs_path,
            target_path=target_abs_path,
            target_sync_path=target_sync_abs_path,
            judge_skill_path=judge_skill_path,
            run_command=run_command,
            run_result_json=run_result_json,
            evaluation_target_llm_path=evaluation_target_llm_path,
            cases_path=cases_abs_path,
            goal_text=goal_text,
            context_files=context_files,
            checkpoint_path=checkpoint_abs_path,
            runtime_log_dir=runtime_log_dir,
        )


def detect_project_task(path_value: str | None) -> bool:
    if not path_value:
        return False
    return os.path.isdir(path_value) and os.path.exists(os.path.join(path_value, "ant.yaml"))
