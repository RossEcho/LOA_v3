from __future__ import annotations

from pathlib import Path

from loa_v3.app import _logs_summary, _settings_summary
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
