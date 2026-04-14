"""Evaluate zao-workflow tagging prompt via unit test output or mock data."""

from __future__ import annotations

import argparse
import glob
import json
import os
import subprocess
import sys
from typing import Any


def load_json(path: str) -> Any:
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def load_cases(path: str) -> list[dict[str, Any]]:
    data = load_json(path)
    if not isinstance(data, list):
        raise ValueError("cases file must be a list")
    return [item for item in data if isinstance(item, dict)]


def latest_result_file(project_path: str) -> str:
    candidates = glob.glob(os.path.join(project_path, "logs", "test_tagging_result_*.json"))
    if not candidates:
        raise FileNotFoundError("No tagging result JSON found under logs/")
    return max(candidates, key=os.path.getmtime)


def run_real_unit_test(project_path: str) -> tuple[int, str, str]:
    script_path = os.path.join(project_path, "tests", "unit", "test_tagging_classify&summarize.py")
    result = subprocess.run(
        [sys.executable, script_path],
        cwd=project_path,
        capture_output=True,
        text=True,
        timeout=600,
        check=False,
    )
    return result.returncode, result.stdout, result.stderr


def build_mock_results(cases: list[dict[str, Any]]) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for case in cases:
        title = str(case.get("title", "") or "")
        keywords = [str(item) for item in case.get("summary_keywords", []) if item]
        summary = "；".join(keywords) if keywords else f"{title} 摘要"
        results.append(
            {
                "id": case.get("id"),
                "title": title,
                "success": True,
                "result": {
                    "content_category": list(case.get("expected_categories", []) or []),
                    "need_verify": bool(case.get("expected_need_verify", False)),
                    "summary": summary,
                },
            }
        )
    return results


