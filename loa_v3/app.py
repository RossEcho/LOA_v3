from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess
from typing import Any

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
RUNS_ROOT = PROJECT_ROOT / 'runs'


def _progress_message(stage: str, payload: dict[str, Any]) -> str:
    if stage == 'planning_started':
        return f"Planning attempt {payload.get('attempt', 1)}..."
    if stage == 'planning_retry':
        return f"Retrying planning (attempt {payload.get('attempt', '?')}) after a non-executable result..."
    if stage == 'plan_ready':
        return f"Plan ready: {payload.get('step_count', 0)} step(s), mode={payload.get('planning_mode', 'unknown')}"
    if stage == 'step_started':
        return f"Running {payload.get('step_id', 'step')} with {payload.get('tool_name', 'tool')}..."
    if stage == 'step_completed':
        return (
            f"Finished {payload.get('step_id', 'step')}: {payload.get('status', 'unknown')} "
            f"exit={payload.get('exit_code', '?')}"
        )
    if stage == 'evaluating':
        return 'Evaluating results...'
    if stage == 'completed':
        return f"Run complete: {'success' if payload.get('success') else 'failure'}"
    if stage == 'stopped':
        return payload.get('message', 'Run stopped.')
    return payload.get('message', stage.replace('_', ' ').title())


def _terminal_progress(stage: str, payload: dict[str, Any]) -> None:
    print(f"[{stage}] {_progress_message(stage, payload)}", flush=True)


def build_app(*, debug: bool = False, progress_callback=None) -> Orchestrator:
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
        progress_callback=progress_callback,
    )


def _build_debug_payload(app: Orchestrator, result) -> dict:
    payload = result.to_dict()
    planner_debug = getattr(app.planner, 'debug_snapshot', None)
    if callable(planner_debug):
        snapshot = planner_debug()
        payload['planner_debug'] = snapshot
        model_exchange = snapshot.get('model_exchange') if isinstance(snapshot, dict) else None
        if isinstance(model_exchange, dict):
            payload['raw_llama_server_response'] = model_exchange.get('raw_response', '')
    return payload


def run_flow(*, debug: bool = False) -> int:
    prompt = input('Prompt: ').strip()
    if not prompt:
        print('Prompt cannot be empty')
        return 1
    app = build_app(debug=debug, progress_callback=_terminal_progress)
    result = app.run(prompt, debug=debug)
    print(result.report)
    if debug:
        print(json.dumps(_build_debug_payload(app, result), ensure_ascii=False, indent=2))
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


def _list_run_directories() -> list[Path]:
    if not RUNS_ROOT.exists():
        return []
    return sorted((path for path in RUNS_ROOT.iterdir() if path.is_dir()), key=lambda item: item.name, reverse=True)


def _logs_summary(run_dirs: list[Path]) -> list[str]:
    lines = [
        f'Runs root: {RUNS_ROOT}',
        f'Log sessions: {len(run_dirs)}',
        '1) Show recent log sessions',
        '2) Clear one log session',
        '3) Clear all log sessions',
        '4) Back',
    ]
    if run_dirs:
        lines.append('Recent:')
        for run_dir in run_dirs[:5]:
            lines.append(f'   - {run_dir.name}')
    return lines


def _print_recent_runs(run_dirs: list[Path], limit: int = 20) -> None:
    if not run_dirs:
        print('No log sessions found')
        return
    print(f'Recent log sessions ({min(len(run_dirs), limit)} shown):')
    for index, run_dir in enumerate(run_dirs[:limit], start=1):
        print(f'{index}) {run_dir.name}')


def _clear_single_log_session() -> None:
    run_dirs = _list_run_directories()
    if not run_dirs:
        print('No log sessions to clear')
        return
    _print_recent_runs(run_dirs)
    choice = input(f'Select session [1-{len(run_dirs[:20])}] or blank to cancel: ').strip()
    if not choice:
        print('Clear one cancelled')
        return
    if not choice.isdigit():
        print('Invalid selection')
        return
    selected_index = int(choice)
    visible_runs = run_dirs[:20]
    if selected_index < 1 or selected_index > len(visible_runs):
        print('Invalid selection')
        return
    target = visible_runs[selected_index - 1]
    confirm = input(f"Type DELETE to remove '{target.name}': ").strip()
    if confirm != 'DELETE':
        print('Clear one cancelled')
        return
    shutil.rmtree(target)
    print(f'Removed log session: {target.name}')


def _clear_all_log_sessions() -> None:
    run_dirs = _list_run_directories()
    if not run_dirs:
        print('No log sessions to clear')
        return
    confirm = input(f'Type DELETE ALL to remove {len(run_dirs)} log sessions: ').strip()
    if confirm != 'DELETE ALL':
        print('Clear all cancelled')
        return
    for run_dir in run_dirs:
        shutil.rmtree(run_dir)
    print(f'Removed {len(run_dirs)} log sessions')


def logs_menu() -> int:
    while True:
        run_dirs = _list_run_directories()
        print('Logs Menu')
        for line in _logs_summary(run_dirs):
            print(line)
        choice = input('Select [1-4]: ').strip()

        if choice == '1':
            _print_recent_runs(run_dirs)
            continue
        if choice == '2':
            _clear_single_log_session()
            continue
        if choice == '3':
            _clear_all_log_sessions()
            continue
        if choice == '4':
            return 0
        print('Invalid selection')


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
        print('5) Logs')
        print('6) Exit')
        choice = input('Select [1-6]: ').strip()

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
            logs_menu()
            continue
        if choice == '6':
            return 0
        print('Invalid selection')
