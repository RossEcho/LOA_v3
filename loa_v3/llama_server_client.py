from __future__ import annotations

import json
from typing import Any
import urllib.error
import urllib.request

from loa_v3.model_client import ModelClient, ModelClientError


class LlamaServerClient(ModelClient):
    def __init__(
        self,
        *,
        endpoint: str,
        model_name: str,
        timeout_sec: int,
        max_tokens: int,
        temperature: float,
        seed: int,
        use_schema: bool = False,
    ) -> None:
        self.endpoint = endpoint
        self.model_name = model_name
        self.timeout_sec = timeout_sec
        self.max_tokens = max_tokens
        self.temperature = temperature
        self.seed = seed
        self.use_schema = use_schema
        self._last_exchange: dict[str, Any] | None = None

    def get_last_exchange(self) -> dict[str, Any] | None:
        return self._last_exchange

    def generate_text(self, prompt: str, *, schema: dict[str, Any] | None = None) -> str:
        payload: dict[str, Any] = {
            "model": self.model_name,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": self.temperature,
            "seed": self.seed,
            "max_tokens": self.max_tokens,
            "stream": False,
        }

        if self.use_schema and schema is not None:
            payload["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "name": "loa_v3_response",
                    "schema": schema,
                },
            }

        self._last_exchange = {
            'endpoint': self.endpoint,
            'request_payload': payload,
            'prompt_preview': prompt[:4000],
            'schema': schema or {},
        }

        request = urllib.request.Request(
            self.endpoint,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            with urllib.request.urlopen(request, timeout=self.timeout_sec) as response:
                body = response.read().decode("utf-8", errors="replace")
                if self._last_exchange is not None:
                    self._last_exchange['http_status'] = getattr(response, 'status', None)
                    self._last_exchange['raw_response'] = body[:12000]
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            if self._last_exchange is not None:
                self._last_exchange['error'] = str(exc)
            raise ModelClientError(f"llama-server request failed: {exc}") from exc

        try:
            data = json.loads(body)
            choice = data["choices"][0]
        except Exception as exc:
            raise ModelClientError("llama-server response was not in chat completions format") from exc

        message = choice.get("message") if isinstance(choice, dict) else None
        content = message.get("content") if isinstance(message, dict) else None
        if not content and isinstance(choice, dict):
            content = choice.get("text")

        if not isinstance(content, str) or not content.strip():
            if self._last_exchange is not None:
                self._last_exchange['error'] = 'llama-server returned empty content'
            raise ModelClientError("llama-server returned empty content")
        if self._last_exchange is not None:
            self._last_exchange['content_preview'] = content[:12000]
        return content
