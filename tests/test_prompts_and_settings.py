from __future__ import annotations

from pathlib import Path

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
