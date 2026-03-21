from __future__ import annotations

import json
from pathlib import Path
import shutil
import sys

from loa_v3.evaluator import Evaluator
from loa_v3.logger import SessionLogger
from loa_v3.model_client import ModelClient
from loa_v3.orchestrator import Orchestrator
from loa_v3.planner import FallbackPlanner, ModelBackedPlanner, _build_planner_catalog, _derive_goal_hints
from loa_v3.prompt_registry import PromptRegistry
from loa_v3.reporter import Reporter
from loa_v3.tool_introspection import build_cli_metadata
from loa_v3.tool_registry import ToolRegistry
from loa_v3.tool_runner import ToolRunner
from loa_v3.tool_selector import ToolSelector
from loa_v3.types import PlanStep, RuntimeLimits


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class StubModelClient(ModelClient):
    def __init__(self, payload: str) -> None:
        self.payload = payload
        self.last_exchange: dict[str, object] | None = None

    def generate_text(self, prompt: str, *, schema: dict | None = None) -> str:
        self.last_exchange = {'prompt_preview': prompt[:2000], 'schema': schema or {}, 'content_preview': self.payload}
        return self.payload

    def get_last_exchange(self) -> dict[str, object] | None:
        return self.last_exchange


def build_fallback_orchestrator() -> Orchestrator:
    registry = ToolRegistry(PROJECT_ROOT)
    limits = RuntimeLimits(max_steps=3)
    return Orchestrator(
        planner=FallbackPlanner(),
        tool_selector=ToolSelector(registry),
        tool_runner=ToolRunner(PROJECT_ROOT, registry, limits),
        evaluator=Evaluator(),
        reporter=Reporter(PromptRegistry(PROJECT_ROOT / 'prompts')),
        logger=SessionLogger(PROJECT_ROOT),
        runtime_limits=limits,
    )


def build_model_orchestrator(payload: str) -> Orchestrator:
    registry = ToolRegistry(PROJECT_ROOT)
    limits = RuntimeLimits(max_steps=3, allow_network=True)
    planner = ModelBackedPlanner(StubModelClient(payload), PromptRegistry(PROJECT_ROOT / 'prompts'))
    return Orchestrator(
        planner=planner,
        tool_selector=ToolSelector(registry),
        tool_runner=ToolRunner(PROJECT_ROOT, registry, limits),
        evaluator=Evaluator(),
        reporter=Reporter(PromptRegistry(PROJECT_ROOT / 'prompts')),
        logger=SessionLogger(PROJECT_ROOT),
        runtime_limits=limits,
    )


def test_generic_prompt_without_model_does_not_execute_fake_fallback_step() -> None:
    orchestrator = build_fallback_orchestrator()
    result = orchestrator.run('list network status', debug=True)

    assert result.plan.planning_mode == 'fallback'
    assert result.plan.steps == []
    assert result.records == []
    assert result.evaluation.success is False
    assert result.evaluation.needs_replan is True
    assert 'Model planning did not produce an executable plan.' == result.evaluation.reason


def test_model_can_choose_ping_tool_step() -> None:
    payload = json.dumps({
        'id': 'plan_test_ping',
        'goal': 'ping 8.8.8.8',
        'rationale': 'Model selected the ping tool.',
        'steps': [
            {
                'id': 'step_1',
                'title': 'Run ping',
                'objective': 'Ping 8.8.8.8.',
                'tool_name': 'ping',
                'tool_input': {'arg_1': '8.8.8.8'},
                'expected_outcome': 'Ping succeeds.'
            }
        ]
    })
    orchestrator = build_model_orchestrator(payload)
    result = orchestrator.run('ping 8.8.8.8', debug=True)
    assert result.plan.planning_mode == 'model'
    assert result.plan.steps[0].tool_name == 'ping'


def test_planner_debug_snapshot_captures_model_exchange() -> None:
    payload = json.dumps({
        'id': 'plan_debug',
        'goal': 'ping 8.8.8.8',
        'rationale': 'debug capture test',
        'steps': [
            {
                'id': 'step_1',
                'title': 'Run ping',
                'objective': 'Ping the host.',
                'tool_name': 'ping',
                'tool_input': {'arg_1': '8.8.8.8'},
                'expected_outcome': 'Ping succeeds.',
            }
        ],
    })
    planner = ModelBackedPlanner(StubModelClient(payload), PromptRegistry(PROJECT_ROOT / 'prompts'))
    registry = ToolRegistry(PROJECT_ROOT)
    planner.build_plan('ping 8.8.8.8', runtime_limits=RuntimeLimits(max_steps=3, allow_network=True), tools=registry.build_planning_metadata())
    snapshot = planner.debug_snapshot()
    assert snapshot['user_prompt'] == 'ping 8.8.8.8'
    assert 'rendered_prompt' in snapshot
    assert snapshot['parsed_payload']['id'] == 'plan_debug'
    assert snapshot['model_exchange']['content_preview'] == payload


