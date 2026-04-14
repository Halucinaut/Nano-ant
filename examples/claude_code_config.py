"""Example configuration for using Claude Code as LLM backend.

This shows how to configure Nano Ant to use Claude Code CLI
instead of HTTP API for LLM calls.
"""

# Example 1: Use Claude Code CLI for all roles
CLAUDE_CODE_CONFIG = {
    "llm": {
        "backend": "claude_code",  # Use Claude Code CLI
        "claude_code_path": "claude",  # Path to claude command
    },
    "agent": {
        "max_iterations": 10,
        "early_stop_rounds": 3,
    },
    "workspace": {
        "path": "./workspace",
        "sandbox_enabled": True,
    },
    "checkpoint": {
        "enabled": True,
        "path": "./checkpoints",
    },
}

# Example 2: Use Hybrid mode (Claude Code primary, HTTP fallback)
HYBRID_CONFIG = {
    "llm": {
        "backend": "hybrid",
        "hybrid_primary": "claude_code",  # Try Claude Code first
        # HTTP fallback configuration
        "model": "gpt-4",
        "base_url": "https://api.openai.com/v1",
        "api_key": "${OPENAI_API_KEY}",  # Will be resolved from env
    },
    "agent": {
        "max_iterations": 10,
    },
}

# Example 3: Original HTTP API mode (for comparison)
HTTP_API_CONFIG = {
    "llm": {
        "backend": "http",  # Use HTTP API (default)
        "default": {
            "model": "gpt-4",
            "base_url": "https://api.openai.com/v1",
            "api_key": "${OPENAI_API_KEY}",
        },
        "roles": {
            "plan": {
                "model": "gpt-4",  # Can override per role
            },
            "coding": {
                "model": "gpt-4",
            },
        },
    },
}

# Example 4: Full configuration with all Harness features
FULL_HARNESS_CONFIG = {
    "llm": {
        "backend": "claude_code",
        "claude_code_path": "claude",
    },
    "agent": {
        "max_iterations": 10,
        "early_stop_rounds": 3,
        "retry_per_role": 2,
        "coding_tool": "llm",
    },
    "workspace": {
        "path": "./workspace",
        "sandbox_enabled": True,
    },
    "checkpoint": {
        "enabled": True,
        "path": "./checkpoints",
    },
    "logging": {
        "level": "info",
        "progress_report": True,
    },
    "harness": {
        "enabled": True,
        "use_workflow_sm": True,  # Use declarative state machine
        "use_sandbox_pool": True,  # Pre-warmed sandboxes
        "sandbox_pool_size": 2,
        "use_structured_feedback": True,  # Structured feedback artifacts
        "telemetry_enabled": True,  # Real-time monitoring
        "short_circuit_threshold": 3,  # Auto-stop after 3 failures
    },
}


def create_orchestrator(config_type: str = "claude_code"):
    """Create an orchestrator with the specified configuration."""
    from nano_ant.agent.orchestrator import Orchestrator, AgentConfig

    configs = {
        "claude_code": CLAUDE_CODE_CONFIG,
        "hybrid": HYBRID_CONFIG,
        "http": HTTP_API_CONFIG,
        "full": FULL_HARNESS_CONFIG,
    }

    config_dict = configs.get(config_type, CLAUDE_CODE_CONFIG)

    # Create orchestrator
    orchestrator = Orchestrator.from_config_dict(config_dict)

    return orchestrator


if __name__ == "__main__":
    # Test creating orchestrators with different configs
    print("Testing Claude Code config...")
    orch = create_orchestrator("claude_code")
    print(f"  LLM Backend: {orch.config.llm_backend}")
    print(f"  Claude Code Path: {orch.config.claude_code_path}")

    print("\nTesting Hybrid config...")
    orch = create_orchestrator("hybrid")
    print(f"  LLM Backend: {orch.config.llm_backend}")
    print(f"  Hybrid Primary: {orch.config.hybrid_primary}")

    print("\nAll configurations work!")
