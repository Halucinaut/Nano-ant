"""Internal task implementation for Nano Ant-managed optimization tasks."""

from __future__ import annotations

from dataclasses import dataclass, field
import json
import os
import subprocess
import sys
from typing import Any

try:
    import yaml
except ModuleNotFoundError:  # pragma: no cover - optional until internal tasks are loaded.
    yaml = None

from ..config import resolve_env_placeholders
from ..judge import JudgeSkill
from .base import EvalReport, TaskContext
from .default_eval_runner import DefaultEvalRunner


def _require_yaml() -> None:
    if yaml is None:
        raise RuntimeError("PyYAML is required to load internal tasks.")


def _read_yaml(path: str) -> dict[str, Any]:
    _require_yaml()
    with open(path, "r", encoding="utf-8") as handle:
        data = resolve_env_placeholders(yaml.safe_load(handle) or {})
    if not isinstance(data, dict):
        raise ValueError(f"Expected YAML object in {path}")
    return data


@dataclass
class InternalTask(TaskContext):
    """Task definition for Nano Ant-managed, file-based optimization tasks."""

    task_dir: str
    task_type: str = "internal"
    task_name: str = ""
    workspace_path: str = ""
    target_file: str = ""
    cases_file: str = ""
    judge_skill_file: str = ""
    target_llm_file: str = ""
    eval_runner_file: str = ""
    config: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.workspace_path:
            self.workspace_path = self.task_dir
        if not self.task_name:
            self.task_name = os.path.basename(os.path.abspath(self.task_dir))

    def _absolute(self, relative_path: str) -> str:
        return os.path.join(self.task_dir, relative_path)

    def load_target(self) -> str:
        with open(self._absolute(self.target_file), "r", encoding="utf-8") as handle:
            return handle.read()

    def save_target(self, content: str) -> None:
        with open(self._absolute(self.target_file), "w", encoding="utf-8") as handle:
            handle.write(content)

    def load_cases(self) -> list[dict[str, Any]]:
        if not self.cases_file:
            return []
        path = self._absolute(self.cases_file)
        if not os.path.exists(path):
            return []
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
        return [item for item in data if isinstance(item, dict)] if isinstance(data, list) else []

    def get_judge_skill(self) -> JudgeSkill:
        if self.judge_skill_file and os.path.exists(self._absolute(self.judge_skill_file)):
            return JudgeSkill.from_dict(_read_yaml(self._absolute(self.judge_skill_file)))
        return JudgeSkill(
            name=f"{self.task_name}_default_skill",
            description=f"Default evaluation skill for internal task {self.task_name}.",
            pass_threshold=80,
        )

    def build_user_goal(self) -> str:
        return "\n".join([
            f"You are optimizing an internal Nano Ant task: {self.task_name}.",
            f"Task type: {self.task_type}.",
            f"Primary target file: `{self.target_file}`.",
            f"Evaluation cases: `{self.cases_file or '(none)'}`.",
            f"Judge skill file: `{self.judge_skill_file or '(none)'}`.",
            "Improve the target iteratively and use the evaluation results as the ground truth signal.",
        ])

    def build_plan_context(self) -> str:
        target_preview = self.load_target()[:1200] if self.target_file and os.path.exists(self._absolute(self.target_file)) else ""
        cases = self.load_cases()
        case_names = [str(item.get("name", "unnamed")) for item in cases[:10]]
        skill = self.get_judge_skill()
        parts = [
            f"[Internal Task]",
            f"- Task Name: {self.task_name}",
            f"- Task Type: {self.task_type}",
            f"- Target File: {self.target_file}",
            f"- Cases File: {self.cases_file or '(none)'}",
            f"- Case Count: {len(cases)}",
            f"- Case Names: {json.dumps(case_names, ensure_ascii=False)}",
            f"- Judge Skill: {skill.name}",
        ]
        if target_preview:
            parts.extend(["", "[Target Preview]", target_preview])
        return "\n".join(parts)

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
        if not self.target_llm_file:
            return default_http_config
        path = self._absolute(self.target_llm_file)
        if not os.path.exists(path):
            return default_http_config
        return _read_yaml(path)

    def _evaluate_with_script(self) -> EvalReport:
        script_path = self._absolute(self.eval_runner_file)
        result = subprocess.run(
            [sys.executable, script_path],
            cwd=self.task_dir,
            capture_output=True,
            text=True,
            timeout=300,
            check=False,
        )
        report_path = self._absolute("eval_report.json")
        payload: dict[str, Any] = {}
        if os.path.exists(report_path):
            with open(report_path, "r", encoding="utf-8") as handle:
                payload = json.load(handle)
        elif result.stdout.strip():
            try:
                payload = json.loads(result.stdout)
            except json.JSONDecodeError:
                payload = {
                    "summary": "Custom eval runner did not emit JSON output.",
                    "errors": [result.stderr.strip()] if result.stderr.strip() else [],
                    "passed": result.returncode == 0,
                }

        report = EvalReport.from_payload(payload)
        if result.returncode != 0 and not report.errors:
            report.errors.append(result.stderr.strip() or "Custom eval runner failed")
            report.passed = False
        if not report.summary:
            report.summary = "Custom eval runner completed."
        return report

    def evaluate(self) -> EvalReport:
        if self.eval_runner_file and os.path.exists(self._absolute(self.eval_runner_file)):
            return self._evaluate_with_script()

        target_content = self.load_target()
        cases = self.load_cases()
        runner = DefaultEvalRunner(self._load_target_llm_config())
        return runner.evaluate(target_content=target_content, cases=cases)

    @classmethod
    def from_dir(cls, task_dir: str) -> "InternalTask":
        metadata: dict[str, Any] = {}
        config: dict[str, Any] = {}
        marker_path = os.path.join(task_dir, ".nano_ant_template.yaml")
        config_path = os.path.join(task_dir, "config.yaml")

        if os.path.exists(marker_path):
            metadata = _read_yaml(marker_path)
        if os.path.exists(config_path):
            config = _read_yaml(config_path)

        def pick(*candidates: str) -> str:
            for candidate in candidates:
                if candidate and os.path.exists(os.path.join(task_dir, candidate)):
                    return candidate
            return candidates[0] if candidates else ""

        task_type = str(
            metadata.get("template_type")
            or config.get("task_type")
            or "internal"
        )
        task_name = str(
            metadata.get("name")
            or config.get("task_name")
            or os.path.basename(os.path.abspath(task_dir))
        )

        target_file = str(
            metadata.get("prompt_file")
            or config.get("target_file")
            or pick("prompt.txt", "target.md", "target.txt", "target.py")
        )
        cases_file = str(
            metadata.get("cases_file")
            or config.get("cases_file")
            or pick("cases.json", "test_cases.json")
        )
        judge_skill_file = str(
            metadata.get("judge_skill_file")
            or config.get("judge_skill_file")
            or pick("judge_skill.yaml")
        )
        target_llm_file = str(
            metadata.get("target_llm_file")
            or config.get("target_llm_file")
            or pick("target_llm.yaml")
        )
        eval_runner_file = str(
            metadata.get("eval_runner")
            or config.get("eval_runner")
            or ("eval_runner.py" if os.path.exists(os.path.join(task_dir, "eval_runner.py")) else "")
        )

        return cls(
            task_dir=task_dir,
            task_type=task_type,
            task_name=task_name,
            workspace_path=task_dir,
            target_file=target_file,
            cases_file=cases_file,
            judge_skill_file=judge_skill_file,
            target_llm_file=target_llm_file,
            eval_runner_file=eval_runner_file,
            config=config,
            metadata=metadata,
        )