def test_onboarding_only_goal_trims_invalid_model_execution_steps() -> None:
    payload = json.dumps({
        'id': 'plan_invalid_extra_use',
        'goal': 'add tool ping',
        'rationale': 'Model incorrectly added a use step.',
        'steps': [
            {
                'id': 'step_0',
                'title': 'Onboard ping',
                'objective': 'Register ping as a tool.',
                'tool_name': 'tool_onboarder',
                'tool_input': {'tool_name': 'ping'},
                'expected_outcome': 'A manifest is created.',
            },
            {
                'id': 'step_1',
                'title': 'Use ping',
                'objective': 'Run ping even though the user did not ask for that.',
                'tool_name': 'ping',
                'tool_input': {'arg_1': '8.8.8.8'},
                'expected_outcome': 'This step should be trimmed away.',
            },
        ],
    })
    planner = ModelBackedPlanner(StubModelClient(payload), PromptRegistry(PROJECT_ROOT / 'prompts'))
    registry = ToolRegistry(PROJECT_ROOT)
    plan = planner.build_plan('add tool ping', runtime_limits=RuntimeLimits(max_steps=3, allow_network=True), tools=registry.build_planning_metadata())
    assert [step.tool_name for step in plan.steps] == ['tool_onboarder']
    assert 'Goal boundary enforcement removed execution steps' in plan.planner_note


def test_model_can_choose_tool_onboarder_script_tool() -> None:
    candidate = 'python' if shutil.which('python') else Path(sys.executable).name
    manifest_path = PROJECT_ROOT / 'tool_manifests' / f'{candidate}.json'
    if manifest_path.exists() and candidate != 'tool_onboarder':
        manifest_path.unlink()
    payload = json.dumps({
        'id': 'plan_test_onboard',
        'goal': f'add {candidate} as a tool',
        'rationale': 'Model selected the onboarding script tool.',
        'steps': [
            {
                'id': 'step_1',
                'title': 'Onboard CLI tool',
                'objective': f'Register {candidate} as an available CLI tool.',
                'tool_name': 'tool_onboarder',
                'tool_input': {'tool_name': candidate},
                'expected_outcome': 'A manifest is created.'
            }
        ]
    })
    orchestrator = build_model_orchestrator(payload)
    result = orchestrator.run(f'add {candidate} as a tool', debug=True)
    assert result.plan.planning_mode == 'model'
    assert result.evaluation.success is True
    assert manifest_path.exists()


def test_planner_catalog_includes_onboarding_hints() -> None:
    registry = ToolRegistry(PROJECT_ROOT)
    catalog = _build_planner_catalog(registry.build_planning_metadata())
    hints = '\n'.join(catalog['planning_hints'])
    assert 'onboarding script' in hints
    assert 'multiple steps' in hints


def test_goal_hints_distinguish_onboard_only_from_use() -> None:
    onboarding = _derive_goal_hints('add the tool ping')
    usage = _derive_goal_hints('try pinging 8.8.8.8')
    combined = _derive_goal_hints('add ping and then use it on 8.8.8.8')

    assert onboarding['onboarding_only'] is True
    assert onboarding['requested_actions'] == ['onboard_tool']
    assert usage['use_only'] is True
    assert usage['requested_actions'] == ['use_tool']
    assert combined['may_require_multi_step'] is True
    assert combined['requested_actions'] == ['onboard_tool', 'use_tool']


def test_build_cli_metadata_infers_structured_help_details() -> None:
    help_output = '''Usage: ping [options] <destination>
  -c <count>         stop after sending count packets
  -i <interval>      wait interval seconds between sending each packet
  -W <timeout>       time to wait for response
'''
    metadata = build_cli_metadata('ping', '/usr/bin/ping', help_output, 'ping version', {'help_command': ['ping', '-h']})
    assert metadata['input_contract'] == {'destination': 'string'}
    assert metadata['required_args'] == ['destination']
    assert metadata['execution']['long_running_by_default'] is True
    assert metadata['execution']['safe_default_flags'] == ['-c', '4']
    assert metadata['optional_args'][0]['flags'][0] == '-c'


def test_tool_registry_exposes_three_tool_types() -> None:
    registry = ToolRegistry(PROJECT_ROOT)
    tool_types = {tool.tool_type for tool in registry.list_tools()}
    assert {0, 1, 2}.issubset(tool_types)
    assert registry.get('tool_onboarder').tool_type == 2


