"""Default evaluator for internal prompt-optimization tasks."""

from __future__ import annotations

import json
import os
import subprocess
from typing import Any
from urllib import request

from .base import EvalReport


class DefaultEvalRunner:
    """Built-in evaluator for file-based prompt optimization tasks."""

    def __init__(self, llm_config: dict[str, Any]):
        self.llm_config = dict(llm_config or {})

    def evaluate(self, target_content: str, cases: list[dict[str, Any]]) -> EvalReport:
        results: list[dict[str, Any]] = []
        errors: list[str] = []
        for case in cases:
            try:
                output = self._call_llm(target_content, str(case.get("input", "") or ""))
                results.append(self._check_case(output, case))
            except Exception as exc:
                errors.append(str(exc))
                results.append({
                    "name": case.get("name", "unnamed"),
                    "success": False,
                    "output": "",
                    "passed_checks": [],
                    "failed_checks": [f"execution_error:{exc}"],
                })

        total_cases = len(cases)
        successful_cases = sum(1 for item in results if item.get("success"))
        success_rate = (successful_cases / total_cases) if total_cases else 0.0
        score = round(success_rate * 100, 2)
        summary = f"{successful_cases}/{total_cases} cases passed"
        return EvalReport(
            total_cases=total_cases,
            successful_cases=successful_cases,
            success_rate=success_rate,
            overall_score=score,
            case_results=results,
            passed=(not errors and successful_cases >= total_cases if total_cases else not errors),
            summary=summary,
            errors=errors,
            raw={"results": results},
        )

    def _call_llm(self, prompt: str, case_input: str) -> str:
        backend = str(self.llm_config.get("backend", "http") or "http")
        if backend == "claude_code":
            return self._call_claude_code(prompt, case_input)
        if backend == "http":
            return self._call_http_llm(prompt, case_input)
        raise ValueError(f"Unsupported target backend: {backend}")

    def _call_claude_code(self, prompt: str, case_input: str) -> str:
        command = str(self.llm_config.get("claude_code_path", "claude") or "claude")
        full_prompt = f"{prompt}\n\n[Workflow Input]\n{case_input}"
        result = subprocess.run(
            [command, "-p", full_prompt],
            capture_output=True,
            text=True,
            timeout=180,
            check=False,
        )
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip() or "claude command failed")
        return result.stdout.strip()

    def _call_http_llm(self, prompt: str, case_input: str) -> str:
        base_url = str(self.llm_config.get("base_url", "") or "").rstrip("/")
        api_key = str(self.llm_config.get("api_key", "") or "")
        if api_key.startswith("${") and api_key.endswith("}"):
            api_key = os.getenv(api_key[2:-1], "")
        body = {
            "model": self.llm_config.get("model"),
            "temperature": self.llm_config.get("temperature", 0.2),
            "max_tokens": self.llm_config.get("max_tokens", 800),
            "messages": [],
        }
        system_prompt = str(self.llm_config.get("system_prompt", "") or "").strip()
        if system_prompt:
            body["messages"].append({"role": "system", "content": system_prompt})
        body["messages"].append({
            "role": "user",
            "content": f"{prompt}\n\n[Workflow Input]\n{case_input}",
        })
        req = request.Request(
            url=base_url + "/chat/completions",
            data=json.dumps(body).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
            },
            method="POST",
        )
        with request.urlopen(req, timeout=120) as response:
            payload = json.loads(response.read().decode("utf-8"))
        choices = payload.get("choices", [])
        if not choices:
            return ""
        return str(choices[0].get("message", {}).get("content", "") or "")

    def _check_case(self, output: str, case: dict[str, Any]) -> dict[str, Any]:
        expected = [str(item) for item in case.get("expected_contains", []) if item]
        forbidden = [str(item) for item in case.get("must_not_contain", []) if item]

        passed_checks: list[str] = []
        failed_checks: list[str] = []

        for phrase in expected:
            if phrase in output:
                passed_checks.append(f"contains:{phrase}")
            else:
                failed_checks.append(f"missing:{phrase}")

        for phrase in forbidden:
            if phrase in output:
                failed_checks.append(f"forbidden:{phrase}")
            else:
                passed_checks.append(f"not_contains:{phrase}")

        return {
            "name": case.get("name", "unnamed"),
            "success": not failed_checks and bool(output.strip()),
            "output": output,
            "passed_checks": passed_checks,
            "failed_checks": failed_checks,
            "notes": case.get("notes", ""),
        }
