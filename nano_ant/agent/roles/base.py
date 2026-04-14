"""Base role class for all agent roles."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any
from dataclasses import dataclass, field
import json
import time

from ...llm.client import LLMClient


@dataclass
class RoleOutput:
    """Output from a role execution."""

    success: bool
    content: str
    metadata: dict[str, Any] = field(default_factory=dict)
    error: str | None = None
    timestamp: float = field(default_factory=time.time)


class BaseRole(ABC):
    """Abstract base class for all agent roles."""

    def __init__(
        self,
        name: str,
        llm_client: LLMClient,
        system_prompt: str,
        max_retries: int = 2,
    ):
        self.name = name
        self.llm = llm_client
        self.system_prompt = system_prompt
        self.max_retries = max_retries
        self._history: list[dict[str, str]] = []

    def _build_messages(self, user_input: str, context: str | None = None) -> list[dict[str, str]]:
        """Build message list for LLM call."""
        messages = [{"role": "system", "content": self.system_prompt}]

        if context:
            messages.append({"role": "user", "content": f"[Context]\n{context}"})

        messages.append({"role": "user", "content": user_input})

        for hist in self._history[-6:]:
            messages.append(hist)

        return messages

    def _add_to_history(self, role: str, content: str) -> None:
        """Add a message to conversation history."""
        self._history.append({"role": role, "content": content})
        if len(self._history) > 20:
            self._history = self._history[-20:]

    def clear_history(self) -> None:
        """Clear conversation history."""
        self._history = []

    def _is_empty_response(self, response: str) -> bool:
        """Check if the response is effectively empty."""
        if not response or not response.strip():
            return True
        # Check if response only contains whitespace or common filler words
        stripped = response.strip().lower()
        if stripped in ["ok", "okay", "sure", "yes", "no", "done"]:
            return True
        return False

    def _extract_json_object(self, response: str) -> dict[str, Any]:
        """Extract the first JSON object from a response."""
        if not response or not response.strip():
            return {}

        if "```json" in response:
            json_start = response.find("```json") + 7
            json_end = response.find("```", json_start)
            json_str = response[json_start:json_end].strip()
        elif "{" in response and "}" in response:
            json_start = response.find("{")
            json_end = response.rfind("}") + 1
            json_str = response[json_start:json_end]
        else:
            return {}

        try:
            data = json.loads(json_str)
        except json.JSONDecodeError:
            return {}

        return data if isinstance(data, dict) else {}

    def execute(
        self,
        user_input: str,
        context: str | None = None,
        **kwargs: Any,
    ) -> RoleOutput:
        """Execute the role with retry logic and empty response handling."""
        messages = self._build_messages(user_input, context)

        last_error: str | None = None
        empty_response_count = 0
        max_empty_retries = 2

        for attempt in range(self.max_retries + max_empty_retries):
            try:
                response = self.llm.chat(messages, **kwargs)

                # Check for empty response and retry
                if self._is_empty_response(response):
                    empty_response_count += 1
                    if empty_response_count <= max_empty_retries:
                        # Add a follow-up prompt to encourage meaningful response
                        messages.append({"role": "assistant", "content": response})
                        messages.append({"role": "user", "content": "Please provide a complete response. Do not leave this empty."})
                        continue
                    # If we've retried enough, proceed with empty response

                self._add_to_history("user", user_input)
                self._add_to_history("assistant", response)

                return self._process_response(response, **kwargs)
            except Exception as e:
                last_error = str(e)
                continue

        return RoleOutput(
            success=False,
            content="",
            error=f"Role {self.name} failed after {self.max_retries} retries: {last_error}",
        )

    @abstractmethod
    def _process_response(self, response: str, **kwargs: Any) -> RoleOutput:
        """Process the LLM response and return structured output."""
        pass
