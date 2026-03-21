from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from loa_v3.types import SessionPaths, utc_now


def _json_safe(value: Any) -> Any:
    if isinstance(value, bytes):
        return value.decode('utf-8', errors='replace')
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    return value


class SessionLogger:
    def __init__(self, project_root: Path) -> None:
        self.project_root = project_root

    def create_session(self, slug: str) -> SessionPaths:
        runs_root = self.project_root / 'runs'
        runs_root.mkdir(parents=True, exist_ok=True)
        safe_slug = ''.join(char if char.isalnum() or char in '-_' else '_' for char in slug)[:60] or 'session'
        stamp = utc_now().replace(':', '').replace('-', '')[:15]
        session_dir = runs_root / f'{stamp}__{safe_slug}'
        suffix = 1
        while session_dir.exists():
            suffix += 1
            session_dir = runs_root / f'{stamp}__{safe_slug}_{suffix}'
        session_dir.mkdir(parents=True, exist_ok=False)
        return SessionPaths(
            root=session_dir,
            user_summary=session_dir / 'user_summary.log',
            execution_log=session_dir / 'execution_log.jsonl',
            decision_log=session_dir / 'decision_log.jsonl',
            debug_trace=session_dir / 'debug_trace.jsonl',
        )

    def _append_jsonl(self, path: Path, payload: dict[str, Any]) -> None:
        with path.open('a', encoding='utf-8') as handle:
            handle.write(json.dumps(_json_safe(payload), ensure_ascii=False) + '\n')

    def log_summary(self, paths: SessionPaths, message: str) -> None:
        with paths.user_summary.open('a', encoding='utf-8') as handle:
            handle.write(message.rstrip() + '\n')

    def log_execution(self, paths: SessionPaths, payload: dict[str, Any]) -> None:
        self._append_jsonl(paths.execution_log, payload)

    def log_decision(self, paths: SessionPaths, payload: dict[str, Any]) -> None:
        self._append_jsonl(paths.decision_log, payload)

    def log_debug(self, paths: SessionPaths, payload: dict[str, Any]) -> None:
        self._append_jsonl(paths.debug_trace, payload)
