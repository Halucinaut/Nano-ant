"""CLI entrypoint for Nano Ant."""

from __future__ import annotations

import argparse
import os
import shlex
import sys
from typing import Any

from .interactive import InteractiveSessionState, InteractiveTerminalUI, run_interactive_task
from .integration import ExternalTask
from .runner import NanoAntRunner, ROLE_NAMES, TaskRequest
from .tasks import InternalTask, ProjectTask, detect_project_task
from .template_mode import (
    compose_template_goal,
    detect_template_mode,
    scaffold_prompt_optimization_template,
    summarize_template,
)


def _add_role_llm_arguments(parser: argparse.ArgumentParser) -> None:
    for role in ROLE_NAMES:
        parser.add_argument(
            f"--{role}-model",
            type=str,
            default=None,
            help=f"Override model for the {role} role",
        )
        parser.add_argument(
            f"--{role}-base-url",
            type=str,
            default=None,
            help=f"Override base URL for the {role} role",
        )
        parser.add_argument(
            f"--{role}-api-key",
            type=str,
            default=None,
            help=f"Override API key for the {role} role",
        )


def _build_llm_override(args: argparse.Namespace) -> dict[str, object]:
    llm_override: dict[str, object] = {"default": {}, "roles": {}}

    if args.backend:
        llm_override["backend"] = args.backend

    default_override = {
        "model": args.model,
        "base_url": args.base_url,
        "api_key": args.api_key,
    }
    llm_override["default"] = {
        key: value
        for key, value in default_override.items()
        if value not in (None, "")
    }

    role_overrides: dict[str, dict[str, str]] = {}
    for role in ROLE_NAMES:
        role_override = {
            "model": getattr(args, f"{role}_model"),
            "base_url": getattr(args, f"{role}_base_url"),
            "api_key": getattr(args, f"{role}_api_key"),
        }
        cleaned = {
            key: value
            for key, value in role_override.items()
            if value not in (None, "")
        }
        if cleaned:
            role_overrides[role] = cleaned

    llm_override["roles"] = role_overrides
    return llm_override


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Nano Ant - a lightweight iterative harness agent framework",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  nano-ant "Create a simple calculator with add and subtract functions"
  nano-ant "Continue the task" --resume 5
  nano-ant --init-template ./prompt-task
  nano-ant "Complete the task" --backend http --model deepseek-v3 --base-url https://example.com/v1 --api-key sk-xxx
  ant
        """,
    )

    parser.add_argument(
        "goal",
        type=str,
        nargs="?",
        help="The goal/task for the agent to accomplish",
    )
    parser.add_argument(
        "--config",
        "-c",
        type=str,
        default="config.yaml",
        help="Path to configuration file (default: config.yaml)",
    )
    parser.add_argument(
        "--resume",
        "-r",
        type=int,
        default=None,
        help="Resume from a specific iteration checkpoint",
    )
    parser.add_argument(
        "--workspace",
        "-w",
        type=str,
        default=None,
        help="Override workspace path from config",
    )
    parser.add_argument(
        "--max-iter",
        "-m",
        type=int,
        default=None,
        help="Override max iterations from config",
    )
    parser.add_argument(
        "--skill",
        type=str,
        default=None,
        help="Override default judge skill for this run",
    )
    parser.add_argument(
        "--backend",
        type=str,
        default=None,
        help="Override LLM backend for this run: http | claude_code | hybrid",
    )
    parser.add_argument(
        "--model",
        type=str,
        default=None,
        help="Override default model for all roles",
    )
    parser.add_argument(
        "--base-url",
        type=str,
        default=None,
        help="Override default OpenAI-compatible base URL for all roles",
    )
    parser.add_argument(
        "--api-key",
        type=str,
        default=None,
        help="Override default API key for all roles",
    )
    parser.add_argument(
        "--interactive",
        "-i",
        action="store_true",
        help="Launch the interactive ant shell",
    )
    parser.add_argument(
        "--init-template",
        type=str,
        default=None,
        help="Scaffold a prompt optimization template in the given directory and exit",
    )
    parser.add_argument(
        "--force-template",
        action="store_true",
        help="Overwrite existing files when used with --init-template",
    )
    parser.add_argument(
        "--project",
        type=str,
        default=None,
        help="Run a unified ant.yaml task directory",
    )
    parser.add_argument(
        "--task-dir",
        type=str,
        default=None,
        help="Deprecated compatibility flag. Prefer passing the project dir directly or using --project.",
    )
    parser.add_argument(
        "--external-task-config",
        type=str,
        default=None,
        help="Deprecated compatibility flag for older external integration configs.",
    )
    parser.add_argument(
        "--resource-id",
        type=str,
        default=None,
        help="Select the resource id when using --external-task-config",
    )
    _add_role_llm_arguments(parser)
    return parser


def _validate_config_path(config_path: str) -> bool:
    if os.path.exists(config_path):
        return True
    print(f"Error: Config file not found: {config_path}")
    print("Please create a config.yaml file or specify one with --config")
    return False


def _build_request_from_args(args: argparse.Namespace, goal: str | None = None, resume: int | None = None) -> TaskRequest:
    task_context = _build_task_context_from_args(args)
    effective_goal = goal or args.goal or ""
    if task_context is not None and not effective_goal.strip():
        effective_goal = task_context.build_user_goal()
    llm_override = _build_llm_override(args)
    if not llm_override["default"] and not llm_override["roles"] and "backend" not in llm_override:
        llm_override = {}
    return TaskRequest(
        goal=effective_goal,
        workspace=args.workspace,
        resume=resume if resume is not None else args.resume,
        max_iterations=args.max_iter,
        judge_skill=args.skill,
        llm=llm_override,
        task_context=task_context,
    )


def _print_result(result) -> None:  # noqa: ANN001
    print("\n" + "=" * 60)
    print("  Execution Complete")
    print("=" * 60)
    print(f"\nStatus: {result.status}")
    print(f"Iterations: {result.iterations}")
    print(f"Best Score: {result.best_score}")
    print(f"Workspace: {result.workspace}")
    print(f"Checkpoint: {result.checkpoint_path}")
    if result.last_iteration_report:
        print(f"Last Iteration Goal: {result.last_iteration_report.get('iteration_goal', '')}")
        print(f"Last Iteration Score: {result.last_iteration_report.get('score', 0)}")
    if result.final_feedback:
        print(f"Final Feedback: {result.final_feedback[:200]}")
    print()


def _run_single_task(runner: NanoAntRunner, request: TaskRequest) -> int:
    if request.workspace:
        os.makedirs(request.workspace, exist_ok=True)
    result = runner.run(request)
    _print_result(result)
    return 0 if result.status == "success" else 1


def _apply_interactive_setting(state: dict[str, Any], key: str, value: str) -> str:
    normalized = key.strip().lower()
    llm_override = state.setdefault("llm_override", {"default": {}, "roles": {}})
    llm_override.setdefault("default", {})
    llm_override.setdefault("roles", {})

    if normalized == "workspace":
        state["workspace"] = value
        return f"workspace set to {value}"
    if normalized in {"skill", "judge-skill"}:
        state["skill"] = value
        return f"judge skill set to {value}"
    if normalized in {"max-iter", "max_iter"}:
        state["max_iter"] = int(value)
        return f"max iterations set to {value}"
    if normalized == "backend":
        llm_override["backend"] = value
        return f"backend set to {value}"
    if normalized == "model":
        llm_override["default"]["model"] = value
        return f"default model set to {value}"
    if normalized == "base-url":
        llm_override["default"]["base_url"] = value
        return f"default base_url set to {value}"
    if normalized == "api-key":
        llm_override["default"]["api_key"] = value
        return "default api_key updated"

    for suffix, field_name in (
        ("-model", "model"),
        ("-base-url", "base_url"),
        ("-api-key", "api_key"),
    ):
        if normalized.endswith(suffix):
            role_name = normalized[:-len(suffix)]
            if role_name in ROLE_NAMES:
                llm_override["roles"].setdefault(role_name, {})
                llm_override["roles"][role_name][field_name] = value
                return f"{role_name} {field_name} set"

    raise ValueError(f"Unsupported setting key: {key}")


def _interactive_request(state: dict[str, Any], goal: str, resume: int | None = None) -> TaskRequest:
    llm_override = state.get("llm_override", {})
    if not llm_override.get("default") and not llm_override.get("roles") and "backend" not in llm_override:
        llm_override = {}
    effective_goal = goal
    task_context = state.get("task_context")
    if task_context is not None and (not goal.strip() or detect_project_task(goal.strip())):
        effective_goal = task_context.build_user_goal()
    return TaskRequest(
        goal=effective_goal,
        workspace=state.get("workspace"),
        resume=resume,
        max_iterations=state.get("max_iter"),
        judge_skill=state.get("skill"),
        llm=llm_override,
        task_context=task_context,
    )


def _build_task_context_from_args(args: argparse.Namespace):
    if getattr(args, "project", None):
        return ProjectTask.from_dir(args.project)
    if args.task_dir:
        return InternalTask.from_dir(args.task_dir)
    if args.external_task_config:
        return ExternalTask.from_config(args.external_task_config, resource_id=args.resource_id)
    return None


def _apply_task_context_to_state(state: dict[str, Any], task_context) -> None:  # noqa: ANN001
    state["task_context"] = task_context
    if task_context is None:
        return
    if not state.get("workspace"):
        state["workspace"] = task_context.workspace_path
    try:
        if not state.get("skill"):
            state["skill"] = task_context.get_judge_skill().name
    except Exception:
        pass


def _resolve_template_workspace(state: dict[str, Any]) -> str | None:
    workspace = state.get("workspace")
    if workspace:
        return str(workspace)
    cwd = os.getcwd()
    if detect_template_mode(cwd):
        return cwd
    return None


def _sync_ui_state(session_state: InteractiveSessionState, state: dict[str, Any]) -> None:
    llm_override = state.get("llm_override", {})
    template_workspace = _resolve_template_workspace(state)
    session_state.workspace = state.get("workspace", "") or (template_workspace or "")
    session_state.judge_skill = state.get("skill", "")
    session_state.backend = str(llm_override.get("backend", "") or "")
    session_state.max_iter = state.get("max_iter")

    metadata = detect_template_mode(template_workspace) if template_workspace else None
    session_state.template_mode = bool(metadata)
    session_state.template_name = str(metadata.get("name", "")) if metadata else ""
    session_state.template_lines = summarize_template(metadata) if metadata else []


def _scaffold_template(path: str, force: bool) -> int:
    created = scaffold_prompt_optimization_template(path, force=force)
    print(f"Template created at {path}")
    for item in created:
        print(f"- {item}")
    print()
    print("Next steps:")
    print("1. Fill target_llm.yaml with the target business model.")
    print("2. Update cases.json and judge_skill.yaml.")
    print("3. Run ant, then use /optimize.")
    return 0


def _run_template_optimization(
    runner: NanoAntRunner,
    state: dict[str, Any],
    session_state: InteractiveSessionState,
    ui: InteractiveTerminalUI,
) -> int:
    workspace = _resolve_template_workspace(state)
    if not workspace:
        session_state.add_log("No template workspace found. Use /template init <path> first.")
        return 1

    metadata = detect_template_mode(workspace)
    if not metadata:
        session_state.add_log(f"Workspace is not a template-mode directory: {workspace}")
        return 1

    if not state.get("workspace"):
        state["workspace"] = workspace
    if not state.get("skill"):
        state["skill"] = str(metadata.get("template_skill_name", "prompt_optimizer"))

    task_context = InternalTask.from_dir(workspace)
    state["task_context"] = task_context
    goal = compose_template_goal(workspace, metadata)
    state["last_goal"] = goal
    _sync_ui_state(session_state, state)
    session_state.add_log(f"Template optimization started in {workspace}")
    return run_interactive_task(runner, _interactive_request(state, goal=goal), session_state, ui)


def _task_command(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="ant task", description="Run or create Nano Ant task directories")
    subparsers = parser.add_subparsers(dest="task_command")

    create_parser = subparsers.add_parser("create", help="Create a task directory")
    create_parser.add_argument("task_type", choices=["prompt_optimization"])
    create_parser.add_argument("--name", required=True, help="Task directory name")
    create_parser.add_argument("--path", default="tasks", help="Parent directory for the new task")

    run_parser = subparsers.add_parser("run", help="Run an internal task directory")
    run_parser.add_argument("task_dir", help="Path to the task directory")
    run_parser.add_argument("--config", "-c", default="config.yaml")

    status_parser = subparsers.add_parser("status", help="Show basic task info")
    status_parser.add_argument("task_dir", help="Path to the task directory")

    parsed = parser.parse_args(argv)

    if parsed.task_command == "create":
        if parsed.task_type != "prompt_optimization":
            print(f"Unsupported task type: {parsed.task_type}")
            return 1
        target_dir = os.path.join(parsed.path, parsed.name)
        created = scaffold_prompt_optimization_template(target_dir, force=False)
        print(f"Task created at {target_dir}")
        for item in created:
            print(f"- {item}")
        return 0

    if parsed.task_command == "run":
        if not _validate_config_path(parsed.config):
            return 1
        runner = NanoAntRunner.from_config_file(parsed.config)
        task = ProjectTask.from_dir(parsed.task_dir) if detect_project_task(parsed.task_dir) else InternalTask.from_dir(parsed.task_dir)
        request = TaskRequest(
            goal=task.build_user_goal(),
            workspace=task.workspace_path,
            judge_skill=task.get_judge_skill().name,
            task_context=task,
        )
        return _run_single_task(runner, request)

    if parsed.task_command == "status":
        task = ProjectTask.from_dir(parsed.task_dir) if detect_project_task(parsed.task_dir) else InternalTask.from_dir(parsed.task_dir)
        print(f"task_name={task.task_name}")
        print(f"task_type={task.task_type}")
        print(f"workspace={task.workspace_path}")
        if hasattr(task, "target_file"):
            print(f"target_file={task.target_file}")
        elif hasattr(task, "target_path"):
            print(f"target_path={task.target_path}")
        if hasattr(task, "cases_file"):
            print(f"cases_file={task.cases_file}")
        elif hasattr(task, "cases_path") and getattr(task, "cases_path", ""):
            print(f"cases_path={task.cases_path}")
        print(f"judge_skill={task.get_judge_skill().name}")
        return 0

    parser.print_help()
    return 1


def run_interactive_shell(args: argparse.Namespace) -> int:
    if not _validate_config_path(args.config):
        return 1

    try:
        runner = NanoAntRunner.from_config_file(args.config)
    except RuntimeError as exc:
        print(f"Error: {exc}")
        print("Install dependencies first, for example: pip install .")
        return 1

    state: dict[str, Any] = {
        "config": args.config,
        "workspace": args.workspace,
        "max_iter": args.max_iter,
        "skill": args.skill,
        "llm_override": _build_llm_override(args),
        "last_goal": "",
        "task_context": _build_task_context_from_args(args),
    }
    if state["task_context"] and not state.get("workspace"):
        state["workspace"] = state["task_context"].workspace_path
    if state["task_context"] and not state.get("skill"):
        try:
            state["skill"] = state["task_context"].get_judge_skill().name
        except Exception:
            pass

    session_state = InteractiveSessionState(config_path=args.config)
    _sync_ui_state(session_state, state)
    ui = InteractiveTerminalUI(session_state)
    session_state.add_log("Interactive shell ready. Use /help for commands.")
    if session_state.template_mode:
        session_state.add_log("Template workspace detected. Use /optimize to start prompt optimization.")

    while True:
        _sync_ui_state(session_state, state)
        ui.render(footer="Type a task, use /optimize, or /help for commands.")
        try:
            line = input("ant> ").strip()
        except EOFError:
            print()
            return 0
        except KeyboardInterrupt:
            print("\nUse /exit to leave the shell.")
            continue

        if not line:
            continue

        if not line.startswith("/"):
            stripped = line.strip()
            if detect_project_task(stripped):
                try:
                    _apply_task_context_to_state(state, ProjectTask.from_dir(stripped))
                    state["last_goal"] = state["task_context"].build_user_goal()
                    _sync_ui_state(session_state, state)
                    run_interactive_task(runner, _interactive_request(state, goal=stripped), session_state, ui)
                except Exception as exc:
                    session_state.add_log(f"Project task load failed: {exc}")
                continue
            state["last_goal"] = line
            _sync_ui_state(session_state, state)
            run_interactive_task(runner, _interactive_request(state, goal=line), session_state, ui)
            continue

        try:
            parts = shlex.split(line)
        except ValueError as exc:
            session_state.add_log(f"Invalid command: {exc}")
            continue

        command = parts[0].lower()
        if command in {"/exit", "/quit"}:
            return 0
        if command == "/help":
            for help_line in [
                "Commands:",
                "  <task text>            Run a task",
                "  /run <task text>       Run a task explicitly",
                "  /run <project_dir>     Run ant.yaml task directory",
                "  /optimize              Run prompt optimization in template mode",
                "  /template              Show current template summary",
                "  /template init <path>  Create a prompt optimization template",
                "  /resume <iteration>    Resume from a checkpoint iteration",
                "  /config                Show current interactive settings",
                "  /set <key> <value>     Update workspace, backend, model, judge-model, and more",
                "  /exit                  Exit the shell",
            ]:
                session_state.add_log(help_line)
            continue
        if command == "/config":
            llm_override = state.get("llm_override", {})
            session_state.add_log(f"config={state['config']}")
            session_state.add_log(f"workspace={state.get('workspace') or '(from config)'}")
            session_state.add_log(f"max_iterations={state.get('max_iter') or '(from config)'}")
            session_state.add_log(f"judge_skill={state.get('skill') or '(default)'}")
            session_state.add_log(f"backend={llm_override.get('backend', '(from config)')}")
            session_state.add_log(f"default_llm={llm_override.get('default', {})}")
            if llm_override.get("roles"):
                session_state.add_log(f"role_overrides={llm_override.get('roles')}")
            template_workspace = _resolve_template_workspace(state)
            if template_workspace:
                session_state.add_log(f"template_workspace={template_workspace}")
            continue
        if command == "/run":
            if len(parts) < 2:
                session_state.add_log("Usage: /run <task text>")
                continue
            goal = line[len("/run"):].strip()
            if detect_project_task(goal):
                try:
                    _apply_task_context_to_state(state, ProjectTask.from_dir(goal))
                    state["last_goal"] = state["task_context"].build_user_goal()
                    _sync_ui_state(session_state, state)
                    run_interactive_task(runner, _interactive_request(state, goal=goal), session_state, ui)
                except Exception as exc:
                    session_state.add_log(f"Project task load failed: {exc}")
                continue
            state["last_goal"] = goal
            _sync_ui_state(session_state, state)
            run_interactive_task(runner, _interactive_request(state, goal=goal), session_state, ui)
            continue
        if command == "/resume":
            if len(parts) != 2 or not parts[1].isdigit():
                session_state.add_log("Usage: /resume <iteration>")
                continue
            resume_iter = int(parts[1])
            goal = state["last_goal"] or "Resume previous task"
            _sync_ui_state(session_state, state)
            run_interactive_task(runner, _interactive_request(state, goal=goal, resume=resume_iter), session_state, ui)
            continue
        if command == "/optimize":
            _run_template_optimization(runner, state, session_state, ui)
            continue
        if command == "/template":
            if len(parts) >= 2 and parts[1] == "init":
                target = parts[2] if len(parts) >= 3 else (state.get("workspace") or os.path.join(os.getcwd(), "prompt-task"))
                try:
                    scaffold_prompt_optimization_template(target, force=False)
                    state["workspace"] = target
                    state["task_context"] = None
                    _sync_ui_state(session_state, state)
                    session_state.add_log(f"Template initialized at {target}")
                    session_state.add_log("Fill target_llm.yaml, then use /optimize.")
                except Exception as exc:
                    session_state.add_log(f"Template init failed: {exc}")
                continue
            template_workspace = _resolve_template_workspace(state)
            metadata = detect_template_mode(template_workspace) if template_workspace else None
            if not metadata:
                session_state.add_log("No template workspace detected. Use /template init <path>.")
                continue
            session_state.add_log(f"template={metadata.get('name', 'Prompt Optimization Template')}")
            for template_line in summarize_template(metadata):
                session_state.add_log(template_line)
            continue
        if command == "/set":
            if len(parts) < 3:
                session_state.add_log("Usage: /set <key> <value>")
                continue
            key = parts[1]
            value = line.split(key, 1)[1].strip()
            try:
                message = _apply_interactive_setting(state, key, value)
                _sync_ui_state(session_state, state)
                session_state.add_log(message)
            except Exception as exc:
                session_state.add_log(str(exc))
            continue

        session_state.add_log(f"Unknown command: {command}. Use /help.")


def main(argv: list[str] | None = None) -> int:
    argv = list(argv or sys.argv[1:])
    if argv and argv[0] == "task":
        return _task_command(argv[1:])

    parser = build_parser()
    args = parser.parse_args(argv)

    if args.goal and detect_project_task(args.goal) and not args.project:
        args.project = args.goal
        args.goal = None

    if args.init_template:
        try:
            return _scaffold_template(args.init_template, force=args.force_template)
        except Exception as exc:
            print(f"Error: {exc}")
            return 1

    if args.interactive or (not args.goal and not args.project and not args.task_dir and not args.external_task_config):
        return run_interactive_shell(args)

    if not os.path.exists(args.config):
        print(f"Error: Config file not found: {args.config}")
        print("Please create a config.yaml file or specify one with --config")
        return 1

    print("=" * 60)
    print("  Nano Ant - Iterative Harness Agent")
    print("=" * 60)
    print(f"\nGoal: {args.goal or args.project}")
    print(f"Config: {args.config}")
    if args.resume:
        print(f"Resuming from iteration: {args.resume}")
    if args.skill:
        print(f"Judge Skill: {args.skill}")
    print()

    try:
        runner = NanoAntRunner.from_config_file(args.config)
        return _run_single_task(runner, _build_request_from_args(args))
    except KeyboardInterrupt:
        print("\n\nExecution interrupted by user.")
        print("You can resume later with --resume option.")
        return 130
    except Exception as exc:  # pragma: no cover - CLI error surfacing
        print(f"\nError: {exc}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
