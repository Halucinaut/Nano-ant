"""Sandbox executor for running code safely."""

from __future__ import annotations

import os
import subprocess
import tempfile
import shutil
import venv
from typing import Any
from dataclasses import dataclass


@dataclass
class ExecutionResult:
    """Result of a sandbox execution."""

    success: bool
    stdout: str
    stderr: str
    return_code: int
    files_created: list[str]
    files_modified: list[str]


class SandboxExecutor:
    """Executes code in a sandboxed environment."""

    FORBIDDEN_IMPORTS = {
        "os.system",
        "subprocess.call",
        "subprocess.run",
        "subprocess.Popen",
        "eval",
        "exec",
        "compile",
        "__import__",
        "importlib",
        "shutil.rmtree",
    }

    def __init__(
        self,
        workspace_path: str,
        timeout: int = 60,
        max_output_size: int = 10000,
    ):
        self.workspace_path = workspace_path
        self.timeout = timeout
        self.max_output_size = max_output_size
        self._venv_path: str | None = None
        self._installed_packages: set[str] = set()

    def _create_venv(self) -> str:
        """Create a virtual environment for isolation."""
        if self._venv_path and os.path.exists(self._venv_path):
            return self._venv_path

        self._venv_path = os.path.join(self.workspace_path, ".nano_ant_venv")
        venv.create(self._venv_path, with_pip=True)
        return self._venv_path

    def _get_python_path(self) -> str:
        """Get the Python executable path in the venv."""
        if not self._venv_path:
            self._create_venv()

        if os.name == "nt":
            return os.path.join(self._venv_path, "Scripts", "python.exe")
        return os.path.join(self._venv_path, "bin", "python")

    def _get_pip_path(self) -> str:
        """Get the pip executable path in the venv."""
        if not self._venv_path:
            self._create_venv()

        if os.name == "nt":
            return os.path.join(self._venv_path, "Scripts", "pip.exe")
        return os.path.join(self._venv_path, "bin", "pip")

    def install_package(self, package: str) -> tuple[bool, str]:
        """Install a package in the sandbox environment."""
        if package in self._installed_packages:
            return True, f"Package {package} already installed"

        pip_path = self._get_pip_path()

        try:
            result = subprocess.run(
                [pip_path, "install", package],
                capture_output=True,
                text=True,
                timeout=120,
            )

            if result.returncode == 0:
                self._installed_packages.add(package)
                return True, result.stdout
            else:
                return False, result.stderr

        except subprocess.TimeoutExpired:
            return False, f"Installation of {package} timed out"
        except Exception as e:
            return False, str(e)

    def install_requirements(self, requirements: list[str]) -> dict[str, tuple[bool, str]]:
        """Install multiple packages."""
        results = {}
        for package in requirements:
            success, output = self.install_package(package)
            results[package] = (success, output)
        return results

    def _scan_for_dangerous_code(self, code: str) -> list[str]:
        """Scan code for potentially dangerous patterns."""
        warnings = []
        code_lower = code.lower()

        for pattern in self.FORBIDDEN_IMPORTS:
            if pattern.lower() in code_lower:
                warnings.append(f"Potentially dangerous pattern found: {pattern}")

        return warnings

    def run_python_file(self, filepath: str, args: list[str] | None = None) -> ExecutionResult:
        """Run a Python file in the sandbox."""
        python_path = self._get_python_path()
        full_path = os.path.join(self.workspace_path, filepath)

        if not os.path.exists(full_path):
            return ExecutionResult(
                success=False,
                stdout="",
                stderr=f"File not found: {filepath}",
                return_code=1,
                files_created=[],
                files_modified=[],
            )

        with open(full_path, "r", encoding="utf-8") as f:
            code = f.read()

        warnings = self._scan_for_dangerous_code(code)

        cmd = [python_path, full_path]
        if args:
            cmd.extend(args)

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=self.timeout,
                cwd=self.workspace_path,
            )

            stdout = result.stdout[:self.max_output_size]
            stderr = result.stderr[:self.max_output_size]

            if warnings:
                stderr = "Warnings:\n" + "\n".join(warnings) + "\n\n" + stderr

            return ExecutionResult(
                success=result.returncode == 0,
                stdout=stdout,
                stderr=stderr,
                return_code=result.returncode,
                files_created=[],
                files_modified=[filepath],
            )

        except subprocess.TimeoutExpired:
            return ExecutionResult(
                success=False,
                stdout="",
                stderr=f"Execution timed out after {self.timeout} seconds",
                return_code=-1,
                files_created=[],
                files_modified=[],
            )
        except Exception as e:
            return ExecutionResult(
                success=False,
                stdout="",
                stderr=str(e),
                return_code=-1,
                files_created=[],
                files_modified=[],
            )

    def run_command(self, command: str, shell: bool = True) -> ExecutionResult:
        """Run a shell command in the sandbox."""
        try:
            result = subprocess.run(
                command,
                shell=shell,
                capture_output=True,
                text=True,
                timeout=self.timeout,
                cwd=self.workspace_path,
            )

            return ExecutionResult(
                success=result.returncode == 0,
                stdout=result.stdout[:self.max_output_size],
                stderr=result.stderr[:self.max_output_size],
                return_code=result.returncode,
                files_created=[],
                files_modified=[],
            )

        except subprocess.TimeoutExpired:
            return ExecutionResult(
                success=False,
                stdout="",
                stderr=f"Command timed out after {self.timeout} seconds",
                return_code=-1,
                files_created=[],
                files_modified=[],
            )
        except Exception as e:
            return ExecutionResult(
                success=False,
                stdout="",
                stderr=str(e),
                return_code=-1,
                files_created=[],
                files_modified=[],
            )

    def run_tests(self, test_command: str) -> ExecutionResult:
        """Run tests using the specified command."""
        return self.run_command(test_command)

    def cleanup(self) -> None:
        """Clean up the sandbox environment."""
        if self._venv_path and os.path.exists(self._venv_path):
            shutil.rmtree(self._venv_path)
            self._venv_path = None

    def __enter__(self) -> "SandboxExecutor":
        self._create_venv()
        return self

    def __exit__(self, *args: Any) -> None:
        pass
