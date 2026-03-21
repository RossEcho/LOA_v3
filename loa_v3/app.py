from __future__ import annotations

import json
from pathlib import Path
import subprocess

from loa_v3.config_loader import SettingsLoader
from loa_v3.evaluator import Evaluator
from loa_v3.logger import SessionLogger
from loa_v3.orchestrator import Orchestrator
from loa_v3.planner import ModelBackedPlanner
from loa_v3.prompt_registry import PromptRegistry
from loa_v3.reporter import Reporter
from loa_v3.tool_registry import ToolRegistry
from loa_v3.tool_runner import ToolRunner
from loa_v3.tool_selector import ToolSelector


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def build_app(*, debug: bool = False) -> Orchestrator:
    settings_loader = SettingsLoader(PROJECT_ROOT)
    settings = settings_loader.load()
    runtime_limits = settings_loader.build_runtime_limits(settings)
    if debug:
        settings['runtime']['debug'] = True

    prompt_registry = PromptRegistry(PROJECT_ROOT / 'prompts')
    model_client = settings_loader.build_model_client(settings)
    registry = ToolRegistry(PROJECT_ROOT)
    planner = ModelBackedPlanner(model_client, prompt_registry)
    selector = ToolSelector(registry)
    runner = ToolRunner(PROJECT_ROOT, registry, runtime_limits)
    evaluator = Evaluator()
    reporter = Reporter(prompt_registry, model_client=None)
    logger = SessionLogger(PROJECT_ROOT)
    return Orchestrator(
        planner=planner,
        tool_selector=selector,
        tool_runner=runner,
        evaluator=evaluator,
        reporter=reporter,
        logger=logger,
        runtime_limits=runtime_limits,
    )


def run_flow(*, debug: bool = False) -> int:
    prompt = input('Prompt: ').strip()
    if not prompt:
        print('Prompt cannot be empty')
        return 1
    app = build_app(debug=debug)
    result = app.run(prompt, debug=debug)
    print(result.report)
    if debug:
        print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
    return 0


def _parse_yes_no(value: str, current: bool) -> bool:
    normalized = (value or '').strip().lower()
    if not normalized:
        return current
    if normalized in {'y', 'yes', 'true', '1', 'on'}:
        return True
    if normalized in {'n', 'no', 'false', '0', 'off'}:
        return False
    return current


def _settings_summary(settings: dict) -> list[str]:
    runtime = settings['runtime']
    model = settings['model']
    return [
        f"1) Llama endpoint: {model.get('endpoint', '')}",
        f"2) Model name: {model.get('model_name', '')}",
        f"3) Max steps: {runtime.get('max_steps', '')}",
        f"4) Command timeout sec: {runtime.get('command_timeout_sec', '')}",
        f"5) Allow network: {'on' if runtime.get('allow_network') else 'off'}",
        '6) Show full settings JSON',
        '7) Back',
    ]


def settings_menu() -> int:
    loader = SettingsLoader(PROJECT_ROOT)

    while True:
        settings = loader.load()
        print(f'Settings file: {loader.settings_path}')
        print('Settings Menu')
        for line in _settings_summary(settings):
            print(line)
        choice = input('Select [1-7]: ').strip()

        if choice == '1':
            endpoint = input('llama-server endpoint: ').strip()
            if endpoint:
                settings['model']['endpoint'] = endpoint
                loader.save(settings)
                print('Endpoint saved')
            continue
        if choice == '2':
            model_name = input('model name: ').strip()
            if model_name:
                settings['model']['model_name'] = model_name
                loader.save(settings)
                print('Model name saved')
            continue
        if choice == '3':
            max_steps = input('max steps: ').strip()
            if max_steps:
                settings['runtime']['max_steps'] = int(max_steps)
                loader.save(settings)
                print('Max steps saved')
            continue
        if choice == '4':
            command_timeout = input('command timeout sec: ').strip()
            if command_timeout:
                settings['runtime']['command_timeout_sec'] = int(command_timeout)
                loader.save(settings)
                print('Command timeout saved')
            continue
        if choice == '5':
            current_network = bool(settings['runtime'].get('allow_network', False))
            allow_network = input(f"allow network? [Y/n] (current: {'on' if current_network else 'off'}): ").strip()
            settings['runtime']['allow_network'] = _parse_yes_no(allow_network, current_network)
            loader.save(settings)
            print('Network setting saved')
            continue
        if choice == '6':
            print(json.dumps(settings, ensure_ascii=False, indent=2))
            continue
        if choice == '7':
            return 0
        print('Invalid selection')


def tests_menu() -> int:
    proc = subprocess.run(
        ['python', '-m', 'pytest', 'tests', '-q', '-p', 'no:cacheprovider'],
        cwd=str(PROJECT_ROOT),
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.stdout.strip():
        print(proc.stdout.strip())
    if proc.stderr.strip():
        print(proc.stderr.strip())
    return proc.returncode


def main() -> int:
    while True:
        print('\nLOA_v3 Menu')
        print('1) Tests')
        print('2) Settings')
        print('3) Conversation flow')
        print('4) Debug mode')
        print('5) Exit')
        choice = input('Select [1-5]: ').strip()

        if choice == '1':
            tests_menu()
            continue
        if choice == '2':
            settings_menu()
            continue
        if choice == '3':
            run_flow(debug=False)
            continue
        if choice == '4':
            run_flow(debug=True)
            continue
        if choice == '5':
            return 0
        print('Invalid selection')
