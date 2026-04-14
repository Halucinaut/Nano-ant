"""Checkpoint manager for saving and loading agent state."""

from __future__ import annotations

import json
import os
import shutil
from typing import Any
from datetime import datetime


class CheckpointManager:
    """Manages checkpoints for the agent."""

    def __init__(self, checkpoint_path: str, enabled: bool = True):
        self.checkpoint_path = checkpoint_path
        self.enabled = enabled
        self._ensure_directory()

    def _ensure_directory(self) -> None:
        """Ensure checkpoint directory exists."""
        if self.enabled:
            os.makedirs(self.checkpoint_path, exist_ok=True)

    def save(
        self,
        iteration: int,
        context_data: dict[str, Any],
        code_files: dict[str, str] | None = None,
    ) -> str:
        """Save a checkpoint for the given iteration."""
        if not self.enabled:
            return ""

        iter_path = os.path.join(self.checkpoint_path, f"iter_{iteration:03d}")
        os.makedirs(iter_path, exist_ok=True)

        state_path = os.path.join(iter_path, "state.json")
        with open(state_path, "w", encoding="utf-8") as f:
            json.dump(context_data, f, ensure_ascii=False, indent=2)

        if code_files:
            code_path = os.path.join(iter_path, "code")
            os.makedirs(code_path, exist_ok=True)
            for filename, content in code_files.items():
                file_path = os.path.join(code_path, filename)
                os.makedirs(os.path.dirname(file_path), exist_ok=True)
                with open(file_path, "w", encoding="utf-8") as f:
                    f.write(content)

        meta_path = os.path.join(iter_path, "meta.json")
        meta = {
            "iteration": iteration,
            "timestamp": datetime.now().isoformat(),
            "checkpoint_path": iter_path,
        }
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False, indent=2)

        return iter_path

    def save_best(self, iteration: int) -> str:
        """Copy the best iteration to 'best' folder."""
        if not self.enabled:
            return ""

        best_path = os.path.join(self.checkpoint_path, "best")
        iter_path = os.path.join(self.checkpoint_path, f"iter_{iteration:03d}")

        if os.path.exists(best_path):
            shutil.rmtree(best_path)

        if os.path.exists(iter_path):
            shutil.copytree(iter_path, best_path)
            return best_path

        return ""

    def load(self, iteration: int | None = None) -> dict[str, Any] | None:
        """Load a checkpoint. If iteration is None, load the latest."""
        if not self.enabled:
            return None

        if iteration is not None:
            iter_path = os.path.join(self.checkpoint_path, f"iter_{iteration:03d}")
        else:
            iterations = self.list_iterations()
            if not iterations:
                return None
            iter_path = os.path.join(self.checkpoint_path, f"iter_{max(iterations):03d}")

        state_path = os.path.join(iter_path, "state.json")
        if not os.path.exists(state_path):
            return None

        with open(state_path, "r", encoding="utf-8") as f:
            return json.load(f)

    def load_best(self) -> dict[str, Any] | None:
        """Load the best checkpoint."""
        if not self.enabled:
            return None

        best_path = os.path.join(self.checkpoint_path, "best")
        state_path = os.path.join(best_path, "state.json")

        if not os.path.exists(state_path):
            return None

        with open(state_path, "r", encoding="utf-8") as f:
            return json.load(f)

    def list_iterations(self) -> list[int]:
        """List all available iteration numbers."""
        if not self.enabled or not os.path.exists(self.checkpoint_path):
            return []

        iterations = []
        for name in os.listdir(self.checkpoint_path):
            if name.startswith("iter_"):
                try:
                    iter_num = int(name.split("_")[1])
                    iterations.append(iter_num)
                except (IndexError, ValueError):
                    continue

        return sorted(iterations)

    def get_latest_iteration(self) -> int | None:
        """Get the latest iteration number."""
        iterations = self.list_iterations()
        return max(iterations) if iterations else None

    def get_checkpoint_path(self, iteration: int | None = None) -> str:
        """Get the path to a specific checkpoint or the best one."""
        if iteration is not None:
            return os.path.join(self.checkpoint_path, f"iter_{iteration:03d}")
        return os.path.join(self.checkpoint_path, "best")

    def cleanup_old_checkpoints(self, keep_last: int = 10) -> None:
        """Remove old checkpoints, keeping only the last N."""
        if not self.enabled:
            return

        iterations = self.list_iterations()
        if len(iterations) <= keep_last:
            return

        to_remove = iterations[:-keep_last]
        for iter_num in to_remove:
            iter_path = os.path.join(self.checkpoint_path, f"iter_{iter_num:03d}")
            if os.path.exists(iter_path):
                shutil.rmtree(iter_path)