def index_results(raw_results: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    indexed: dict[str, dict[str, Any]] = {}
    for item in raw_results:
        if not isinstance(item, dict):
            continue
        case_id = str(item.get("id", ""))
        title = str(item.get("title", ""))
        if case_id:
            indexed[case_id] = item
        if title:
            indexed[title] = item
    return indexed


def evaluate_case(case: dict[str, Any], actual: dict[str, Any] | None) -> dict[str, Any]:
    failed_checks: list[str] = []
    passed_checks: list[str] = []

    if not actual or not actual.get("success"):
        return {
            "name": case.get("title", "unnamed"),
            "success": False,
            "passed_checks": passed_checks,
            "failed_checks": ["processor_failed"],
            "actual": actual or {},
        }

    result = actual.get("result") or {}
    categories = [str(item) for item in result.get("content_category", []) if item]
    need_verify = bool(result.get("need_verify", False))
    summary = str(result.get("summary", "") or "")

    expected_categories = [str(item) for item in case.get("expected_categories", []) if item]
    expected_need_verify = bool(case.get("expected_need_verify", False))
    summary_keywords = [str(item) for item in case.get("summary_keywords", []) if item]

    if categories == expected_categories:
        passed_checks.append("categories_exact_match")
    else:
        failed_checks.append(f"categories_mismatch:{categories}")

    if need_verify == expected_need_verify:
        passed_checks.append("need_verify_match")
    else:
        failed_checks.append(f"need_verify_mismatch:{need_verify}")

    if summary.strip():
        passed_checks.append("summary_non_empty")
    else:
        failed_checks.append("summary_empty")

    if "。" not in summary and "！" not in summary and "？" not in summary:
        passed_checks.append("summary_single_sentence_like")
    else:
        failed_checks.append("summary_not_single_sentence_like")

    missing_keywords = [keyword for keyword in summary_keywords if keyword not in summary]
    if not missing_keywords:
        passed_checks.append("summary_keywords_present")
    else:
        failed_checks.append(f"summary_missing_keywords:{','.join(missing_keywords)}")

    return {
        "name": case.get("title", "unnamed"),
        "success": not failed_checks,
        "passed_checks": passed_checks,
        "failed_checks": failed_checks,
        "actual": {
            "content_category": categories,
            "need_verify": need_verify,
            "summary": summary,
        },
    }


def build_report(cases: list[dict[str, Any]], raw_results: list[dict[str, Any]], errors: list[str] | None = None) -> dict[str, Any]:
    indexed = index_results(raw_results)
    case_results: list[dict[str, Any]] = []

    for case in cases:
        actual = indexed.get(str(case.get("id", ""))) or indexed.get(str(case.get("title", "")))
        case_results.append(evaluate_case(case, actual))

    total_cases = len(case_results)
    successful_cases = sum(1 for item in case_results if item.get("success"))
    success_rate = (successful_cases / total_cases) if total_cases else 0.0
    overall_score = round(success_rate * 100, 2)
    return {
        "meta": {
            "task_name": "zao_tagging_classification",
            "resource_path": "",
            "evaluator": "external_zao_tagging_case.evaluate_zao_tagging",
        },
        "summary": {
            "passed": successful_cases == total_cases and total_cases > 0,
            "overall_score": overall_score,
            "total_cases": total_cases,
            "successful_cases": successful_cases,
            "success_rate": success_rate,
            "text": f"{successful_cases}/{total_cases} tagging cases passed",
        },
        "case_results": [
            {
                "name": item.get("name", "unnamed"),
                "success": bool(item.get("success", False)),
                "score": 100 if item.get("success", False) else 0,
                "passed_checks": item.get("passed_checks", []),
                "failed_checks": item.get("failed_checks", []),
                "input": {},
                "expected": {},
                "actual": item.get("actual", {}),
                "error": "",
            }
            for item in case_results
        ],
        "errors": errors or [],
        "artifacts": [],
        "raw_results": raw_results,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate zao-workflow tagging prompt")
    parser.add_argument("--project-path", required=True)
    parser.add_argument("--cases", required=True)
    parser.add_argument("--mode", choices=["mock", "real"], default="mock")
    parser.add_argument("--report", default="")
    args = parser.parse_args()

    project_path = os.path.abspath(args.project_path)
    cases = load_cases(args.cases)

    if args.mode == "mock":
        report = build_report(cases, build_mock_results(cases))
        report["meta"]["resource_path"] = os.path.join(project_path, "prompts", "tagging", "classification.md")
        if args.report:
            with open(args.report, "w", encoding="utf-8") as handle:
                json.dump(report, handle, ensure_ascii=False, indent=2)
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0

    return_code, stdout, stderr = run_real_unit_test(project_path)
    errors: list[str] = []
    if stdout.strip():
        errors.append(stdout.strip())
    if stderr.strip():
        errors.append(stderr.strip())

    try:
        raw_results = load_json(latest_result_file(project_path))
    except Exception as exc:
        report = {
            "meta": {
                "task_name": "zao_tagging_classification",
                "resource_path": os.path.join(project_path, "prompts", "tagging", "classification.md"),
                "evaluator": "external_zao_tagging_case.evaluate_zao_tagging",
            },
            "summary": {
                "passed": False,
                "overall_score": 0.0,
                "total_cases": len(cases),
                "successful_cases": 0,
                "success_rate": 0.0,
                "text": "Failed to load tagging unit test result file",
            },
            "case_results": [],
            "errors": errors + [str(exc)],
            "artifacts": [],
        }
        if args.report:
            with open(args.report, "w", encoding="utf-8") as handle:
                json.dump(report, handle, ensure_ascii=False, indent=2)
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 1

    report = build_report(cases, raw_results, errors=errors)
    report["meta"]["resource_path"] = os.path.join(project_path, "prompts", "tagging", "classification.md")
    if args.report:
        with open(args.report, "w", encoding="utf-8") as handle:
            json.dump(report, handle, ensure_ascii=False, indent=2)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["summary"]["passed"] and return_code == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
