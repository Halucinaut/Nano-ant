"""Judge Role - evaluates results and determines success."""

from __future__ import annotations

from typing import Any
import json
import subprocess

from .base import BaseRole, RoleOutput
from ...judge import JudgeSkillRegistry
from ...harness.feedback_artifact import (
    FeedbackArtifact,
    FixAction,
    IssueType,
    MetricScore,
    Severity,
)


class JudgeRole(BaseRole):
    """Judge role responsible for evaluating results and determining success."""

    def __init__(
        self,
        llm_client,
        system_prompt: str,
        workspace_path: str,
        max_retries: int = 2,
        skill_registry: JudgeSkillRegistry | None = None,
    ):
        super().__init__("Judge", llm_client, system_prompt, max_retries)
        self.workspace_path = workspace_path
        self.skill_registry = skill_registry or JudgeSkillRegistry()

    def _check_missing_files(
        self,
        files_modified: list[str],
        files_to_create: list[str],
    ) -> tuple[bool, list[str]]:
        """Check if all required files were created."""
        issues = []
        has_missing = False

        for required_file in files_to_create:
            found = False
            for modified in files_modified:
                if required_file in modified or modified in required_file:
                    found = True
                    break
            if not found:
                has_missing = True
                issues.append(f"Missing required file: {required_file}")

        return has_missing, issues

    def _check_empty_implementations(self, code_changes: str) -> tuple[bool, list[str]]:
        """Check if code contains empty implementations (pass, ...)."""
        issues = []
        has_empty = False

        lines = code_changes.split("\n")
        for i, line in enumerate(lines):
            stripped = line.strip()
            if stripped in ["pass", "..."]:
                has_empty = True
                issues.append(f"Line {i+1}: Empty implementation found (pass/...)")

        return has_empty, issues

    def _process_response(self, response: str, **kwargs: Any) -> RoleOutput:
        """Process judge response and extract evaluation results."""
        evaluation = self._extract_json_object(response)
        passed = evaluation.get("passed", False)
        score = evaluation.get("score", 0)

        action_output = kwargs.get("action_output", kwargs.get("code_changes", ""))
        files_modified = kwargs.get("files_modified", [])
        files_to_create = kwargs.get("files_to_create", [])
        observations = kwargs.get("observations", [])
        test_results = kwargs.get("test_results", {})
        judge_skill = kwargs.get("judge_skill")
        pass_threshold = int(kwargs.get("pass_threshold", 80) or 80)

        if action_output:
            has_empty, empty_issues = self._check_empty_implementations(action_output)
            if has_empty:
                passed = False
                if score >= 50:
                    score = min(score, 45)
                evaluation["issues"] = evaluation.get("issues", []) + empty_issues
                evaluation["feedback"] = evaluation.get("feedback", "") + " [AUTO-FAILED: Empty implementations detected]"

        if files_to_create:
            has_missing, missing_issues = self._check_missing_files(files_modified, files_to_create)
            if has_missing:
                passed = False
                if score >= 60:
                    score = min(score, 55)
                evaluation["issues"] = evaluation.get("issues", []) + missing_issues
                evaluation["feedback"] = evaluation.get("feedback", "") + " [AUTO-FAILED: Missing required artifacts]"

        failed_observations = [obs for obs in observations if not obs.get("success", False)]
        if failed_observations:
            passed = False
            if score >= 70:
                score = min(score, 60)
            issues = [
                f"Failed action observation: {obs.get('action_type', 'unknown')} {obs.get('target', '')}".strip()
                for obs in failed_observations
            ]
            evaluation["issues"] = evaluation.get("issues", []) + issues

        if not test_results.get("passed", True):
            passed = False

        if score < pass_threshold:
            passed = False

        if not evaluation.get("stop_recommendation"):
            evaluation["stop_recommendation"] = "success" if passed else "continue"

        evaluation["passed"] = passed
        evaluation["score"] = score
        evaluation["judge_skill"] = judge_skill
        evaluation["pass_threshold"] = pass_threshold

        return RoleOutput(
            success=True,
            content=response,
            metadata={
                "evaluation": evaluation,
                "passed": passed,
                "score": score,
                "feedback": evaluation.get("feedback", response),
                "issues": evaluation.get("issues", []),
                "stop_recommendation": evaluation.get("stop_recommendation", "continue"),
                "judge_skill": judge_skill,
                "pass_threshold": pass_threshold,
                "metrics": evaluation.get("metrics", []),
            },
        )

    def _build_fix_actions(self, issues: list[str], files_modified: list[str]) -> list[FixAction]:
        """Generate structured fix actions from issues."""
        fix_actions: list[FixAction] = []
        primary_target = files_modified[0] if files_modified else ""

        for issue in issues:
            issue_lower = issue.lower()
            if "pass" in issue_lower or "..." in issue_lower:
                fix_actions.append(FixAction(
                    target_file=primary_target,
                    issue_type=IssueType.MISSING_IMPL,
                    severity=Severity.CRITICAL,
                    description=issue,
                    suggested_prompt=f"Fix this issue: {issue}. Do NOT use 'pass' or '...'.",
                ))
            elif "missing" in issue_lower and "file" in issue_lower:
                fix_actions.append(FixAction(
                    target_file=issue.split(":")[-1].strip() if ":" in issue else primary_target,
                    issue_type=IssueType.MISSING_IMPL,
                    severity=Severity.CRITICAL,
                    description=issue,
                    suggested_prompt=f"Create the missing artifact or file referenced here: {issue}",
                ))
            elif "failed action observation" in issue_lower or "test failed" in issue_lower:
                fix_actions.append(FixAction(
                    target_file=primary_target,
                    issue_type=IssueType.BUG,
                    severity=Severity.MAJOR,
                    description=issue,
                    suggested_prompt=f"Investigate and fix the failed execution path: {issue}",
                ))
            else:
                fix_actions.append(FixAction(
                    target_file=primary_target,
                    issue_type=IssueType.QUALITY,
                    severity=Severity.MAJOR,
                    description=issue,
                    suggested_prompt=f"Address this issue: {issue}",
                ))
        return fix_actions

    def _build_metrics(self, metric_dicts: list[dict[str, Any]] | None) -> list[MetricScore]:
        """Normalize metric blocks returned by the Judge model."""
        metrics: list[MetricScore] = []
        for item in metric_dicts or []:
            if not isinstance(item, dict):
                continue
            metrics.append(MetricScore(
                name=str(item.get("name", "metric")),
                score=float(item.get("score", 0)),
                weight=float(item.get("weight", 1.0)),
                explanation=str(item.get("explanation", "") or ""),
            ))
        return metrics

    def run_tests(self, test_commands: list[str]) -> dict[str, Any]:
        """Run automated tests and return results."""
        results = {
            "passed": True,
            "output": "",
            "errors": [],
        }

        if not test_commands:
            results["output"] = "No test commands provided"
            return results

        for cmd in test_commands:
            try:
                result = subprocess.run(
                    cmd,
                    shell=True,
                    cwd=self.workspace_path,
                    capture_output=True,
                    text=True,
                    timeout=60,
                )

                results["output"] += f"\n$ {cmd}\n{result.stdout}\n{result.stderr}"

                if result.returncode != 0:
                    results["passed"] = False
                    results["errors"].append(f"Command failed: {cmd}")

            except subprocess.TimeoutExpired:
                results["passed"] = False
                results["errors"].append(f"Command timed out: {cmd}")
            except Exception as e:
                results["passed"] = False
                results["errors"].append(f"Error running {cmd}: {str(e)}")

        return results

    def evaluate(
        self,
        user_goal: str,
        action_output: str,
        test_results: dict[str, Any],
        plan_data: dict[str, Any],
        actions: list[dict[str, Any]],
        observations: list[dict[str, Any]],
        files_modified: list[str],
        files_to_create: list[str] | None = None,
        judge_skill_name: str | None = None,
        task_type: str = "",
    ) -> RoleOutput:
        """Evaluate the iteration results against the user goal."""
        judge_skill = self.skill_registry.resolve(
            user_goal=user_goal,
            explicit_name=judge_skill_name,
            task_type=task_type,
        )
        prompt = f"""[User Goal]:
{user_goal}

[Judge Skill]:
{judge_skill.to_prompt_context()}

[Plan]:
{json.dumps(plan_data, ensure_ascii=False)[:2000]}

[Action Output]:
{action_output[:3000]}

[Actions]:
{json.dumps(actions, ensure_ascii=False)[:1500]}

[Observations]:
{json.dumps(observations, ensure_ascii=False)[:2000]}

[Files Modified]:
{json.dumps(files_modified, ensure_ascii=False)}

[Files Expected]:
{json.dumps(files_to_create or [], ensure_ascii=False)}

[Test Results]:
Passed: {test_results.get('passed', False)}
Output: {test_results.get('output', 'No tests run')[:1000]}
Errors: {json.dumps(test_results.get('errors', []), ensure_ascii=False)}

Please evaluate the results from a product manager's perspective and provide your assessment in JSON format:
{{
    "passed": true/false,
    "score": 0-100,
    "metrics": [
        {{
            "name": "metric name",
            "score": 0-100,
            "weight": 0.0-1.0,
            "explanation": "why this score was given"
        }}
    ],
    "feedback": "detailed feedback for improvement",
    "summary": "short summary of the iteration result",
    "issues": ["issue1", "issue2", ...],
    "suggestions": ["suggestion1", "suggestion2", ...],
    "stop_recommendation": "continue" | "success" | "abort"
}}

The evaluation should consider:
1. Does the code achieve the user's goal?
2. Are the planned actions meaningful and correctly executed?
3. Are all required artifacts created?
4. Are there any failed observations or blocked steps?
5. Do the tests pass (if any)?
6. Apply the Judge Skill rubric and required checks strictly.
"""
        return self.execute(
            prompt,
            action_output=action_output,
            plan_data=plan_data,
            actions=actions,
            observations=observations,
            test_results=test_results,
            files_modified=files_modified,
            files_to_create=files_to_create or [],
            judge_skill=judge_skill.name,
            pass_threshold=judge_skill.pass_threshold,
        )

    def evaluate_with_feedback(
        self,
        user_goal: str,
        action_output: str,
        test_results: dict[str, Any],
        plan_data: dict[str, Any],
        actions: list[dict[str, Any]],
        observations: list[dict[str, Any]],
        files_modified: list[str],
        files_to_create: list[str] | None = None,
        iteration: int = 0,
        judge_skill_name: str | None = None,
        task_type: str = "",
    ) -> tuple[RoleOutput, FeedbackArtifact]:
        """Evaluate and return structured FeedbackArtifact.

        Returns both RoleOutput (for backward compat) and new FeedbackArtifact.
        """
        # Run standard evaluation
        role_output = self.evaluate(
            user_goal=user_goal,
            action_output=action_output,
            test_results=test_results,
            plan_data=plan_data,
            actions=actions,
            observations=observations,
            files_modified=files_modified,
            files_to_create=files_to_create,
            judge_skill_name=judge_skill_name,
            task_type=task_type,
        )

        # Parse JSON from content
        metadata = role_output.metadata.get("evaluation", {})

        # Build structured feedback
        passed = metadata.get("passed", False)
        score = metadata.get("score", 0)
        feedback_text = metadata.get("feedback", "")
        issues = metadata.get("issues", [])
        fix_actions = self._build_fix_actions(issues, files_modified)
        metrics = self._build_metrics(metadata.get("metrics", []))

        artifact = FeedbackArtifact(
            passed=passed,
            score=score,
            summary=feedback_text,
            metrics=metrics,
            fix_actions=fix_actions,
            iteration=iteration,
            raw_evaluation=metadata,
        )

        return role_output, artifact
