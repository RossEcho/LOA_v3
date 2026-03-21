from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from loa_v3.llama_server_client import LlamaServerClient
from loa_v3.types import RuntimeLimits


def _merge_dicts(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _merge_dicts(merged[key], value)
        else:
            merged[key] = value
    return merged


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding='utf-8-sig'))
    return payload if isinstance(payload, dict) else {}


class SettingsLoader:
    def __init__(self, project_root: Path) -> None:
        self.project_root = project_root
        self.defaults_path = project_root / 'config' / 'defaults.json'
        self.settings_path = project_root / 'config' / 'settings.json'

    def load(self) -> dict[str, Any]:
        defaults = _read_json(self.defaults_path)
        local = _read_json(self.settings_path)
        merged = _merge_dicts(defaults, local)

        model = merged.setdefault('model', {})
        model['endpoint'] = os.getenv('LOA_LLAMA_SERVER_URL', model.get('endpoint'))
        model['model_name'] = os.getenv('LOA_LLAMA_SERVER_MODEL', model.get('model_name'))
        model['timeout_sec'] = int(os.getenv('LOA_LLM_TIMEOUT_SEC', model.get('timeout_sec', 90)))
        model['max_tokens'] = int(os.getenv('LOA_LLM_MAX_TOKENS', model.get('max_tokens', 512)))
        model['temperature'] = float(os.getenv('LOA_TEMP', model.get('temperature', 0.0)))
        model['seed'] = int(os.getenv('LOA_SEED', model.get('seed', 0)))
        return merged

    def save(self, payload: dict[str, Any]) -> None:
        self.settings_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')

    def build_model_client(self, settings: dict[str, Any]) -> LlamaServerClient:
        model = settings['model']
        return LlamaServerClient(
            endpoint=model['endpoint'],
            model_name=model['model_name'],
            timeout_sec=int(model['timeout_sec']),
            max_tokens=int(model['max_tokens']),
            temperature=float(model['temperature']),
            seed=int(model['seed']),
            use_schema=bool(model.get('use_schema', False)),
        )

    def build_runtime_limits(self, settings: dict[str, Any]) -> RuntimeLimits:
        runtime = settings['runtime']
        return RuntimeLimits(
            max_steps=int(runtime['max_steps']),
            allow_network=bool(runtime['allow_network']),
            allow_file_write=bool(runtime['allow_file_write']),
            allow_privilege_escalation=bool(runtime['allow_privilege_escalation']),
            stop_on_no_progress=bool(runtime['stop_on_no_progress']),
            stop_on_step_failure=bool(runtime['stop_on_step_failure']),
        )
