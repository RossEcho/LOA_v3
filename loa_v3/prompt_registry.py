from __future__ import annotations

from pathlib import Path


class PromptRegistry:
    def __init__(self, prompts_dir: Path) -> None:
        self.prompts_dir = prompts_dir

    def load(self, key: str) -> str:
        path = self.prompts_dir / f"{key}.txt"
        if not path.exists():
            raise FileNotFoundError(f"prompt not found: {path}")
        return path.read_text(encoding="utf-8")

    def render(self, key: str, **values: str) -> str:
        template = self.load(key)
        return template.format(**values)
