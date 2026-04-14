"""Interactive terminal UI for Nano Ant."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
import os
import queue
import shutil
import threading
import time
from typing import Any

from .runner import NanoAntRunner, TaskRequest, TaskResult


RESET = "\x1b[0m"
BOLD = "\x1b[1m"
DIM = "\x1b[2m"
ACCENT = "\x1b[38;5;114m"
MUTED = "\x1b[38;5;245m"

PIXEL_ANT_LOGO = [
    "      ██      ██      ",
    "  ██████████████████  ",
    "    ██████████████    ",
    "██    ████  ████    ██",
    "  ██  ██      ██  ██  ",
    "      ██      ██      ",
]


def _terminal_size() -> tuple[int, int]:
    size = shutil.get_terminal_size(fallback=(132, 36))
    return max(size.columns, 96), max(size.lines, 28)


def _wrap_text(text: str, width: int) -> list[str]:
    if width <= 8:
        return [text[:width]]
    if not text:
        return [""]
    words = text.split()
    if not words:
        return [text[:width]]

    lines: list[str] = []
    current = words[0]
    for word in words[1:]:
        candidate = f"{current} {word}"
        if len(candidate) <= width:
            current = candidate
        else:
            lines.append(current[:width])
            current = word
    lines.append(current[:width])
    return lines


def _truncate(text: str, width: int) -> str:
    if len(text) <= width:
        return text
    if width <= 3:
        return text[:width]
    return text[:width - 3] + "..."


def _pad(text: str, width: int) -> str:
    return _truncate(text, width).ljust(width)


def _panel(title: str, body_lines: list[str], width: int, height: int | None = None) -> list[str]:
    inner = max(width - 4, 8)
    normalized: list[str] = []
    for line in body_lines:
        wrapped = _wrap_text(line, inner)
        normalized.extend(wrapped or [""])
    if height is not None:
        body_slots = max(height - 4, 1)
        normalized = normalized[:body_slots]
        if len(normalized) < body_slots:
            normalized.extend([""] * (body_slots - len(normalized)))

    top = f"┌{'─' * (width - 2)}┐"
    title_line = f"│ {_pad(title, width - 4)} │"
    divider = f"├{'─' * (width - 2)}┤"
    body = [f"│ {_pad(line, width - 4)} │" for line in normalized]
    bottom = f"└{'─' * (width - 2)}┘"
    border = ACCENT
    return [
        border + top + RESET,
        border + title_line + RESET,
        border + divider + RESET,
        *body,
        border + bottom + RESET,
    ]


def _combine_columns(left: list[str], right: list[str], gap: str = "  ") -> list[str]:
    height = max(len(left), len(right))
    left_width = max((len(_strip_ansi(item)) for item in left), default=0)
    right_width = max((len(_strip_ansi(item)) for item in right), default=0)

    left_padded = left + [" " * left_width] * (height - len(left))
    right_padded = right + [" " * right_width] * (height - len(right))

    combined: list[str] = []
    for left_line, right_line in zip(left_padded, right_padded):
        combined.append(left_line + gap + right_line)
    return combined


def _strip_ansi(text: str) -> str:
    result = []
    i = 0
    while i < len(text):
        if text[i] == "\x1b":
            while i < len(text) and text[i] != "m":
                i += 1
            i += 1
            continue
        result.append(text[i])
        i += 1
    return "".join(result)


@dataclass
class InteractiveSessionState:
    """Mutable state used by the interactive terminal UI."""

    config_path: str
    workspace: str = ""
    judge_skill: str = ""
    backend: str = ""
    max_iter: int | None = None
    logs: list[str] = field(default_factory=list)
    running: bool = False
    current_goal: str = ""
    status: str = "idle"
    last_result: TaskResult | None = None
    spinner_index: int = 0
    template_mode: bool = False
    template_name: str = ""
    template_lines: list[str] = field(default_factory=list)
    run_log_path: str = ""

    def add_log(self, message: str) -> None:
        self.logs.append(message)
        if len(self.logs) > 240:
            self.logs = self.logs[-240:]

    def status_badge(self) -> str:
        if self.running:
            spinner = "|/-\\"[self.spinner_index % 4]
            self.spinner_index += 1
            return f"RUNNING {spinner}"
        if self.last_result:
            return self.last_result.status.upper()
        return self.status.upper()


class InteractiveTerminalUI:
    """ANSI-based interactive UI that renders Nano Ant progress in-place."""

    def __init__(self, state: InteractiveSessionState):
        self.state = state

    def render(self, footer: str = "Type a task or /help") -> None:
        width, height = _terminal_size()
        sidebar_width = min(max(width // 4, 30), 38)
        main_width = width - sidebar_width - 2
        top_height = max(height - 3, 24)
        summary_height = 9
        activity_height = max(top_height - summary_height, 10)

        header = self._build_header(width)
        sidebar = self._build_sidebar(sidebar_width, top_height)
        main = self._build_main(main_width, summary_height, activity_height)
        content = _combine_columns(sidebar, main)
        footer_line = f"{DIM}{_truncate(footer, width)}{RESET}"

        buffer = "\n".join([header, *content[:height - 2], footer_line])
        print("\x1b[2J\x1b[H" + buffer + "\n", end="", flush=True)

    def _build_header(self, width: int) -> str:
        title = f"{BOLD}{ACCENT}Nano Ant{RESET}"
        subtitle = f"{MUTED}interactive harness · prompt/workflow optimization{RESET}"
        status = f"{BOLD}{self.state.status_badge()}{RESET}"
        line = f"{title}  {subtitle}  [{status}]"
        return _truncate(line, width)

    def _build_sidebar(self, width: int, total_height: int) -> list[str]:
        logo_panel = _panel(
            "ANT",
            [*PIXEL_ANT_LOGO, "", "task runtime", "iterative harness"],
            width=width,
            height=12,
        )
        session_lines = [
            f"status: {self.state.status_badge()}",
            f"config: {self.state.config_path}",
            f"workspace: {self.state.workspace or '(from config)'}",
            f"backend: {self.state.backend or '(from config)'}",
            f"judge skill: {self.state.judge_skill or '(default)'}",
            f"max iter: {self.state.max_iter if self.state.max_iter is not None else '(from config)'}",
        ]
        if self.state.run_log_path:
            session_lines.append(f"log: {self.state.run_log_path}")
        session_panel = _panel("SESSION", session_lines, width=width, height=10)

        template_lines = self.state.template_lines or [
            "No template detected.",
            "Use /template init ./prompt-task",
            "or set workspace to an existing",
            "template-mode directory.",
        ]
        template_title = "TEMPLATE" if self.state.template_mode else "MODE"
        template_panel = _panel(template_title, template_lines, width=width, height=11)

        commands = [
            "/run <task>",
            "/optimize",
            "/template",
            "/template init <path>",
            "/set workspace ./demo",
            "/config",
            "/resume <iteration>",
            "/exit",
        ]
        remaining = max(total_height - len(logo_panel) - len(session_panel) - len(template_panel), 8)
        commands_panel = _panel("COMMANDS", commands, width=width, height=remaining)

        return logo_panel + session_panel + template_panel + commands_panel

    def _build_main(self, width: int, summary_height: int, activity_height: int) -> list[str]:
        current_goal = self.state.current_goal or "(idle)"
        summary_lines = [
            f"current goal: {current_goal}",
            f"status: {self.state.status_badge()}",
        ]
        if self.state.last_result:
            result = self.state.last_result
            summary_lines.extend([
                f"last result: {result.status}",
                f"best score: {result.best_score}",
                f"iterations: {result.iterations}",
            ])
            if result.artifacts:
                summary_lines.append("artifacts: " + ", ".join(result.artifacts[:3]))
            if result.final_feedback:
                summary_lines.append("judge: " + result.final_feedback)
        else:
            summary_lines.extend([
                "last result: (none)",
                "best score: (none)",
                "iterations: (none)",
                "judge: (none)",
            ])
        summary_panel = _panel("RUN SUMMARY", summary_lines, width=width, height=summary_height)

        activity_lines = self._build_log_lines(width - 4, activity_height - 4)
        activity_panel = _panel("ACTIVITY", activity_lines, width=width, height=activity_height)
        return summary_panel + activity_panel

    def _build_log_lines(self, width: int, log_height: int) -> list[str]:
        wrapped: list[str] = []
        for raw_line in self.state.logs[-120:]:
            wrapped.extend(_wrap_text(raw_line, width))
        visible = wrapped[-log_height:]
        if len(visible) < log_height:
            visible.extend([""] * (log_height - len(visible)))
        return visible


def run_interactive_task(
    runner: NanoAntRunner,
    request: TaskRequest,
    state: InteractiveSessionState,
    ui: InteractiveTerminalUI,
) -> int:
    """Run a task while rendering live progress to the terminal."""
    event_queue: "queue.Queue[tuple[str, Any]]" = queue.Queue()

    def resolve_log_dir() -> str:
        if request.task_context is not None:
            task_log_dir = getattr(request.task_context, "runtime_log_dir", "") or ""
            if task_log_dir:
                return task_log_dir
            task_workspace = getattr(request.task_context, "workspace_path", "") or ""
            if task_workspace:
                return os.path.join(task_workspace, ".nano_ant_runs")
        if request.workspace:
            return os.path.join(request.workspace, ".nano_ant_runs")
        return os.path.join(os.getcwd(), ".nano_ant_runs")

    def append_run_log(message: str) -> None:
        if not state.run_log_path:
            return
        with open(state.run_log_path, "a", encoding="utf-8") as handle:
            handle.write(message.rstrip() + "\n")

    def worker() -> None:
        try:
            orchestrator = runner.build_orchestrator(request)
            orchestrator.config.progress_report = True
            orchestrator.log_handler = lambda level, line: event_queue.put(("log", line))
            result_dict = orchestrator.run(
                request.goal,
                resume=request.resume,
                task_context=request.task_context,
            )
            last_report = orchestrator.context.global_state.get("last_iteration_report", {}) if orchestrator.context else {}
            final_feedback = orchestrator.get_final_feedback()
            artifacts: list[str] = []
            if orchestrator.context:
                for record in orchestrator.context.iteration_history[-3:]:
                    artifacts.extend(record.action_output.get("metadata", {}).get("files_modified", []))
            task_result = TaskResult.from_run_result(
                run_result=result_dict,
                workspace=orchestrator.config.workspace_path,
                last_iteration_report=last_report,
                final_feedback=final_feedback,
                artifacts=list(dict.fromkeys(artifacts)),
            )
            event_queue.put(("result", task_result))
        except Exception as exc:  # pragma: no cover - surfaced in UI
            event_queue.put(("error", str(exc)))

    state.running = True
    state.current_goal = request.goal
    state.status = "running"
    state.last_result = None
    log_dir = resolve_log_dir()
    os.makedirs(log_dir, exist_ok=True)
    state.run_log_path = os.path.join(log_dir, f"run_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log")
    state.add_log(f"Starting task: {request.goal}")
    append_run_log(f"Starting task: {request.goal}")

    thread = threading.Thread(target=worker, daemon=True)
    thread.start()

    exit_code = 1
    footer = "Running task..."

    try:
        while thread.is_alive() or not event_queue.empty():
            while True:
                try:
                    event_type, payload = event_queue.get_nowait()
                except queue.Empty:
                    break
                if event_type == "log":
                    state.add_log(str(payload))
                    append_run_log(str(payload))
                elif event_type == "result":
                    state.last_result = payload
                    state.status = payload.status
                    state.workspace = payload.workspace
                    exit_code = 0 if payload.status == "success" else 1
                    completion_line = f"Completed: status={payload.status} score={payload.best_score} iterations={payload.iterations}"
                    state.add_log(completion_line)
                    append_run_log(completion_line)
                    if payload.final_feedback:
                        feedback_line = f"Judge feedback: {_truncate(payload.final_feedback, 180)}"
                        state.add_log(feedback_line)
                        append_run_log(feedback_line)
                elif event_type == "error":
                    state.status = "error"
                    state.add_log(f"Error: {payload}")
                    append_run_log(f"Error: {payload}")
                    exit_code = 1
            ui.render(footer=footer)
            time.sleep(0.08)
    finally:
        state.running = False
        if state.last_result is None and state.status == "running":
            state.status = "idle"
        ui.render(footer="Task complete. Press Enter or type the next command.")

    return exit_code
