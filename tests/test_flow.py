from __future__ import annotations

from pathlib import Path

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


def test_fallback_flow_runs_and_creates_report() -> None:
    orchestrator = build_test_orchestrator()
    result = orchestrator.run('show me the current directory', debug=True)

    assert result.evaluation.complete is True
    assert result.evaluation.success is True
    assert 'Goal:' in result.report
    assert Path(result.session_dir).exists()


def test_tool_registry_exposes_three_tool_types() -> None:
    registry = ToolRegistry(PROJECT_ROOT)
    tool_types = {tool.tool_type for tool in registry.list_tools()}
    assert {0, 1, 2}.issubset(tool_types)


def test_fallback_planner_uses_portable_python_command() -> None:
    plan = FallbackPlanner().build_plan('inspect', runtime_limits=RuntimeLimits(), tools=[])
    assert plan.steps[0].tool_input['command'][0]
    assert '-c' in plan.steps[0].tool_input['command']


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
