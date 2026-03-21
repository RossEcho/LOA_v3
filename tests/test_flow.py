from __future__ import annotations

import json
from pathlib import Path
import shutil
import sys

from loa_v3.evaluator import Evaluator
from loa_v3.logger import SessionLogger
from loa_v3.orchestrator import Orchestrator
from loa_v3.planner import FallbackPlanner
from loa_v3.prompt_registry import PromptRegistry
from loa_v3.reporter import Reporter
from loa_v3.tool_registry import ToolRegistry
from loa_v3.tool_runner import ToolRunner
from loa_v3.tool_selector import ToolSelector
from loa_v3.types import PlanStep, RuntimeLimits


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def build_test_orchestrator() -> Orchestrator:
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


def test_generic_prompt_without_model_does_not_execute_fake_fallback_step() -> None:
    orchestrator = build_test_orchestrator()
    result = orchestrator.run('use ping on 8.8.8.8', debug=True)

    assert result.plan.planning_mode == 'fallback'
    assert result.plan.steps == []
    assert result.records == []
    assert result.evaluation.success is False
    assert result.evaluation.needs_replan is True
    assert 'Model planning did not produce an executable plan.' == result.evaluation.reason


def test_tool_registry_exposes_three_tool_types() -> None:
    registry = ToolRegistry(PROJECT_ROOT)
    tool_types = {tool.tool_type for tool in registry.list_tools()}
    assert {0, 1, 2}.issubset(tool_types)


def test_fallback_planner_has_no_generic_execution_step() -> None:
    plan = FallbackPlanner().build_plan('inspect', runtime_limits=RuntimeLimits(), tools=[])
    assert plan.planning_mode == 'fallback'
    assert plan.steps == []


def test_missing_command_becomes_tool_failure_instead_of_crash() -> None:
    orchestrator = build_test_orchestrator()
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


def test_add_tool_prompt_creates_manifest_for_detected_cli() -> None:
    candidate = 'python' if shutil.which('python') else Path(sys.executable).name
    manifest_path = PROJECT_ROOT / 'tool_manifests' / f'{candidate}.json'
    if manifest_path.exists():
        manifest_path.unlink()

    orchestrator = build_test_orchestrator()
    result = orchestrator.run(f'add tool {candidate}', debug=True)

    assert result.plan.planning_mode == 'rule_based'
    assert result.evaluation.success is True
    assert manifest_path.exists()
    payload = json.loads(manifest_path.read_text(encoding='utf-8'))
    assert payload['name'] == candidate
    assert payload['tool_type'] == 1


def test_report_includes_planning_mode() -> None:
    orchestrator = build_test_orchestrator()
    result = orchestrator.run('use ping on 8.8.8.8', debug=True)
    assert 'Planning mode: fallback' in result.report
