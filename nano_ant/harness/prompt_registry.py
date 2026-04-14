"""Prompt engineering with version control and performance tracking.

This module treats prompts as versioned artifacts with performance metrics,
enabling A/B testing and data-driven prompt optimization.
"""

import hashlib
import json
import os
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass
class PromptMetrics:
    """Performance metrics for a prompt version."""
    uses: int = 0
    successes: int = 0
    total_score: int = 0
    avg_score: float = 0.0
    avg_latency_ms: float = 0.0

    def record_outcome(self, success: bool, score: int, latency_ms: float = 0):
        """Record an outcome for this prompt."""
        self.uses += 1
        if success:
            self.successes += 1
        self.total_score += score
        self.avg_score = self.total_score / self.uses
        # Exponential moving average for latency
        if self.avg_latency_ms == 0:
            self.avg_latency_ms = latency_ms
        else:
            self.avg_latency_ms = 0.9 * self.avg_latency_ms + 0.1 * latency_ms

    def success_rate(self) -> float:
        """Calculate success rate."""
        if self.uses == 0:
            return 0.0
        return self.successes / self.uses


@dataclass
class PromptVersion:
    """A versioned prompt with metadata."""
    name: str
    version: str
    content: str
    role: str
    created_at: datetime = field(default_factory=datetime.now)
    metrics: PromptMetrics = field(default_factory=PromptMetrics)
    parent_version: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def content_hash(self) -> str:
        """Get hash of prompt content."""
        return hashlib.sha256(self.content.encode()).hexdigest()[:16]

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "name": self.name,
            "version": self.version,
            "content": self.content,
            "role": self.role,
            "created_at": self.created_at.isoformat(),
            "metrics": {
                "uses": self.metrics.uses,
                "successes": self.metrics.successes,
                "avg_score": self.metrics.avg_score,
                "success_rate": self.metrics.success_rate(),
            },
            "content_hash": self.content_hash,
            "parent_version": self.parent_version,
            "metadata": self.metadata,
        }


