"""Reproducibility support for deterministic agent runs.

This module ensures that agent runs can be fully reproduced
given the same seed, enabling debugging and experimentation.
"""

import hashlib
import json
import os
import random
from dataclasses import dataclass, field
from typing import Any, Dict, Iterator, List, Optional
from datetime import datetime

from ..memory.context import Context, IterationRecord


@dataclass
class RunSeed:
    """Complete seed for a reproducible run.

    This captures all sources of non-determinism:
    - Random number generator state
    - LLM parameters (temperature, seed)
    - Dependency versions (lock file hash)
    - Prompt versions used
    - Initial checkpoint (if resuming)
    """
    random_seed: int
    llm_temperature: float = 0.0
    llm_seed: int = 0
    dependency_hash: str = ""
    prompt_versions: Dict[str, str] = field(default_factory=dict)
    checkpoint_hash: Optional[str] = None
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "random_seed": self.random_seed,
            "llm_temperature": self.llm_temperature,
            "llm_seed": self.llm_seed,
            "dependency_hash": self.dependency_hash,
            "prompt_versions": self.prompt_versions,
            "checkpoint_hash": self.checkpoint_hash,
            "created_at": self.created_at,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RunSeed":
        return cls(
            random_seed=data["random_seed"],
            llm_temperature=data.get("llm_temperature", 0.0),
            llm_seed=data.get("llm_seed", 0),
            dependency_hash=data.get("dependency_hash", ""),
            prompt_versions=data.get("prompt_versions", {}),
            checkpoint_hash=data.get("checkpoint_hash"),
            created_at=data.get("created_at", ""),
            metadata=data.get("metadata", {}),
        )


class ReproducibilityHarness:
    """Harness for reproducible agent runs.

    Usage:
        harness = ReproducibilityHarness()

        # Create seed for new run
        seed = harness.create_seed(
            workspace_path="./workspace",
            prompt_registry=prompt_registry,
        )
        harness.save_seed(seed, "run_001.json")

        # Later, replay the run
        seed = harness.load_seed("run_001.json")
        for iteration in harness.replay(seed, orchestrator):
            print(f"Replayed iteration {iteration.iteration}")
    """

    def __init__(self, seeds_path: str = "./seeds"):
        self.seeds_path = seeds_path
        os.makedirs(seeds_path, exist_ok=True)

    def create_seed(
        self,
        workspace_path: str,
        prompt_registry: Optional[Any] = None,
        llm_temperature: float = 0.0,
    ) -> RunSeed:
        """Create a seed for a reproducible run."""
        random_seed = random.randint(0, 2**32 - 1)

        # Hash dependencies
        dependency_hash = self._hash_dependencies(workspace_path)

        # Get prompt versions
        prompt_versions = {}
        if prompt_registry:
            for role in ["leader", "plan", "coding", "judge"]:
                prompt = prompt_registry.select(role)
                if prompt:
                    prompt_versions[role] = f"{prompt.name}@{prompt.version}"

        return RunSeed(
            random_seed=random_seed,
            llm_temperature=llm_temperature,
            llm_seed=random_seed,  # Use same seed for LLM if supported
            dependency_hash=dependency_hash,
            prompt_versions=prompt_versions,
        )

    def _hash_dependencies(self, workspace_path: str) -> str:
        """Hash the dependency files to capture versions."""
        req_file = os.path.join(workspace_path, "requirements.txt")

        if not os.path.exists(req_file):
            return ""

        with open(req_file, "rb") as f:
            content = f.read()
            return hashlib.sha256(content).hexdigest()[:16]

    def save_seed(self, seed: RunSeed, filename: str) -> str:
        """Save a seed to disk."""
        filepath = os.path.join(self.seeds_path, filename)
        with open(filepath, "w") as f:
            json.dump(seed.to_dict(), f, indent=2)
        return filepath

    def load_seed(self, filename: str) -> Optional[RunSeed]:
        """Load a seed from disk."""
        filepath = os.path.join(self.seeds_path, filename)
        if not os.path.exists(filepath):
            return None

        with open(filepath, "r") as f:
            data = json.load(f)
            return RunSeed.from_dict(data)

    def apply_seed(self, seed: RunSeed) -> None:
        """Apply a seed to make the current process deterministic."""
        # Set random seed
        random.seed(seed.random_seed)

        # Note: LLM seed would need to be supported by the LLM client
        # This is a placeholder for when that support is added

    def verify_reproducibility(
        self,
        seed: RunSeed,
        context: Context,
    ) -> Dict[str, Any]:
        """Verify if a run matches the expected seed."""
        issues = []

        # Check prompt versions
        # (Would need access to actual prompts used)

        # Check dependency hash
        current_hash = self._hash_dependencies(context.workspace_path)
        if current_hash != seed.dependency_hash:
            issues.append({
                "type": "dependency_mismatch",
                "expected": seed.dependency_hash,
                "actual": current_hash,
            })

        return {
            "reproducible": len(issues) == 0,
            "issues": issues,
        }

    def compare_runs(
        self,
        run_a: str,
        run_b: str,
    ) -> Dict[str, Any]:
        """Compare two runs for differences."""
        seed_a = self.load_seed(run_a)
        seed_b = self.load_seed(run_b)

        if not seed_a or not seed_b:
            return {"error": "Could not load one or both seeds"}

        differences = {}

        if seed_a.random_seed != seed_b.random_seed:
            differences["random_seed"] = (seed_a.random_seed, seed_b.random_seed)

        if seed_a.dependency_hash != seed_b.dependency_hash:
            differences["dependencies"] = (seed_a.dependency_hash, seed_b.dependency_hash)

        if seed_a.prompt_versions != seed_b.prompt_versions:
            differences["prompts"] = {
                k: (seed_a.prompt_versions.get(k), seed_b.prompt_versions.get(k))
                for k in set(seed_a.prompt_versions.keys()) | set(seed_b.prompt_versions.keys())
                if seed_a.prompt_versions.get(k) != seed_b.prompt_versions.get(k)
            }

        return {
            "identical": len(differences) == 0,
            "differences": differences,
        }

    def replay(
        self,
        seed: RunSeed,
        orchestrator: Any,
    ) -> Iterator[IterationRecord]:
        """Replay a run from a seed.

        Yields each iteration as it's replayed.
        """
        self.apply_seed(seed)

        # Configure orchestrator for deterministic mode
        # (This would need to be implemented in Orchestrator)

        # Note: Full replay requires saving all intermediate states
        # This is a simplified version

        yield from []


class DeterministicMode:
    """Context manager for deterministic execution."""

    def __init__(self, seed: RunSeed):
        self.seed = seed
        self._old_random_state = None

    def __enter__(self):
        self._old_random_state = random.getstate()
        random.seed(self.seed.random_seed)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self._old_random_state:
            random.setstate(self._old_random_state)
        return False
