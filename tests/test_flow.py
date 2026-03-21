from __future__ import annotations

import json
from pathlib import Path
import shutil
import sys

from loa_v3.evaluator import Evaluator
from loa_v3.logger import SessionLogger
from loa_v3.model_client import ModelClient
from loa_v3.orchestrator import Orchestrator
from loa_v3.planner import FallbackPlanner, ModelBackedPlanner, _build_planner_catalog
from loa_v3.prompt_registry import PromptRegistry
from loa_v3.reporter import Reporter
from loa_v3.tool_registry import ToolRegistry
from loa_v3.tool_runner import ToolRunner
from loa_v3.tool_selector import ToolSelector
from loa_v3.types import PlanStep, RuntimeLimits


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class StubModelClient(ModelClient):
    def __init__(self, payload: str) -> None:
        self.payload = payload

    def generate_text(self, prompt: str, *, schema: dict | None = None) -> str:
        return self.payload


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
                'tool_input': {'target': '8.8.8.8'},
                'expected_outcome': 'Ping succeeds.'
            }
        ]
    })
    orchestrator = build_model_orchestrator(payload)
    result = orchestrator.run('ping 8.8.8.8', debug=True)
    assert result.plan.planning_mode == 'model'
    assert result.plan.steps[0].tool_name == 'ping'


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
    assert 'tool_onboarder' in hints
    assert 'ping' in hints


def test_tool_registry_exposes_three_tool_types() -> None:
    registry = ToolRegistry(PROJECT_ROOT)
    tool_types = {tool.tool_type for tool in registry.list_tools()}
    assert {0, 1, 2}.issubset(tool_types)
    assert registry.get('tool_onboarder').tool_type == 2


def test_tool_registry_enriches_ping_and_onboarder_metadata() -> None:
    registry = ToolRegistry(PROJECT_ROOT)
    assert registry.get('ping').metadata['input_contract'] == {'target': 'string'}
    assert registry.get('tool_onboarder').metadata['input_contract'] == {'tool_name': 'string'}


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
