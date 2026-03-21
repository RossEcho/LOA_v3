from __future__ import annotations

from abc import ABC, abstractmethod
import json
from typing import Any


class ModelClientError(RuntimeError):
    pass


def extract_json_object(text: str) -> dict[str, Any]:
    if not isinstance(text, str) or not text.strip():
        raise ModelClientError("model output did not contain a valid JSON object")

    start = text.find("{")
    if start < 0:
        raise ModelClientError("model output did not contain a valid JSON object")

    depth = 0
    in_string = False
    escaped = False

    for index in range(start, len(text)):
        char = text[index]
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue

        if char == '"':
            in_string = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                candidate = text[start : index + 1]
                try:
                    parsed = json.loads(candidate)
                except json.JSONDecodeError as exc:
                    raise ModelClientError("model output did not contain a valid JSON object") from exc
                if not isinstance(parsed, dict):
                    raise ModelClientError("model output JSON is not an object")
                return parsed

    raise ModelClientError("model output did not contain a valid JSON object")


class ModelClient(ABC):
    @abstractmethod
    def generate_text(self, prompt: str, *, schema: dict[str, Any] | None = None) -> str:
        raise NotImplementedError

    def get_last_exchange(self) -> dict[str, Any] | None:
        return None

    def generate_json(self, prompt: str, *, schema: dict[str, Any] | None = None) -> dict[str, Any]:
        text = self.generate_text(prompt, schema=schema)
        return extract_json_object(text)


class NullModelClient(ModelClient):
    def generate_text(self, prompt: str, *, schema: dict[str, Any] | None = None) -> str:
        raise ModelClientError("no model backend is available")
