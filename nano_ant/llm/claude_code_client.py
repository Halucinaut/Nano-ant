"""Claude Code CLI client for direct Claude Code integration.

This module provides a client that uses Claude Code CLI instead of
HTTP API calls to LLM providers.
"""

import os
import subprocess
import tempfile
import json
from typing import Any, Dict, List, Optional
from dataclasses import dataclass
from datetime import datetime


@dataclass
class ClaudeCodeResponse:
    """Response from Claude Code CLI."""
    content: str
    success: bool
    error: Optional[str] = None
    duration_ms: float = 0.0


class ClaudeCodeClient:
    """Client that uses Claude Code CLI for LLM calls.

    This provides the same interface as LLMClient but routes calls
    through Claude Code CLI instead of HTTP APIs.

    Usage:
        client = ClaudeCodeClient(
            claude_code_path="claude",
            timeout=120,
        )

        response = client.chat([
            {"role": "system", "content": "You are a helpful assistant"},
            {"role": "user", "content": "Hello!"},
        ])
    """

    def __init__(
        self,
        claude_code_path: str = "claude",
        timeout: float = 120.0,
        max_retries: int = 2,
        working_dir: Optional[str] = None,
    ):
        self.claude_code_path = claude_code_path
        self.timeout = timeout
        self.max_retries = max_retries
        self.working_dir = working_dir or os.getcwd()
        self._check_claude_code()

    def _check_claude_code(self) -> None:
        """Check if Claude Code CLI is available."""
        try:
            result = subprocess.run(
                [self.claude_code_path, "--version"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode != 0:
                raise RuntimeError(f"Claude Code CLI not found at {self.claude_code_path}")
        except FileNotFoundError:
            raise RuntimeError(
                f"Claude Code CLI not found at '{self.claude_code_path}'. "
                "Please install Claude Code CLI first."
            )

    def _messages_to_prompt(self, messages: List[Dict[str, str]]) -> str:
        """Convert message list to a single prompt string."""
        parts = []

        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")

            if role == "system":
                parts.append(f"<system>\n{content}\n</system>")
            elif role == "user":
                parts.append(f"<user>\n{content}\n</user>")
            elif role == "assistant":
                parts.append(f"<assistant>\n{content}\n</assistant>")
            else:
                parts.append(f"<{role}>\n{content}\n</{role}>")

        return "\n\n".join(parts)

    def _create_prompt_file(self, prompt: str) -> str:
        """Create a temporary file with the prompt."""
        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".txt",
            delete=False,
            prefix="nano_ant_prompt_",
        ) as f:
            f.write(prompt)
            return f.name

    def chat(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        **kwargs: Any,
    ) -> str:
        """Send a chat request via Claude Code CLI.

        This method provides the same interface as LLMClient.chat()
        for drop-in replacement.
        """
        import time

        prompt = self._messages_to_prompt(messages)

        # Build Claude Code command
        # We use a file-based approach to avoid command line length limits
        prompt_file = self._create_prompt_file(prompt)

        try:
            start_time = time.time()

            # Run Claude Code with the prompt
            cmd = [
                self.claude_code_path,
                "--dangerously-skip-permissions",
            ]

            # Add the prompt as an argument
            cmd.append(prompt)

            result = subprocess.run(
                cmd,
                cwd=self.working_dir,
                capture_output=True,
                text=True,
                timeout=self.timeout,
            )

            duration_ms = (time.time() - start_time) * 1000

            if result.returncode != 0:
                error_msg = result.stderr.strip() or "Claude Code execution failed"
                raise RuntimeError(f"Claude Code error: {error_msg}")

            # Extract response content
            content = result.stdout.strip()

            return content

        except subprocess.TimeoutExpired:
            raise RuntimeError(f"Claude Code execution timed out after {self.timeout}s")

        finally:
            # Clean up temp file
            try:
                os.unlink(prompt_file)
            except Exception:
                pass

    def chat_with_retry(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        **kwargs: Any,
    ) -> str:
        """Send a chat request with retry logic."""
        last_error: Optional[Exception] = None

        for attempt in range(self.max_retries + 1):
            try:
                return self.chat(messages, temperature, max_tokens, **kwargs)
            except Exception as e:
                last_error = e
                if attempt < self.max_retries:
                    import time
                    time.sleep(1 * (attempt + 1))  # Exponential backoff
                    continue

        raise RuntimeError(
            f"Claude Code request failed after {self.max_retries + 1} retries: {last_error}"
        )

    def close(self) -> None:
        """Close the client (no-op for CLI client)."""
        pass

    def __enter__(self):
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()


class HybridClient:
    """Client that can switch between HTTP API and Claude Code CLI.

    This is useful for gradually migrating from API-based to CLI-based calls.

    Usage:
        client = HybridClient(
            primary="claude_code",  # or "http"
            http_config={"model": "gpt-4", "api_key": "..."},
            claude_code_path="claude",
        )

        # Use same interface regardless of backend
        response = client.chat(messages)
    """

    def __init__(
        self,
        primary: str = "claude_code",  # "claude_code" or "http"
        http_config: Optional[Dict[str, Any]] = None,
        claude_code_path: str = "claude",
        working_dir: Optional[str] = None,
    ):
        self.primary = primary
        self._http_config = http_config or {}
        self._claude_code_path = claude_code_path
        self._working_dir = working_dir or os.getcwd()

        self._http_client: Optional[Any] = None
        self._cli_client: Optional[ClaudeCodeClient] = None

        self._init_clients()

    def _init_clients(self) -> None:
        """Initialize both clients."""
        # Always init HTTP client as fallback
        from .client import LLMClient

        self._http_client = LLMClient(
            model=self._http_config.get("model", "gpt-4"),
            base_url=self._http_config.get("base_url", "https://api.openai.com/v1"),
            api_key=self._http_config.get("api_key", ""),
        )

        # Init Claude Code client
        try:
            self._cli_client = ClaudeCodeClient(
                claude_code_path=self._claude_code_path,
                working_dir=self._working_dir,
            )
        except RuntimeError as e:
            print(f"Warning: Claude Code CLI not available: {e}")
            self._cli_client = None
            if self.primary == "claude_code":
                print("Falling back to HTTP API")
                self.primary = "http"

    def chat(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        **kwargs: Any,
    ) -> str:
        """Send a chat request using the configured primary client."""
        if self.primary == "claude_code" and self._cli_client:
            try:
                return self._cli_client.chat(messages, temperature, max_tokens, **kwargs)
            except Exception as e:
                print(f"Claude Code failed, falling back to HTTP: {e}")
                return self._http_client.chat(messages, temperature, max_tokens, **kwargs)
        else:
            return self._http_client.chat(messages, temperature, max_tokens, **kwargs)

    def close(self) -> None:
        """Close both clients."""
        if self._http_client:
            self._http_client.close()
        if self._cli_client:
            self._cli_client.close()

    def __enter__(self):
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()
