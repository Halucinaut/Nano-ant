"""Template mode helpers for product-facing prompt optimization workflows."""

from __future__ import annotations

from copy import deepcopy
import json
import os
from typing import Any

try:
    import yaml
except ModuleNotFoundError:  # pragma: no cover - optional until template loading is used.
    yaml = None


TEMPLATE_MARKER = ".nano_ant_template.yaml"
TEMPLATE_TYPE = "prompt_optimization"


def _require_yaml() -> None:
    if yaml is None:
        raise RuntimeError("PyYAML is required to use template mode.")


def _load_yaml_file(path: str) -> dict[str, Any]:
    _require_yaml()
    with open(path, "r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    if not isinstance(data, dict):
        raise ValueError(f"Expected YAML object in {path}")
    return data


def _dump_yaml_file(path: str, data: dict[str, Any]) -> None:
    _require_yaml()
    with open(path, "w", encoding="utf-8") as handle:
        yaml.safe_dump(data, handle, sort_keys=False, allow_unicode=True)


def _write_file(path: str, content: str, force: bool) -> None:
    if os.path.exists(path) and not force:
        raise FileExistsError(f"File already exists: {path}")
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(content)


def _template_metadata() -> dict[str, Any]:
    return {
        "template_type": TEMPLATE_TYPE,
        "name": "Prompt Optimization Template",
        "description": "Optimize a prompt against structured cases with a reusable eval runner.",
        "prompt_file": "prompt.txt",
        "cases_file": "cases.json",
        "judge_skill_file": "judge_skill.yaml",
        "target_llm_file": "target_llm.yaml",
        "eval_runner": "eval_runner.py",
        "task_file": "task.md",
        "eval_report_file": "eval_report.json",
        "recommended_command": "python eval_runner.py",
        "template_skill_name": "prompt_optimizer",
    }


def scaffold_prompt_optimization_template(target_dir: str, force: bool = False) -> list[str]:
    """Create a prompt-optimization template for non-technical users."""
    os.makedirs(target_dir, exist_ok=True)
    metadata = _template_metadata()

    created_paths: list[str] = []

    files_to_write = {
        os.path.join(target_dir, TEMPLATE_MARKER): None,
        os.path.join(target_dir, metadata["prompt_file"]): _prompt_template(),
        os.path.join(target_dir, metadata["cases_file"]): _cases_template(),
        os.path.join(target_dir, metadata["judge_skill_file"]): None,
        os.path.join(target_dir, metadata["target_llm_file"]): None,
        os.path.join(target_dir, metadata["eval_runner"]): _eval_runner_template(),
        os.path.join(target_dir, metadata["task_file"]): _task_template(),
    }

    if yaml is None:
        raise RuntimeError("PyYAML is required to scaffold template mode.")

    marker_path = os.path.join(target_dir, TEMPLATE_MARKER)
    judge_skill_path = os.path.join(target_dir, metadata["judge_skill_file"])
    target_llm_path = os.path.join(target_dir, metadata["target_llm_file"])

    if os.path.exists(marker_path) and not force:
        raise FileExistsError(f"Template already exists at {target_dir}")

    for path, content in files_to_write.items():
        if content is not None:
            _write_file(path, content, force=force)
            created_paths.append(path)

    _dump_yaml_file(marker_path, metadata)
    created_paths.append(marker_path)

    _dump_yaml_file(judge_skill_path, _judge_skill_template())
    created_paths.append(judge_skill_path)

    _dump_yaml_file(target_llm_path, _target_llm_template())
    created_paths.append(target_llm_path)
    return created_paths


def detect_template_mode(workspace: str | None) -> dict[str, Any] | None:
    """Return template metadata if the workspace is a template-mode project."""
    if not workspace:
        return None
    marker_path = os.path.join(workspace, TEMPLATE_MARKER)
    if not os.path.exists(marker_path):
        return None
    metadata = _load_yaml_file(marker_path)
    if str(metadata.get("template_type", "") or "") != TEMPLATE_TYPE:
        return None
    metadata["workspace"] = workspace
    return metadata


def load_template_judge_skill(workspace: str | None) -> dict[str, Any] | None:
    """Load a template-local judge skill definition if present."""
    metadata = detect_template_mode(workspace)
    if not metadata:
        return None
    skill_path = os.path.join(workspace, str(metadata.get("judge_skill_file", "judge_skill.yaml")))
    if not os.path.exists(skill_path):
        return None
    skill_data = _load_yaml_file(skill_path)
    if not skill_data.get("name"):
        skill_data["name"] = str(metadata.get("template_skill_name", "prompt_optimizer"))
    return skill_data


def merge_template_skill(config_data: dict[str, Any], workspace: str | None) -> dict[str, Any]:
    """Merge template-local judge skill into config when template mode is active."""
    skill_data = load_template_judge_skill(workspace)
    if not skill_data:
        return config_data

    merged = deepcopy(config_data)
    judge_data = merged.setdefault("judge", {})
    existing_skills = judge_data.setdefault("skills", [])
    if not isinstance(existing_skills, list):
        existing_skills = []
        judge_data["skills"] = existing_skills

    skill_name = str(skill_data.get("name", "prompt_optimizer"))
    filtered = [
        item for item in existing_skills
        if not isinstance(item, dict) or str(item.get("name", "")) != skill_name
    ]
    filtered.append(skill_data)
    judge_data["skills"] = filtered

    current_default = str(judge_data.get("default_skill", "") or "")
    if not current_default or current_default == "default":
        judge_data["default_skill"] = skill_name

    return merged


def compose_template_goal(workspace: str, metadata: dict[str, Any]) -> str:
    """Build a task goal for the prompt optimization template."""
    prompt_file = str(metadata.get("prompt_file", "prompt.txt"))
    cases_file = str(metadata.get("cases_file", "cases.json"))
    judge_skill_file = str(metadata.get("judge_skill_file", "judge_skill.yaml"))
    target_llm_file = str(metadata.get("target_llm_file", "target_llm.yaml"))
    eval_runner = str(metadata.get("eval_runner", "eval_runner.py"))
    eval_report_file = str(metadata.get("eval_report_file", "eval_report.json"))
    skill_name = str(metadata.get("template_skill_name", "prompt_optimizer"))

    return "\n".join([
        "You are working inside a prompt-optimization template workspace.",
        f"Primary objective: improve `{prompt_file}` against the cases in `{cases_file}`.",
        f"Use the audit rubric defined in `{judge_skill_file}` and prefer judge skill `{skill_name}`.",
        f"The target model used for business evaluation is configured in `{target_llm_file}`.",
        f"After each meaningful prompt change, run `python {eval_runner}` to generate `{eval_report_file}`.",
        "Use the evaluation output to understand failure modes and improve the prompt iteratively.",
        "Prefer modifying the prompt itself. Only update the local template config files when clearly necessary.",
    ])


def summarize_template(metadata: dict[str, Any]) -> list[str]:
    """Return short human-readable lines for UI display."""
    return [
        f"type: {metadata.get('template_type', TEMPLATE_TYPE)}",
        f"prompt: {metadata.get('prompt_file', 'prompt.txt')}",
        f"cases: {metadata.get('cases_file', 'cases.json')}",
        f"skill: {metadata.get('judge_skill_file', 'judge_skill.yaml')}",
        f"target llm: {metadata.get('target_llm_file', 'target_llm.yaml')}",
        f"eval: {metadata.get('recommended_command', 'python eval_runner.py')}",
    ]


def _prompt_template() -> str:
    return (
        "You are a helpful workflow assistant.\n\n"
        "Follow the business rules below:\n"
        "1. Answer clearly and directly.\n"
        "2. Keep the final output concise.\n"
        "3. Use the required format when the user asks for structured output.\n\n"
        "When responding, use the input provided by the workflow as the current task.\n"
    )


def _cases_template() -> str:
    cases = [
        {
            "name": "basic_case",
            "input": "用户想退款，但没有给订单号。",
            "expected_contains": ["订单号", "退款"],
            "must_not_contain": ["无法帮助你"],
            "notes": "应该先礼貌索取必要信息，不要直接拒绝。",
        },
        {
            "name": "structured_case",
            "input": "请给我一个三步执行方案，用于催收缺失资料。",
            "expected_contains": ["1.", "2.", "3."],
            "must_not_contain": ["长篇背景介绍"],
            "notes": "需要输出结构化步骤。",
        },
    ]
    return json.dumps(cases, ensure_ascii=False, indent=2) + "\n"


def _judge_skill_template() -> dict[str, Any]:
    return {
        "name": "prompt_optimizer",
        "description": "Evaluate whether the prompt handles business workflow cases clearly, safely, and consistently.",
        "audit_focus": [
            "instruction clarity",
            "business goal completion",
            "format stability",
            "tone consistency",
        ],
        "rubric": [
            "Reward outputs that directly solve the user input in the expected workflow style.",
            "Penalize missing required structure, vague wording, and answers that skip key business constraints.",
            "Use eval_runner output as concrete evidence when judging improvements.",
        ],
        "required_checks": [
            "Confirm that eval_runner output exists and was regenerated after prompt changes.",
            "Check whether expected phrases or structures appear across representative cases.",
            "Check whether forbidden content still appears in the model output.",
        ],
        "pass_threshold": 82,
        "confidence_hint": "high",
        "applies_to": ["prompt optimization", "workflow prompt", "template mode"],
    }


def _target_llm_template() -> dict[str, Any]:
    return {
        "backend": "http",
        "model": "Qwen3-30B-A3B",
        "base_url": "",
        "api_key": "",
        "temperature": 0.2,
        "max_tokens": 800,
        "system_prompt": "",
    }


def _task_template() -> str:
    return (
        "# Prompt Optimization Task\n\n"
        "这个目录是给产品同学使用的模板模式。\n\n"
        "你只需要关注这几个文件：\n\n"
        "- `prompt.txt`：需要优化的 prompt\n"
        "- `cases.json`：代表性业务样例\n"
        "- `judge_skill.yaml`：审核标准\n"
        "- `target_llm.yaml`：实际跑这个 prompt 的目标模型配置\n\n"
        "推荐流程：\n\n"
        "1. 填好 `target_llm.yaml`\n"
        "2. 补充 `cases.json`\n"
        "3. 根据业务审核标准调整 `judge_skill.yaml`\n"
        "4. 运行 `ant` 进入交互界面\n"
        "5. 输入 `/optimize` 让 Nano Ant 自动开始优化这个 prompt\n"
    )


def _eval_runner_template() -> str:
    return '''"""Run prompt evaluation for the template-mode workspace."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from typing import Any
from urllib import error, request

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
        "content": f"{prompt}\\n\\n[Workflow Input]\\n{case_input}",
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
    message = choices[0].get("message", {})
    return str(message.get("content", "") or "")


def call_claude_code(prompt: str, case_input: str) -> str:
    full_prompt = f"{prompt}\\n\\n[Workflow Input]\\n{case_input}"
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
    except (error.URLError, TimeoutError, RuntimeError, ValueError) as exc:
        execution_error = str(exc)

    success_count = sum(1 for item in results if item.get("success"))
    report = {
        "target_backend": llm_config.get("backend", "http"),
        "target_model": llm_config.get("model", ""),
        "cases": len(cases),
        "executed_cases": len(results),
        "successful_cases": success_count,
        "failed_cases": len(results) - success_count,
        "execution_error": execution_error,
        "results": results,
    }

    report_path = os.path.join(WORKSPACE, "eval_report.json")
    with open(report_path, "w", encoding="utf-8") as handle:
        json.dump(report, handle, ensure_ascii=False, indent=2)

    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if not execution_error else 1


if __name__ == "__main__":
    sys.exit(main())
'''