def test_tool_registry_enriches_generic_cli_and_onboarder_metadata() -> None:
    registry = ToolRegistry(PROJECT_ROOT)
    ping = registry.get('ping')
    assert ping.metadata['input_contract']
    assert 'execution' in ping.metadata
    assert ping.metadata['required_args'] == list(ping.metadata['input_contract'].keys())
    assert registry.get('tool_onboarder').metadata['input_contract'] == {'tool_name': 'string'}
    assert registry.get('tool_onboarder').metadata['capabilities']['adds_cli_tools'] is True


def test_tool_runner_uses_runtime_default_timeout_when_manifest_omits_it(tmp_path: Path) -> None:
    project_root = tmp_path / 'project_timeout'
    project_root.mkdir()
    (project_root / 'tool_manifests').mkdir()
    script_path = project_root / 'echo_timeout.py'
    script_path.write_text('import sys\nprint("ok")\n', encoding='utf-8')
    (project_root / 'tool_manifests' / 'echo_timeout.json').write_text(json.dumps({
        'name': 'echo_timeout',
        'tool_type': 1,
        'description': 'Echo for timeout tests.',
        'command_template': [sys.executable, str(script_path)],
        'metadata': {
            'input_contract': {'arg_1': 'string'},
            'argument_order': ['arg_1'],
            'execution': {
                'long_running_by_default': False,
                'safe_default_flags': [],
            },
        },
    }, ensure_ascii=False), encoding='utf-8')
    registry = ToolRegistry(project_root)
    limits = RuntimeLimits(max_steps=2, allow_network=True, command_timeout_sec=90)
    runner = ToolRunner(project_root, registry, limits)
    assert runner._resolve_timeout(registry.get('echo_timeout')) == 90


def test_tool_runner_uses_safe_default_flags_from_manifest(tmp_path: Path) -> None:
    project_root = tmp_path / 'project'
    project_root.mkdir()
    (project_root / 'tool_manifests').mkdir()
    script_path = project_root / 'echo_args.py'
    script_path.write_text('import json, sys\nprint(json.dumps(sys.argv[1:]))\n', encoding='utf-8')
    (project_root / 'tool_manifests' / 'echo_args.json').write_text(json.dumps({
        'name': 'echo_args',
        'tool_type': 1,
        'description': 'Echo argv for tests.',
        'command_template': [sys.executable, str(script_path)],
        'metadata': {
            'input_contract': {'destination': 'string'},
            'argument_order': ['destination'],
            'execution': {
                'long_running_by_default': True,
                'safe_default_flags': ['--count', '4'],
                'default_timeout_sec': 30,
            },
        },
    }, ensure_ascii=False), encoding='utf-8')
    registry = ToolRegistry(project_root)
    runner = ToolRunner(project_root, registry, RuntimeLimits(max_steps=2, allow_network=True))
    outcome = runner.run_step(PlanStep(
        id='step_1',
        title='Echo args',
        objective='Verify safe default flags are included.',
        tool_name='echo_args',
        tool_input={'destination': '8.8.8.8'},
        expected_outcome='The runner passes safe flags before user args.',
    ))
    assert outcome.exit_code == 0
    assert json.loads(outcome.stdout.strip()) == ['--count', '4', '8.8.8.8']


def test_fallback_planner_has_no_generic_execution_step() -> None:
    plan = FallbackPlanner().build_plan('inspect', runtime_limits=RuntimeLimits(), tools=[])
    assert plan.planning_mode == 'fallback'
    assert plan.steps == []


def test_missing_command_becomes_tool_failure_instead_of_crash() -> None:
    orchestrator = build_fallback_orchestrator()
    bad_step = PlanStep(
        id='bad_step',
        title='Run missing command',
        objective='Verify missing executables fail gracefully.',
        tool_name='shell',
        tool_input={'command': ['command-that-does-not-exist-12345']},
        expected_outcome='The command should fail without crashing the orchestrator.',
    )

    record = orchestrator._execute_step(bad_step)
    assert record.status == 'failed'
    assert 'command execution failed' in record.anomalies[0]


def test_logger_accepts_bytes_payloads() -> None:
    logger = SessionLogger(PROJECT_ROOT)
    paths = logger.create_session('bytes_logger_test')
    logger.log_execution(paths, {'stdout': b'raw-bytes', 'nested': {'stderr': b'err'}})
    content = paths.execution_log.read_text(encoding='utf-8')
    assert 'raw-bytes' in content
    assert 'err' in content


def test_report_includes_planning_mode() -> None:
    orchestrator = build_fallback_orchestrator()
    result = orchestrator.run('list network status', debug=True)
    assert 'Planning mode: fallback' in result.report