class PromptRegistry:
    """Registry for versioned prompts with performance tracking.

    This enables:
    - Version control for prompts
    - A/B testing between prompt versions
    - Performance-based prompt selection
    - Data-driven prompt optimization

    Usage:
        registry = PromptRegistry(registry_path="./prompts")

        # Register a new prompt version
        registry.register(PromptVersion(
            name="coding_v2",
            version="2.1.0",
            content="You are a coding assistant...",
            role="coding",
        ))

        # Select best performing prompt
        prompt = registry.select("coding", context)

        # Record outcome
        registry.record_outcome("coding_v2", "2.1.0", success=True, score=95)
    """

    def __init__(self, registry_path: Optional[str] = None):
        self.registry_path = registry_path or "./prompt_registry"
        self._prompts: Dict[str, Dict[str, PromptVersion]] = {}
        self._role_index: Dict[str, List[str]] = {}
        self._load_registry()

    def _load_registry(self) -> None:
        """Load existing registry from disk."""
        if not os.path.exists(self.registry_path):
            return

        registry_file = os.path.join(self.registry_path, "registry.json")
        if not os.path.exists(registry_file):
            return

        try:
            with open(registry_file, "r") as f:
                data = json.load(f)

            for prompt_data in data.get("prompts", []):
                version = PromptVersion(
                    name=prompt_data["name"],
                    version=prompt_data["version"],
                    content=prompt_data["content"],
                    role=prompt_data["role"],
                    created_at=datetime.fromisoformat(prompt_data["created_at"]),
                    parent_version=prompt_data.get("parent_version"),
                    metadata=prompt_data.get("metadata", {}),
                )
                # Restore metrics
                metrics_data = prompt_data.get("metrics", {})
                version.metrics.uses = metrics_data.get("uses", 0)
                version.metrics.successes = metrics_data.get("successes", 0)
                version.metrics.total_score = metrics_data.get("total_score", 0)
                version.metrics.avg_score = metrics_data.get("avg_score", 0.0)

                self._add_to_index(version)

        except Exception as e:
            print(f"Warning: Failed to load prompt registry: {e}")

    def _save_registry(self) -> None:
        """Save registry to disk."""
        os.makedirs(self.registry_path, exist_ok=True)

        data = {
            "prompts": [
                v.to_dict()
                for versions in self._prompts.values()
                for v in versions.values()
            ]
        }

        registry_file = os.path.join(self.registry_path, "registry.json")
        with open(registry_file, "w") as f:
            json.dump(data, f, indent=2)

    def _add_to_index(self, version: PromptVersion) -> None:
        """Add a prompt version to indexes."""
        if version.name not in self._prompts:
            self._prompts[version.name] = {}
        self._prompts[version.name][version.version] = version

        if version.role not in self._role_index:
            self._role_index[version.role] = []
        if version.name not in self._role_index[version.role]:
            self._role_index[version.role].append(version.name)

    def register(self, version: PromptVersion) -> None:
        """Register a new prompt version."""
        self._add_to_index(version)
        self._save_registry()

    def get(self, name: str, version: Optional[str] = None) -> Optional[PromptVersion]:
        """Get a prompt version.

        If version is None, returns the latest version.
        """
        if name not in self._prompts:
            return None

        versions = self._prompts[name]

        if version is None:
            # Return latest version
            return max(versions.values(), key=lambda v: v.created_at)

        return versions.get(version)

    def list_versions(self, name: str) -> List[str]:
        """List all versions for a prompt."""
        if name not in self._prompts:
            return []
        return sorted(self._prompts[name].keys())

    def list_by_role(self, role: str) -> List[str]:
        """List all prompts for a role."""
        return self._role_index.get(role, [])

    def select(self, role: str, strategy: str = "best") -> Optional[PromptVersion]:
        """Select the best prompt for a role.

        Strategies:
            best: Select highest success rate (with minimum uses)
            latest: Select most recent version
            ucb: Upper Confidence Bound (exploration/exploitation)
        """
        prompt_names = self._role_index.get(role, [])
        if not prompt_names:
            return None

        candidates = []
        for name in prompt_names:
            version = self.get(name)
            if version:
                candidates.append(version)

        if not candidates:
            return None

        if strategy == "latest":
            return max(candidates, key=lambda v: v.created_at)

        if strategy == "best":
            # Filter for minimum usage to avoid lucky shots
            experienced = [v for v in candidates if v.metrics.uses >= 3]
            if experienced:
                return max(experienced, key=lambda v: v.metrics.success_rate())
            return max(candidates, key=lambda v: v.metrics.success_rate())

        if strategy == "ucb":
            return self._ucb_select(candidates)

        return candidates[0]

    def _ucb_select(self, candidates: List[PromptVersion]) -> PromptVersion:
        """Select using Upper Confidence Bound algorithm."""
        total_uses = sum(v.metrics.uses for v in candidates)

        if total_uses == 0:
            return candidates[0]

        best_score = -1.0
        best_candidate = candidates[0]

        for v in candidates:
            if v.metrics.uses == 0:
                # Always try unused prompts
                return v

            avg_reward = v.metrics.success_rate()
            exploration = (2 * (total_uses ** 0.5) / v.metrics.uses) ** 0.5
            ucb_score = avg_reward + exploration

            if ucb_score > best_score:
                best_score = ucb_score
                best_candidate = v

        return best_candidate

    def record_outcome(
        self,
        name: str,
        version: str,
        success: bool,
        score: int,
        latency_ms: float = 0,
    ) -> None:
        """Record the outcome of using a prompt."""
        prompt = self.get(name, version)
        if prompt:
            prompt.metrics.record_outcome(success, score, latency_ms)
            self._save_registry()

    def compare_versions(self, name: str, version_a: str, version_b: str) -> Dict[str, Any]:
        """Compare two versions of a prompt."""
        a = self.get(name, version_a)
        b = self.get(name, version_b)

        if not a or not b:
            return {"error": "One or both versions not found"}

        return {
            "version_a": version_a,
            "version_b": version_b,
            "uses_a": a.metrics.uses,
            "uses_b": b.metrics.uses,
            "success_rate_a": a.metrics.success_rate(),
            "success_rate_b": b.metrics.success_rate(),
            "avg_score_a": a.metrics.avg_score,
            "avg_score_b": b.metrics.avg_score,
            "winner": version_a if a.metrics.success_rate() > b.metrics.success_rate() else version_b,
        }

    def fork_version(
        self,
        name: str,
        base_version: str,
        new_version: str,
        content: str,
        metadata: Optional[Dict] = None,
    ) -> Optional[PromptVersion]:
        """Create a new version based on an existing one."""
        base = self.get(name, base_version)
        if not base:
            return None

        new_prompt = PromptVersion(
            name=name,
            version=new_version,
            content=content,
            role=base.role,
            parent_version=base_version,
            metadata=metadata or {},
        )

        self.register(new_prompt)
        return new_prompt

    def get_stats(self) -> Dict[str, Any]:
        """Get overall registry statistics."""
        total_prompts = len(self._prompts)
        total_versions = sum(len(vs) for vs in self._prompts.values())

        total_uses = sum(
            v.metrics.uses
            for versions in self._prompts.values()
            for v in versions.values()
        )

        total_successes = sum(
            v.metrics.successes
            for versions in self._prompts.values()
            for v in versions.values()
        )

        return {
            "total_prompts": total_prompts,
            "total_versions": total_versions,
            "total_uses": total_uses,
            "total_successes": total_successes,
            "overall_success_rate": total_successes / total_uses if total_uses > 0 else 0,
        }
