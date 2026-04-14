"""OpenAI-compatible LLM client."""

import os
from typing import Any, Optional
import json
import urllib.error
import urllib.request

try:
    import httpx
except ModuleNotFoundError:  # pragma: no cover - optional dependency.
    httpx = None


class LLMClient:
    """OpenAI-compatible LLM client for chat completions."""

    def __init__(
        self,
        model: str,
        base_url: str = "https://api.openai.com/v1",
        api_key: Optional[str] = None,
        timeout: float = 120.0,
        max_retries: int = 3,
    ):
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key or os.getenv("OPENAI_API_KEY", "")
        self.timeout = timeout
        self.max_retries = max_retries
        self._client = httpx.Client(timeout=timeout) if httpx is not None else None

    def chat(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        **kwargs: Any,
    ) -> str:
        """Send a chat completion request."""
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }

        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
        }

        if max_tokens:
            payload["max_tokens"] = max_tokens

        payload.update(kwargs)

        url = f"{self.base_url}/chat/completions"

        last_error: Optional[Exception] = None
        for attempt in range(self.max_retries):
            try:
                if self._client is not None:
                    response = self._client.post(url, headers=headers, json=payload)
                    response.raise_for_status()
                    data = response.json()
                else:
                    request = urllib.request.Request(
                        url,
                        data=json.dumps(payload).encode("utf-8"),
                        headers=headers,
                        method="POST",
                    )
                    with urllib.request.urlopen(request, timeout=self.timeout) as response:
                        data = json.loads(response.read().decode("utf-8"))
                return data["choices"][0]["message"]["content"]
            except Exception as e:
                last_error = e
                if attempt < self.max_retries - 1:
                    continue

        raise RuntimeError(f"LLM request failed after {self.max_retries} retries: {last_error}")

    def close(self) -> None:
        """Close the HTTP client."""
        if self._client is not None:
            self._client.close()

    def __enter__(self) -> "LLMClient":
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()
