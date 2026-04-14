"""Run prompt evaluation for the product prompt sample."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from typing import Any
from urllib import request

import yaml


WORKSPACE = os.path.dirname(os.path.abspath(__file__))


def load_text(path: str) -> str:
    with open(path, "r", encoding="utf-8") as handle:
        return handle.read()


def load_yaml(path: str) -> dict[str, Any]:
    with open(path, "r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    if not isinstance(data, dict):
        raise ValueError(f"Expected object in {path}")
    return data


def load_cases(path: str) -> list[dict[str, Any]]:
    with open(path, "r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, list):
        raise ValueError("cases.json must be a list")
    return [item for item in data if isinstance(item, dict)]


def call_http_llm(config: dict[str, Any], prompt: str, case_input: str) -> str:
    base_url = str(config.get("base_url", "")).rstrip("/")
    api_key = str(config.get("api_key", ""))
    if api_key.startswith("${") and api_key.endswith("}"):
        api_key = os.getenv(api_key[2:-1], "")
    body = {
        "model": config.get("model"),
        "temperature": config.get("temperature", 0.2),
        "max_tokens": config.get("max_tokens", 800),
        "messages": [],
    }
    system_prompt = str(config.get("system_prompt", "") or "").strip()
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


def call_claude_code(prompt: str, case_input: str) -> str:
    full_prompt = f"{prompt}\n\n[Workflow Input]\n{case_input}"
    result = subprocess.run(
        ["claude", "-p", full_prompt],
        capture_output=True,
        text=True,
        timeout=180,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "claude command failed")
    return result.stdout.strip()


def run_case(config: dict[str, Any], prompt: str, case: dict[str, Any]) -> dict[str, Any]:
    backend = str(config.get("backend", "http") or "http")
    case_input = str(case.get("input", "") or "")

    if backend == "claude_code":
        output = call_claude_code(prompt, case_input)
    elif backend == "http":
        output = call_http_llm(config, prompt, case_input)
    else:
        raise ValueError(f"Unsupported backend: {backend}")

    expected_contains = [str(item) for item in case.get("expected_contains", []) if item]
    must_not_contain = [str(item) for item in case.get("must_not_contain", []) if item]

    passed_checks = []
    failed_checks = []
    for phrase in expected_contains:
        if phrase in output:
            passed_checks.append(f"contains:{phrase}")
        else:
            failed_checks.append(f"missing:{phrase}")

    for phrase in must_not_contain:
        if phrase in output:
            failed_checks.append(f"forbidden:{phrase}")
        else:
            passed_checks.append(f"not_contains:{phrase}")

    return {
        "name": case.get("name", "case"),
        "input": case_input,
        "output": output,
        "notes": case.get("notes", ""),
        "passed_checks": passed_checks,
        "failed_checks": failed_checks,
        "success": not failed_checks and bool(output.strip()),
    }


def main() -> int:
    prompt = load_text(os.path.join(WORKSPACE, "prompt.txt"))
    cases = load_cases(os.path.join(WORKSPACE, "cases.json"))
    llm_config = load_yaml(os.path.join(WORKSPACE, "target_llm.yaml"))

    results = []
    execution_error = ""
    try:
        for case in cases:
            results.append(run_case(llm_config, prompt, case))
    except Exception as exc:
        execution_error = str(exc)

    total_cases = len(cases)
    success_count = sum(1 for item in results if item.get("success"))
    success_rate = (success_count / total_cases) if total_cases else 0.0
    report = {
        "meta": {
            "task_name": "product_prompt_sample",
            "resource_path": os.path.join(WORKSPACE, "prompt.txt"),
            "evaluator": "product_prompt_sample.eval_runner",
            "target_backend": llm_config.get("backend", "http"),
            "target_model": llm_config.get("model", ""),
        },
        "summary": {
            "passed": not execution_error and success_count == total_cases and total_cases > 0,
            "overall_score": round(success_rate * 100, 2),
            "total_cases": total_cases,
            "successful_cases": success_count,
            "success_rate": success_rate,
            "text": f"{success_count}/{total_cases} cases passed",
        },
        "case_results": [
            {
                "name": item.get("name", "case"),
                "success": bool(item.get("success", False)),
                "score": 100 if item.get("success", False) else 0,
                "passed_checks": item.get("passed_checks", []),
                "failed_checks": item.get("failed_checks", []),
                "input": {"text": item.get("input", "")},
                "expected": {
                    "expected_contains": [str(v) for v in next((c.get("expected_contains", []) for c in cases if c.get("name") == item.get("name")), [])],
                    "must_not_contain": [str(v) for v in next((c.get("must_not_contain", []) for c in cases if c.get("name") == item.get("name")), [])],
                },
                "actual": {"output": item.get("output", "")},
                "error": "",
            }
            for item in results
        ],
        "errors": [execution_error] if execution_error else [],
        "artifacts": [
            {
                "type": "report",
                "path": os.path.join(WORKSPACE, "eval_report.json"),
            }
        ],
    }

    report_path = os.path.join(WORKSPACE, "eval_report.json")
    with open(report_path, "w", encoding="utf-8") as handle:
        json.dump(report, handle, ensure_ascii=False, indent=2)

    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if not execution_error else 1


if __name__ == "__main__":
    sys.exit(main())
