from __future__ import annotations

from pathlib import Path

from loa_v3.app import _build_debug_payload, _logs_summary, _progress_message, _settings_summary
from loa_v3.config_loader import SettingsLoader
from loa_v3.prompt_registry import PromptRegistry


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_prompt_registry_renders_prompt() -> None:
    registry = PromptRegistry(PROJECT_ROOT / 'prompts')
    rendered = registry.render('planner_prompt', input_json='{"hello":"world"}')
    assert 'hello' in rendered
    assert 'Return exactly one JSON object' in rendered


def test_settings_loader_reads_defaults() -> None:
    loader = SettingsLoader(PROJECT_ROOT)
    settings = loader.load()
    assert settings['model']['endpoint'].startswith('http://')
    assert settings['runtime']['max_steps'] >= 1
    assert settings['runtime']['allow_network'] is True
    assert settings['runtime']['command_timeout_sec'] == 90


def test_settings_summary_exposes_submenu_items() -> None:
    loader = SettingsLoader(PROJECT_ROOT)
    settings = loader.load()
    summary = _settings_summary(settings)
    assert any('Llama endpoint' in item for item in summary)
    assert any('Command timeout sec' in item for item in summary)
    assert summary[-1] == '7) Back'


def test_logs_summary_exposes_cleanup_actions(tmp_path: Path) -> None:
    run_dirs = [tmp_path / 'run_a', tmp_path / 'run_b']
    summary = _logs_summary(run_dirs)
    assert any('Show recent log sessions' in item for item in summary)
    assert any('Clear one log session' in item for item in summary)
    assert any('Clear all log sessions' in item for item in summary)
    assert summary[-1].endswith('run_b')


def test_progress_message_formats_runtime_updates() -> None:
    assert _progress_message('planning_retry', {'attempt': 2}).startswith('Retrying planning')
    assert 'use_ping' in _progress_message('step_started', {'step_id': 'use_ping', 'tool_name': 'ping'})


class _PlannerWithSnapshot:
    def debug_snapshot(self) -> dict:
        return {
            'model_exchange': {
                'raw_response': '{"choices":[{"message":{"content":"{}"}}]}'
            }
        }


class _AppWithPlanner:
    def __init__(self) -> None:
        self.planner = _PlannerWithSnapshot()


class _ResultStub:
    def to_dict(self) -> dict:
        return {'report': 'ok'}


def test_build_debug_payload_includes_raw_llama_response() -> None:
    payload = _build_debug_payload(_AppWithPlanner(), _ResultStub())
    assert 'planner_debug' in payload
    assert payload['raw_llama_server_response'].startswith('{"choices"')
