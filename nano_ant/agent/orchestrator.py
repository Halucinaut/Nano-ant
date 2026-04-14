"""Orchestrator - main controller for the Nano Ant agent."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
import os

try:
    import yaml
except ModuleNotFoundError:  # pragma: no cover - optional until config file loading is used.
    yaml = None

from .roles import LeaderRole, PlanRole, ActionRole, JudgeRole
from ..llm.client import LLMClient
from ..llm.claude_code_client import ClaudeCodeClient, HybridClient
from ..memory.context import Context, IterationRecord
from ..checkpoint.manager import CheckpointManager
from ..config import resolve_env_placeholders
from ..sandbox.executor import SandboxExecutor
from ..harness import (
    EffectTracker,
    WorkflowStateMachine,
)
from ..harness.telemetry import IterationTelemetry
from ..harness.sandbox_pool import SandboxPool
from ..agent.action_models import ActionObservation
from ..judge import JudgeSkillRegistry
from ..tasks import TaskContext
from ..tools import ActionToolExecutor, ToolProvider


@dataclass
class AgentConfig:
    """Configuration for the agent."""

    max_iterations: int = 10
    early_stop_rounds: int = 3
    retry_per_role: int = 2
    checkpoint_enabled: bool = True
    checkpoint_path: str = "./checkpoints"
    workspace_path: str = "./workspace"
    sandbox_enabled: bool = True
    log_level: str = "info"
    progress_report: bool = True
    action_backend: str = "llm"
    claude_code_path: str = "claude"
    use_leader: bool = False

    llm_backend: str = "http"
    llm_model: str = "gpt-4"
    llm_base_url: str = "https://api.openai.com/v1"
    llm_api_key: str = ""
    hybrid_primary: str = "claude_code"

    harness_enabled: bool = True
    use_workflow_sm: bool = True
    use_sandbox_pool: bool = True
    sandbox_pool_size: int = 2
    use_structured_feedback: bool = True
    telemetry_enabled: bool = True
    short_circuit_threshold: int = 3
    judge_default_skill: str = "default"

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AgentConfig":
        agent_data = data.get("agent", {})
        checkpoint_data = data.get("checkpoint", {})
        workspace_data = data.get("workspace", {})
        logging_data = data.get("logging", {})
        harness_data = data.get("harness", {})
        llm_data = data.get("llm", {})
        judge_data = data.get("judge", {})

        return cls(
            max_iterations=agent_data.get("max_iterations", 10),
            early_stop_rounds=agent_data.get("early_stop_rounds", 3),
            retry_per_role=agent_data.get("retry_per_role", 2),
            checkpoint_enabled=checkpoint_data.get("enabled", True),
            checkpoint_path=checkpoint_data.get("path", "./checkpoints"),
            workspace_path=workspace_data.get("path", "./workspace"),
            sandbox_enabled=workspace_data.get("sandbox_enabled", True),
            log_level=logging_data.get("level", "info"),
            progress_report=logging_data.get("progress_report", True),
            action_backend=agent_data.get("action_backend", agent_data.get("coding_tool", "llm")),
            claude_code_path=agent_data.get("claude_code_path", "claude"),
            use_leader=agent_data.get("use_leader", False),
            llm_backend=llm_data.get("backend", "http"),
            llm_model=llm_data.get("model", "gpt-4"),
            llm_base_url=llm_data.get("base_url", "https://api.openai.com/v1"),
            llm_api_key=llm_data.get("api_key", ""),
            hybrid_primary=llm_data.get("hybrid_primary", "claude_code"),
            harness_enabled=harness_data.get("enabled", True),
            use_workflow_sm=harness_data.get("use_workflow_sm", True),
            use_sandbox_pool=harness_data.get("use_sandbox_pool", True),
            sandbox_pool_size=harness_data.get("sandbox_pool_size", 2),
            use_structured_feedback=harness_data.get("use_structured_feedback", True),
            telemetry_enabled=harness_data.get("telemetry_enabled", True),
            short_circuit_threshold=harness_data.get("short_circuit_threshold", 3),
            judge_default_skill=judge_data.get("default_skill", "default"),
        )


class Orchestrator:
    """Main orchestrator that coordinates roles and manages the workflow."""

    def __init__(
        self,
        config: AgentConfig,
        llm_configs: dict[str, dict[str, str]],
        prompts: dict[str, str],
        tool_providers: list[ToolProvider] | None = None,
        judge_skill_registry: JudgeSkillRegistry | None = None,
    ):
        self.config = config
        self.llm_configs = llm_configs
        self.prompts = prompts

        self._clients: dict[str, Any] = {}
        self.context: Context | None = None
        self._current_iteration = 0
        self._score_history: list[int] = []
        self.tool_providers = list(tool_providers or [])
        self.judge_skill_registry = judge_skill_registry or JudgeSkillRegistry(default_skill_name=self.config.judge_default_skill)
        self.log_handler: Any = None
        self.task_context: TaskContext | None = None

        self._init_clients()
        self._init_roles()
        self._init_managers()
        self._init_harness()

    def _init_clients(self) -> None:
        """Initialize LLM clients based on backend configuration."""
        backend = self.config.llm_backend

        if backend == "claude_code":
            self._log("Using Claude Code CLI for all LLM calls", "info")
            for role_name in ["leader", "plan", "action", "judge"]:
                self._clients[role_name] = ClaudeCodeClient(
                    claude_code_path=self.config.claude_code_path,
                    working_dir=self.config.workspace_path,
                )
            return

        if backend == "hybrid":
            self._log(f"Using Hybrid LLM client (primary: {self.config.hybrid_primary})", "info")
            for role_name in ["leader", "plan", "action", "judge"]:
                self._clients[role_name] = HybridClient(
                    primary=self.config.hybrid_primary,
                    http_config={
                        "model": self.config.llm_model,
                        "base_url": self.config.llm_base_url,
                        "api_key": self.config.llm_api_key,
                    },
                    claude_code_path=self.config.claude_code_path,
                    working_dir=self.config.workspace_path,
                )
            return

        default_config = self.llm_configs.get("default", {})
        for role_name in ["leader", "plan", "action", "judge"]:
            role_config = self.llm_configs.get("roles", {}).get(role_name, default_config)
            if role_name == "action" and not role_config:
                role_config = self.llm_configs.get("roles", {}).get("coding", default_config)
            self._clients[role_name] = LLMClient(
                model=role_config.get("model", default_config.get("model", self.config.llm_model)),
                base_url=role_config.get("base_url", default_config.get("base_url", self.config.llm_base_url)),
                api_key=role_config.get("api_key", default_config.get("api_key", self.config.llm_api_key)),
            )

    def _init_roles(self) -> None:
        """Initialize all roles."""
        self.leader = None
        if self.config.use_leader:
            self.leader = LeaderRole(
                llm_client=self._clients["leader"],
                system_prompt=self.prompts.get("leader", ""),
                max_retries=self.config.retry_per_role,
            )

        self.plan = PlanRole(
            llm_client=self._clients["plan"],
            system_prompt=self.prompts.get("plan", ""),
            max_retries=self.config.retry_per_role,
        )

        self.action = ActionRole(
            llm_client=self._clients["action"],
            system_prompt=self.prompts.get("action", self.prompts.get("coding", "")),
            workspace_path=self.config.workspace_path,
            max_retries=self.config.retry_per_role,
            action_backend=self.config.action_backend,
            claude_code_path=self.config.claude_code_path,
        )

        self.judge = JudgeRole(
            llm_client=self._clients["judge"],
            system_prompt=self.prompts.get("judge", ""),
            workspace_path=self.config.workspace_path,
            max_retries=self.config.retry_per_role,
            skill_registry=self.judge_skill_registry,
        )

    def _init_managers(self) -> None:
        """Initialize checkpoint manager and sandbox executor."""
        self.checkpoint_manager = CheckpointManager(
            checkpoint_path=self.config.checkpoint_path,
            enabled=self.config.checkpoint_enabled,
        )

        self.sandbox = None
        if self.config.sandbox_enabled:
            self.sandbox = SandboxExecutor(workspace_path=self.config.workspace_path)
        self.tool_executor = ActionToolExecutor(
            workspace_path=self.config.workspace_path,
            sandbox=self.sandbox,
            external_providers=self.tool_providers,
        )

    def _init_harness(self) -> None:
        """Initialize harness components."""
        self.effect_tracker = EffectTracker() if self.config.harness_enabled else None
        self.workflow_sm = WorkflowStateMachine(max_iterations=self.config.max_iterations) if self.config.use_workflow_sm else None
        self.sandbox_pool = None
        if self.config.use_sandbox_pool and self.config.sandbox_enabled:
            self.sandbox_pool = SandboxPool(
                pool_size=self.config.sandbox_pool_size,
                workspace_base=os.path.join(self.config.workspace_path, "_pools"),
            )
            self.sandbox_pool.start()
        self.telemetry = IterationTelemetry(
            short_circuit_threshold=self.config.short_circuit_threshold,
        ) if self.config.telemetry_enabled else None

    def _log(self, message: str, level: str = "info") -> None:
        """Log a message."""
        if not self.config.progress_report:
            return
        prefix = {
            "info": "ℹ️",
            "success": "✅",
            "error": "❌",
            "warning": "⚠️",
            "progress": "🔄",
        }.get(level, "•")
        line = f"{prefix} {message}"
        if self.log_handler:
            self.log_handler(level, line)
            return
        print(line)

    def _report_iteration_start(self, iteration: int) -> None:
        self._log(f"[Iter {iteration}/{self.config.max_iterations}] Starting...", "progress")

    def _report_role_output(self, role: str, success: bool, summary: str = "") -> None:
        status = "✅" if success else "❌"
        self._log(f"├── {role}: {status} {summary[:100] if summary else ''}")

    def _should_invoke_leader(self, iteration: int) -> tuple[bool, str]:
        """Decide whether Leader should be invoked for strategy guidance."""
        if not self.leader or not self.context:
            return False, ""

        if iteration == 0:
            return True, "initial_iteration"

        latest_feedback = self.context.global_state.get("latest_feedback_artifact")
        if latest_feedback:
            try:
                latest_artifact = self.context.global_state.get("latest_feedback_artifact", {})
                critical_actions = latest_artifact.get("fix_actions", [])
                if any(action.get("severity") == "critical" for action in critical_actions):
                    return True, "critical_feedback_detected"
            except Exception:
                pass

        no_improvement_count = self.context.global_state.get("no_improvement_count", 0)
        if no_improvement_count > 0:
            return True, "no_improvement_detected"

        if len(self._score_history) >= 4:
            recent = self._score_history[-4:]
            if all(recent[i] > recent[i + 1] for i in range(len(recent) - 1)):
                return True, "score_degradation"
            if recent[-1] >= 70 and not recent[-1] >= 80:
                return True, "near_success_review"

        return False, ""

    def _record_leader_guidance(self, leader_output: dict[str, Any]) -> None:
        """Persist leader strategy output into shared memory state."""
        if not self.context:
            return

        leader_meta = leader_output.get("metadata", {})
        decision = leader_meta.get("decision", {})
        meta_state = decision.get("meta_state", {}) if isinstance(decision.get("meta_state", {}), dict) else {}

        self.context.global_state["leader_guidance"] = {
            "strategy": decision.get("strategy", leader_meta.get("strategy", "")),
            "instructions_for_plan": decision.get("instructions_for_plan", leader_meta.get("instructions_for_plan", "")),
            "next_action": decision.get("next_action", leader_meta.get("next_action", "continue")),
            "target_role": decision.get("target_role", leader_meta.get("target_role", "plan")),
        }

        existing_meta = self.context.global_state.get("leader_meta_state", {})
        if not isinstance(existing_meta, dict):
            existing_meta = {}
        existing_meta.update(meta_state)
        self.context.global_state["leader_meta_state"] = existing_meta

        invocation_count = self.context.global_state.get("leader_invocation_count", 0)
        self.context.global_state["leader_invocation_count"] = invocation_count + 1

    def _reconfigure_workspace(self, workspace_path: str, checkpoint_path: str | None = None) -> None:
        """Reconfigure role and tool components to operate on a new workspace."""
        new_workspace = workspace_path or self.config.workspace_path
        new_checkpoint = checkpoint_path or self.config.checkpoint_path

        if new_workspace == self.config.workspace_path and new_checkpoint == self.config.checkpoint_path:
            return

        if self.sandbox_pool:
            try:
                self.sandbox_pool.cleanup()
            except Exception:
                pass

        self.config.workspace_path = new_workspace
        self.config.checkpoint_path = new_checkpoint
        self._init_clients()
        self._init_roles()
        self._init_managers()
        self._init_harness()

    def _activate_task_context(self, task_context: TaskContext | None) -> str | None:
        """Bind a task context to this run and return the effective goal."""
        if task_context is None:
            self.task_context = None
            return None

        self.task_context = task_context
        task_checkpoint_path = getattr(task_context, "checkpoint_path", "") or None
        self._reconfigure_workspace(task_context.workspace_path, checkpoint_path=task_checkpoint_path)
        try:
            task_skill = task_context.get_judge_skill()
            self.judge_skill_registry.register(task_skill)
            self.config.judge_default_skill = task_skill.name
        except Exception:
            task_skill = None

        return task_context.build_user_goal()

    def _get_workspace_info(self) -> str:
        info_parts = [f"Path: {self.config.workspace_path}"]

        if os.path.exists(self.config.workspace_path):
            files = []
            for root, dirs, filenames in os.walk(self.config.workspace_path):
                dirs[:] = [d for d in dirs if d not in {".git", "__pycache__", ".nano_ant_venv", "_pools"}]
                for filename in filenames:
                    rel_path = os.path.relpath(os.path.join(root, filename), self.config.workspace_path)
                    files.append(rel_path)
            info_parts.append(f"Files: {len(files)}")
            if files:
                info_parts.append("Sample files: " + ", ".join(files[:10]))

        if self.task_context:
            info_parts.append("")
            info_parts.append("[Task Context]")
            info_parts.append(self.task_context.build_plan_context()[:4000])

        return "\n".join(info_parts)

    def _get_relevant_files(self, plan_output: dict[str, Any]) -> dict[str, str]:
        """Load relevant files referenced by the plan."""
        plan_meta = plan_output.get("metadata", {})
        file_candidates = list(plan_meta.get("files_to_create", []))

        for action in plan_meta.get("actions", []):
            path = action.get("path", "")
            if path:
                file_candidates.append(path)

        files: dict[str, str] = {}
        for filename in dict.fromkeys(file_candidates):
            filepath = os.path.join(self.config.workspace_path, filename)
            if os.path.exists(filepath):
                with open(filepath, "r", encoding="utf-8") as handle:
                    files[filename] = handle.read()
        return files

    def _apply_action_output(self, action_output: dict[str, Any]) -> tuple[list[dict[str, Any]], list[str]]:
        """Execute action output through the tool layer."""
        meta = action_output.get("metadata", {})
        return self.tool_executor.execute(
            action_dicts=meta.get("actions", []),
            code_blocks=meta.get("code_blocks", []),
        )

    def _run_local_tests(self, action_output: dict[str, Any]) -> dict[str, Any]:
        """Run test commands extracted from the action response."""
        meta = action_output.get("metadata", {})
        test_commands = meta.get("test_commands", [])
        if not test_commands:
            return {"passed": True, "output": "No test commands provided", "errors": []}

        results = {"passed": True, "output": "", "errors": []}
        for command in test_commands:
            observation_dicts, _ = self.tool_executor.execute(
                action_dicts=[{"action_type": "run_command", "command": command}],
                code_blocks=[],
            )
            observation = ActionObservation.from_dict(observation_dicts[0])
            results["output"] += f"\n$ {command}\n{observation.stdout}\n{observation.stderr}"
            if not observation.success:
                results["passed"] = False
                results["errors"].append(f"Test failed: {command}")
        return results

    def _install_dependencies(self, action_output: dict[str, Any]) -> None:
        """Install detected python dependencies inside the sandbox when possible."""
        if not self.sandbox:
            return

        commands = action_output.get("metadata", {}).get("dependency_commands", [])
        packages: list[str] = []
        for command in commands:
            if command.startswith("pip install "):
                package = command[len("pip install "):].strip()
                if package:
                    packages.append(package)

        for package in dict.fromkeys(packages):
            success, output = self.sandbox.install_package(package)
            if success:
                self._log(f"Installed dependency: {package}", "info")
            else:
                self._log(f"Failed to install {package}: {output[:100]}", "warning")

    def _resolve_judge_skill_name(self, plan_meta: dict[str, Any]) -> str | None:
        """Resolve the judge skill name for the current iteration."""
        explicit_skill = plan_meta.get("judge_skill")
        if explicit_skill:
            return str(explicit_skill)
        if self.task_context:
            try:
                return self.task_context.get_judge_skill().name
            except Exception:
                pass
        if self.context:
            skill_from_state = self.context.global_state.get("judge_skill")
            if skill_from_state:
                return str(skill_from_state)
        return self.config.judge_default_skill

    def _run_task_evaluation(self) -> dict[str, Any] | None:
        """Run task-context evaluation if a task context is attached."""
        if not self.task_context:
            return None
        try:
            report = self.task_context.evaluate()
            return report.to_test_results()
        except Exception as exc:
            return {
                "passed": False,
                "output": f"Task evaluation failed: {exc}",
                "errors": [str(exc)],
                "metadata": {},
            }

    def _build_state_delta(
        self,
        iteration: int,
        plan_meta: dict[str, Any],
        action_output: dict[str, Any],
        judge_output: dict[str, Any],
        observations: list[dict[str, Any]],
        test_results: dict[str, Any],
    ) -> dict[str, Any]:
        """Build a compact state delta for the completed iteration."""
        judge_meta = judge_output.get("metadata", {})
        files_modified = action_output.get("metadata", {}).get("files_modified", [])
        failed_observations = [obs for obs in observations if not obs.get("success", False)]
        previous_score = self._score_history[-1] if self._score_history else 0
        current_score = judge_meta.get("score", 0)

        return {
            "iteration": iteration,
            "score_delta": current_score - previous_score,
            "new_score": current_score,
            "passed": judge_meta.get("passed", False),
            "files_modified": files_modified,
            "actions_executed": len(action_output.get("metadata", {}).get("actions", [])),
            "failed_action_count": len(failed_observations),
            "test_passed": test_results.get("passed", True),
            "planned_artifacts": plan_meta.get("files_to_create", []),
        }

    def _build_iteration_report(
        self,
        iteration: int,
        leader_output: dict[str, Any],
        plan_output: dict[str, Any],
        action_output: dict[str, Any],
        judge_output: dict[str, Any],
        state_delta: dict[str, Any],
    ) -> dict[str, Any]:
        """Build a stable, user-facing iteration report."""
        judge_meta = judge_output.get("metadata", {})
        leader_meta = leader_output.get("metadata", {})
        plan_meta = plan_output.get("metadata", {})
        return {
            "iteration": iteration,
            "strategy": leader_meta.get("strategy", ""),
            "iteration_goal": plan_meta.get("iteration_goal", ""),
            "actions_planned": len(plan_meta.get("actions", [])),
            "actions_executed": state_delta.get("actions_executed", 0),
            "files_modified": state_delta.get("files_modified", []),
            "passed": judge_meta.get("passed", False),
            "score": judge_meta.get("score", 0),
            "issues": judge_meta.get("issues", [])[:5],
            "state_delta": state_delta,
        }

    def run_iteration(self) -> dict[str, Any]:
        """Run a single iteration of the agent loop."""
        iteration = self._current_iteration

        if self.telemetry:
            self.telemetry.on_iteration_start(iteration)

        leader_output: dict[str, Any] = {}
        plan_output: dict[str, Any] = {}
        action_output: dict[str, Any] = {}
        judge_output: dict[str, Any] = {}
        feedback_artifact = None

        should_invoke_leader, trigger_reason = self._should_invoke_leader(iteration)
        if self.leader and should_invoke_leader:
            leader_context = self.context.build_leader_context(
                current_iteration=iteration,
                score_history=self._score_history,
            ) if self.context else {
                "goal": "",
                "current_iteration": iteration,
                "score_history": [],
            }
            leader_result = self.leader.analyze_state(
                iteration=iteration,
                leader_context=leader_context,
                trigger_reason=trigger_reason,
            )
            leader_output = {
                "success": leader_result.success,
                "content": leader_result.content,
                "metadata": leader_result.metadata,
            }
            self._report_role_output("Leader", leader_result.success, leader_result.content[:100])
            self._record_leader_guidance(leader_output)
            if self.effect_tracker and leader_result.success:
                model = getattr(self._clients["leader"], "model", "unknown")
                self.effect_tracker.log_llm_call(
                    role="leader",
                    iteration=iteration,
                    model=model,
                    prompt="analyze_state",
                    response=leader_result.content[:1000],
                )
            if not leader_result.success:
                return {"iteration": iteration, "leader_output": leader_output, "status": "error", "error": leader_result.error}
        else:
            leader_output = {
                "success": True,
                "content": "Leader not invoked for this iteration; orchestrator proceeding directly to planning.",
                "metadata": {
                    "decision": {
                        "next_action": "continue",
                        "target_role": "plan",
                        "strategy": self.context.global_state.get("leader_meta_state", {}).get("current_strategy", "continue_current_trajectory") if self.context else "continue_current_trajectory",
                        "instructions_for_plan": self.context.global_state.get("leader_guidance", {}).get("instructions_for_plan", "") if self.context else "",
                        "meta_state": self.context.global_state.get("leader_meta_state", {}) if self.context else {},
                    },
                    "next_action": "continue",
                    "target_role": "plan",
                    "strategy": self.context.global_state.get("leader_meta_state", {}).get("current_strategy", "continue_current_trajectory") if self.context else "continue_current_trajectory",
                    "instructions_for_plan": self.context.global_state.get("leader_guidance", {}).get("instructions_for_plan", "") if self.context else "",
                },
            }

        plan_result = self.plan.create_plan(
            user_goal=self.context.user_goal,
            workspace_info=self._get_workspace_info(),
            feedback=self.context.get_feedback_for_plan() if self.context else None,
            plan_state=self.context.global_state.get("plan_state", {}) if self.context else {},
        )
        plan_output = {
            "success": plan_result.success,
            "content": plan_result.content,
            "metadata": plan_result.metadata,
        }
        if self.telemetry:
            self.telemetry.on_plan_created(iteration, plan_result.metadata)
        if not plan_result.success:
            return {
                "iteration": iteration,
                "leader_output": leader_output,
                "plan_output": plan_output,
                "status": "error",
                "error": plan_result.error,
            }

        plan_meta = plan_result.metadata
        judge_skill_name = self._resolve_judge_skill_name(plan_meta)
        planning_mode = plan_meta.get("planning_mode", "single_step")
        current_step = plan_meta.get("current_step", 1)
        total_steps = plan_meta.get("total_steps", 1)
        if planning_mode == "multi_step":
            self._report_role_output("Plan", True, f"Step {current_step}/{total_steps}")
        else:
            self._report_role_output("Plan", True, plan_meta.get("iteration_goal", "") or plan_result.content[:100])

        relevant_files = self._get_relevant_files(plan_output)
        action_prompt = plan_meta.get("prompt_for_action", plan_result.content)
        action_result = self.action.execute_plan(
            task_prompt=action_prompt,
            relevant_files=relevant_files,
            planned_actions=plan_meta.get("actions", []),
        )
        action_output = {
            "success": action_result.success,
            "content": action_result.content,
            "metadata": action_result.metadata,
        }
        if not action_result.success:
            return {
                "iteration": iteration,
                "leader_output": leader_output,
                "plan_output": plan_output,
                "action_output": action_output,
                "status": "error",
                "error": action_result.error,
            }

        if self.telemetry:
            self.telemetry.on_action_generated(iteration, action_result.content, "action")

        observations, executed_files = self._apply_action_output(action_output)
        action_output["metadata"]["observations"] = observations
        action_output["metadata"]["files_modified"] = list(dict.fromkeys(
            action_output["metadata"].get("files_modified", []) + executed_files
        ))
        self._report_role_output(
            "Action",
            True,
            f"{len(action_output['metadata'].get('actions', []))} actions, {len(action_output['metadata'].get('files_modified', []))} files",
        )

        if self.effect_tracker:
            model = getattr(self._clients["action"], "model", "unknown")
            self.effect_tracker.log_llm_call(
                role="action",
                iteration=iteration,
                model=model,
                prompt=action_prompt[:1000],
                response=action_result.content[:1000],
            )
            for block in action_output["metadata"].get("code_blocks", []):
                filename = block.get("filename")
                if filename:
                    self.effect_tracker.log_file_write(
                        role="action",
                        iteration=iteration,
                        path=filename,
                        content=block.get("code", ""),
                    )

        self._install_dependencies(action_output)
        test_results = self._run_local_tests(action_output)
        task_eval_results = self._run_task_evaluation()
        if task_eval_results:
            combined_output = "\n".join(filter(None, [
                test_results.get("output", ""),
                task_eval_results.get("output", ""),
            ]))
            test_results = {
                "passed": bool(test_results.get("passed", True) and task_eval_results.get("passed", True)),
                "output": combined_output,
                "errors": list(test_results.get("errors", [])) + list(task_eval_results.get("errors", [])),
                "metadata": {
                    **(test_results.get("metadata", {}) if isinstance(test_results.get("metadata", {}), dict) else {}),
                    **(task_eval_results.get("metadata", {}) if isinstance(task_eval_results.get("metadata", {}), dict) else {}),
                },
            }
        if self.telemetry:
            self.telemetry.on_tests_executed(iteration, test_results)

        if self.config.use_structured_feedback and hasattr(self.judge, "evaluate_with_feedback"):
            judge_result, feedback_artifact = self.judge.evaluate_with_feedback(
                user_goal=self.context.user_goal,
                action_output=action_result.content,
                test_results=test_results,
                plan_data=plan_meta,
                actions=action_output["metadata"].get("actions", []),
                observations=observations,
                files_modified=action_output["metadata"].get("files_modified", []),
                files_to_create=plan_meta.get("files_to_create", []),
                iteration=iteration,
                judge_skill_name=judge_skill_name,
                task_type=plan_meta.get("task_type", ""),
            )
        else:
            judge_result = self.judge.evaluate(
                user_goal=self.context.user_goal,
                action_output=action_result.content,
                test_results=test_results,
                plan_data=plan_meta,
                actions=action_output["metadata"].get("actions", []),
                observations=observations,
                files_modified=action_output["metadata"].get("files_modified", []),
                files_to_create=plan_meta.get("files_to_create", []),
                judge_skill_name=judge_skill_name,
                task_type=plan_meta.get("task_type", ""),
            )

        judge_output = {
            "success": judge_result.success,
            "content": judge_result.content,
            "metadata": judge_result.metadata,
        }
        judge_meta = judge_result.metadata
        if self.telemetry:
            self.telemetry.on_judge_evaluation(
                iteration=iteration,
                passed=judge_meta.get("passed", False),
                score=judge_meta.get("score", 0),
                feedback=judge_meta.get("feedback", ""),
            )

        self._report_role_output(
            "Judge",
            judge_result.success and judge_meta.get("passed", False),
            f"Score: {judge_meta.get('score', 0)}, Passed: {judge_meta.get('passed', False)}",
        )

        state_delta = self._build_state_delta(
            iteration=iteration,
            plan_meta=plan_meta,
            action_output=action_output,
            judge_output=judge_output,
            observations=observations,
            test_results=test_results,
        )
        iteration_report = self._build_iteration_report(
            iteration=iteration,
            leader_output=leader_output,
            plan_output=plan_output,
            action_output=action_output,
            judge_output=judge_output,
            state_delta=state_delta,
        )

        self._score_history.append(judge_meta.get("score", 0))
        if self.telemetry:
            should_stop, reason = self.telemetry.should_short_circuit(iteration, self._score_history)
            if should_stop:
                return {
                    "iteration": iteration,
                    "status": "short_circuit",
                    "reason": reason,
                    "leader_output": leader_output,
                    "plan_output": plan_output,
                    "action_output": action_output,
                    "coding_output": action_output,
                    "judge_output": judge_output,
                    "state_delta": state_delta,
                    "iteration_report": iteration_report,
                }

        if planning_mode == "multi_step":
            completed_steps = list(plan_meta.get("completed_steps", []))
            if current_step not in completed_steps:
                completed_steps.append(current_step)
            plan_state = {
                "planning_mode": planning_mode,
                "total_steps": total_steps,
                "current_step": current_step,
                "completed_steps": completed_steps,
            }
            all_steps_done = len(completed_steps) >= total_steps
        else:
            plan_state = {"planning_mode": "single_step"}
            all_steps_done = True

        result = {
            "iteration": iteration,
            "leader_output": leader_output,
            "plan_output": plan_output,
            "action_output": action_output,
            "coding_output": action_output,
            "judge_output": judge_output,
            "test_results": test_results,
            "plan_state": plan_state,
            "state_delta": state_delta,
            "iteration_report": iteration_report,
            "status": "success" if judge_meta.get("passed", False) and all_steps_done else "continue",
        }
        if feedback_artifact:
            result["feedback_artifact"] = feedback_artifact.to_dict()
        return result

    def run(self, user_goal: str, resume: int | None = None, task_context: TaskContext | None = None) -> dict[str, Any]:
        """Run the agent loop."""
        effective_goal = self._activate_task_context(task_context) or user_goal
        user_goal = effective_goal
        self._log(f"Starting Nano Ant with goal: {user_goal[:100]}...", "info")

        if resume is not None:
            state = self.checkpoint_manager.load(resume)
            if state:
                self.context = Context.from_dict(state)
                self._current_iteration = self.context.global_state.get("total_iterations", 0)
                self._log(f"Resumed from iteration {resume}", "info")
            else:
                self._log(f"Could not find checkpoint {resume}, starting fresh", "warning")
                self.context = Context(user_goal, self.config.workspace_path)
                self._current_iteration = 0
        else:
            self.context = Context(user_goal, self.config.workspace_path)
            self._current_iteration = 0

        if self.task_context and self.context:
            self.context.global_state["task_plan_context"] = self.task_context.build_plan_context()
            self.context.global_state["task_type"] = self.task_context.task_type
            try:
                self.context.global_state["judge_skill"] = self.task_context.get_judge_skill().name
            except Exception:
                pass
        self._score_history = [
            int(record.judge_output.get("metadata", {}).get("score", 0))
            for record in self.context.iteration_history
            if isinstance(record.judge_output, dict)
        ]

        final_result: dict[str, Any] = {}

        while self._current_iteration < self.config.max_iterations:
            self._report_iteration_start(self._current_iteration + 1)
            iter_result = self.run_iteration()

            record = IterationRecord(
                iteration=self._current_iteration,
                leader_output=iter_result.get("leader_output", {}),
                plan_output=iter_result.get("plan_output", {}),
                action_output=iter_result.get("action_output", iter_result.get("coding_output", {})),
                coding_output=iter_result.get("coding_output", iter_result.get("action_output", {})),
                judge_output=iter_result.get("judge_output", {}),
                feedback_artifact=iter_result.get("feedback_artifact", {}),
                state_delta=iter_result.get("state_delta", {}),
                iteration_report=iter_result.get("iteration_report", {}),
            )
            self.context.add_iteration(record)

            if "plan_state" in iter_result:
                self.context.global_state["plan_state"] = iter_result["plan_state"]
            if "feedback_artifact" in iter_result:
                self.context.global_state["latest_feedback_artifact"] = iter_result["feedback_artifact"]
            if "iteration_report" in iter_result:
                self.context.global_state["last_iteration_report"] = iter_result["iteration_report"]

            judge_meta = iter_result.get("judge_output", {}).get("metadata", {})
            score = judge_meta.get("score", 0)
            improved = self.context.update_best(score, self._current_iteration)

            if improved:
                self.checkpoint_manager.save_best(self._current_iteration)
                self._log(f"New best score: {score}", "success")

            self.checkpoint_manager.save(iteration=self._current_iteration, context_data=self.context.to_dict())
            self._log(f"Checkpoint saved: iter_{self._current_iteration:03d}", "info")

            if iter_result.get("status") == "error":
                final_result = {
                    "status": "error",
                    "iterations": self._current_iteration + 1,
                    "best_score": self.context.global_state["best_score"],
                    "checkpoint_path": self.checkpoint_manager.get_checkpoint_path(self._current_iteration),
                    "error": iter_result.get("error", "Unknown iteration error"),
                }
                break

            if iter_result.get("status") == "short_circuit":
                final_result = {
                    "status": "short_circuit",
                    "iterations": self._current_iteration + 1,
                    "best_score": self.context.global_state["best_score"],
                    "checkpoint_path": self.checkpoint_manager.get_checkpoint_path(self._current_iteration),
                    "reason": iter_result.get("reason", ""),
                }
                break

            if iter_result.get("status") == "success" and judge_meta.get("passed", False):
                final_result = {
                    "status": "success",
                    "iterations": self._current_iteration + 1,
                    "best_score": score,
                    "checkpoint_path": self.checkpoint_manager.get_checkpoint_path(self._current_iteration),
                }
                break

            if self.context.global_state["no_improvement_count"] >= self.config.early_stop_rounds:
                final_result = {
                    "status": "early_stop",
                    "iterations": self._current_iteration + 1,
                    "best_score": self.context.global_state["best_score"],
                    "checkpoint_path": self.checkpoint_manager.get_checkpoint_path(self.context.global_state["best_iteration"]),
                }
                break

            self._current_iteration += 1
        else:
            final_result = {
                "status": "max_iterations",
                "iterations": self.config.max_iterations,
                "best_score": self.context.global_state["best_score"],
                "checkpoint_path": self.checkpoint_manager.get_checkpoint_path(self.context.global_state["best_iteration"]),
            }

        self._log(f"Final Result: {final_result['status']}", "info")
        self._log(f"Total Iterations: {final_result['iterations']}", "info")
        self._log(f"Best Score: {final_result['best_score']}", "info")
        self._log(f"Checkpoint: {final_result['checkpoint_path']}", "info")
        return final_result

    def get_final_feedback(self) -> str:
        """Return the most recent judge feedback."""
        if not self.context or not self.context.iteration_history:
            return ""
        last_record = self.context.iteration_history[-1]
        return str(last_record.judge_output.get("metadata", {}).get("feedback", "") or "")

    @classmethod
    def _load_prompts(cls, config_data: dict[str, Any], config_path: str | None = None) -> dict[str, str]:
        """Load prompts from configured locations with package fallback."""
        prompt_dirs: list[str] = []

        if config_path:
            prompt_dirs.append(os.path.join(os.path.dirname(config_path), "prompts"))

        configured_prompt_dir = config_data.get("prompts_dir")
        if configured_prompt_dir:
            prompt_dirs.append(configured_prompt_dir)

        package_prompt_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "prompts"))
        prompt_dirs.append(package_prompt_dir)

        prompts: dict[str, str] = {}
        prompt_map = {
            "leader": "leader.txt",
            "plan": "plan.txt",
            "action": "action.txt",
            "judge": "judge.txt",
        }

        for prompt_dir in prompt_dirs:
            if not os.path.exists(prompt_dir):
                continue
            for role, filename in prompt_map.items():
                if role in prompts:
                    continue
                prompt_file = os.path.join(prompt_dir, filename)
                if os.path.exists(prompt_file):
                    with open(prompt_file, "r", encoding="utf-8") as handle:
                        prompts[role] = handle.read()

            legacy_action_prompt = os.path.join(prompt_dir, "coding.txt")
            if "action" not in prompts and os.path.exists(legacy_action_prompt):
                with open(legacy_action_prompt, "r", encoding="utf-8") as handle:
                    prompts["action"] = handle.read()

        return prompts

    @classmethod
    def from_config_file(cls, config_path: str) -> "Orchestrator":
        if yaml is None:
            raise RuntimeError("PyYAML is required to load configuration files.")
        with open(config_path, "r", encoding="utf-8") as handle:
            config_data = resolve_env_placeholders(yaml.safe_load(handle) or {})

        agent_config = AgentConfig.from_dict(config_data)
        prompts = cls._load_prompts(config_data, config_path=config_path)
        llm_configs = {
            "default": config_data.get("llm", {}).get("default", {}),
            "roles": config_data.get("llm", {}).get("roles", {}),
        }
        judge_skill_registry = JudgeSkillRegistry.from_config(config_data)
        return cls(
            config=agent_config,
            llm_configs=llm_configs,
            prompts=prompts,
            judge_skill_registry=judge_skill_registry,
        )

    @classmethod
    def from_config_dict(
        cls,
        config_data: dict[str, Any],
        prompts: dict[str, str] | None = None,
        tool_providers: list[ToolProvider] | None = None,
    ) -> "Orchestrator":
        resolved_config = resolve_env_placeholders(config_data)
        agent_config = AgentConfig.from_dict(resolved_config)
        prompt_data = prompts or cls._load_prompts(resolved_config)
        llm_configs = {
            "default": resolved_config.get("llm", {}).get("default", {}),
            "roles": resolved_config.get("llm", {}).get("roles", {}),
        }
        judge_skill_registry = JudgeSkillRegistry.from_config(resolved_config)
        return cls(
            config=agent_config,
            llm_configs=llm_configs,
            prompts=prompt_data,
            tool_providers=tool_providers,
            judge_skill_registry=judge_skill_registry,
        )
