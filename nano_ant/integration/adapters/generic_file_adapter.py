"""Generic file-based adapter for integrating external projects."""

from __future__ import annotations

import json
import os
import subprocess
from typing import Any

from ...tasks.base import EvalReport
from ..adapter_base import ExternalAdapter


class GenericFileAdapter(ExternalAdapter):
    """Read/write file resources and optionally run project-local commands."""

    def __init__(
        self,
        project_path: str,
        resources_dir: str = "",
        default_extension: str = "",
        execute_command: str = "",
        evaluate_command: str = "",
        evaluation_report_path: str = "",
    ):
        self.project_path = project_path
        self.resources_dir = resources_dir
        self.default_extension = default_extension
        self.execute_command = execute_command
        self.evaluate_command = evaluate_command
        self.evaluation_report_path = evaluation_report_path

    def _resolve_path(self, resource_id: str) -> str:
        if os.path.isabs(resource_id):
            return resource_id
        relative = resource_id
        if self.default_extension and not relative.endswith(self.default_extension):
            relative = f"{relative}{self.default_extension}"
        if self.resources_dir:
            relative = os.path.join(self.resources_dir, relative)
        return os.path.join(self.project_path, relative)

    def load_resource(self, resource_id: str) -> str:
        with open(self._resolve_path(resource_id), "r", encoding="utf-8") as handle:
            return handle.read()

    def save_resource(self, resource_id: str, content: str) -> None:
        path = self._resolve_path(resource_id)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(content)

    def execute(self, resource_content: str, context: dict[str, Any]) -> dict[str, Any]:
        if not self.execute_command:
            return {
                "passed": True,
                "stdout": "No external execute command configured.",
                "stderr": "",
                "resource_content_preview": resource_content[:1000],
            }

        result = subprocess.run(
            self.execute_command,
            shell=True,
            cwd=self.project_path,
            capture_output=True,
            text=True,
            timeout=int(context.get("execute_timeout", 300) or 300),
        )
        return {
            "passed": result.returncode == 0,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "return_code": result.returncode,
        }

    def evaluate(self, execution_result: dict[str, Any]) -> EvalReport:
        if self.evaluate_command:
            result = subprocess.run(
                self.evaluate_command,
                shell=True,
                cwd=self.project_path,
                capture_output=True,
                text=True,
                timeout=300,
            )
            payload: dict[str, Any] = {}
            if self.evaluation_report_path:
                report_path = os.path.join(self.project_path, self.evaluation_report_path)
                if os.path.exists(report_path):
                    with open(report_path, "r", encoding="utf-8") as handle:
                        payload = json.load(handle)
            elif result.stdout.strip():
                try:
                    payload = json.loads(result.stdout)
                except json.JSONDecodeError:
                    payload = {
                        "summary": "External evaluator did not emit JSON output.",
                        "errors": [result.stderr.strip()] if result.stderr.strip() else [],
                        "passed": result.returncode == 0,
                    }
            report = EvalReport.from_payload(payload)
            if result.returncode != 0 and not report.errors:
                report.errors.append(result.stderr.strip() or "External evaluation command failed")
                report.passed = False
            return report

        passed = bool(execution_result.get("passed", True))
        stdout = str(execution_result.get("stdout", "") or "")
        stderr = str(execution_result.get("stderr", "") or "")
        return EvalReport(
            total_cases=0,
            successful_cases=0,
            success_rate=1.0 if passed else 0.0,
            overall_score=100.0 if passed else 0.0,
            case_results=[],
            passed=passed,
            summary="External execution completed.",
            errors=[stderr] if stderr else [],
            raw=execution_result,
        )
