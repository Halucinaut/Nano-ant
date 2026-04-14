"""Evaluate zao-workflow's fast-news prompt through the external script pipeline."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from typing import Any


def load_cases(path: str) -> list[dict[str, Any]]:
    with open(path, "r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, list):
        raise ValueError("cases file must be a list")
    return [item for item in data if isinstance(item, dict)]


def run_external_script(project_path: str, input_payload: dict[str, Any]) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="zao_news_flash_case_") as tmpdir:
        input_path = os.path.join(tmpdir, "input.json")
        output_path = os.path.join(tmpdir, "output.json")

        with open(input_path, "w", encoding="utf-8") as handle:
            json.dump(input_payload, handle, ensure_ascii=False, indent=2)

        result = subprocess.run(
            [sys.executable, "scripts/run_script.py", "--input", input_path, "--output", output_path],
            cwd=project_path,
            capture_output=True,
            text=True,
            timeout=300,
            check=False,
        )

        payload: dict[str, Any] = {
            "success": False,
            "data": None,
            "error": result.stderr.strip() or result.stdout.strip(),
        }
        if os.path.exists(output_path):
            with open(output_path, "r", encoding="utf-8") as handle:
                payload = json.load(handle)
        if result.returncode != 0 and not payload.get("error"):
            payload["error"] = f"run_script failed with return code {result.returncode}"
        return payload


def evaluate_case(project_path: str, case: dict[str, Any]) -> dict[str, Any]:
    input_payload = {"news_data": case.get("news_data", [])}
    output = run_external_script(project_path, input_payload)
    result_data = output.get("data") or {}
    analysis = result_data.get("analysis") or {}
    content = str(analysis.get("content", "") or "")
    title = str(analysis.get("title", "") or "")
    content_type = str(result_data.get("content_type", "") or "")

    passed_checks: list[str] = []
    failed_checks: list[str] = []

    if output.get("success"):
        passed_checks.append("processor_success")
    else:
        failed_checks.append(f"processor_error:{output.get('error', 'unknown')}")

    expected_type = str(case.get("expected_content_type", "快讯") or "快讯")
    if content_type == expected_type:
        passed_checks.append(f"content_type:{content_type}")
    else:
        failed_checks.append(f"wrong_content_type:{content_type}")

    if title and len(title) <= 18:
        passed_checks.append("title_length_ok")
    else:
        failed_checks.append(f"title_length_invalid:{len(title)}")

    content_len = len(content)
    if 90 <= content_len <= 170:
        passed_checks.append("content_length_ok")
    else:
        failed_checks.append(f"content_length_invalid:{content_len}")

    for phrase in [str(item) for item in case.get("expected_contains", []) if item]:
        if phrase in content:
            passed_checks.append(f"contains:{phrase}")
        else:
            failed_checks.append(f"missing:{phrase}")

    for phrase in [str(item) for item in case.get("must_not_contain", []) if item]:
        if phrase in content:
            failed_checks.append(f"forbidden:{phrase}")
        else:
            passed_checks.append(f"not_contains:{phrase}")

    return {
        "name": case.get("name", "unnamed"),
        "success": not failed_checks,
        "title": title,
        "content_type": content_type,
        "content": content,
        "passed_checks": passed_checks,
        "failed_checks": failed_checks,
        "error": output.get("error", ""),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate zao-workflow news_flash prompt")
    parser.add_argument("--project-path", required=True)
    parser.add_argument("--cases", required=True)
    args = parser.parse_args()

    project_path = os.path.abspath(args.project_path)
    cases = load_cases(args.cases)
    case_results = [evaluate_case(project_path, case) for case in cases]

    total_cases = len(case_results)
    successful_cases = sum(1 for item in case_results if item.get("success"))
    success_rate = (successful_cases / total_cases) if total_cases else 0.0
    overall_score = round(success_rate * 100, 2)
    report = {
        "total_cases": total_cases,
        "successful_cases": successful_cases,
        "success_rate": success_rate,
        "overall_score": overall_score,
        "passed": successful_cases == total_cases and total_cases > 0,
        "summary": f"{successful_cases}/{total_cases} fast-news cases passed",
        "case_results": case_results,
        "errors": [item["error"] for item in case_results if item.get("error")],
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
