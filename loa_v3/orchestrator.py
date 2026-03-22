from __future__ import annotations

from loa_v3.evaluator import Evaluator
from loa_v3.logger import SessionLogger
from loa_v3.planner import Planner
from loa_v3.reporter import Reporter
from loa_v3.tool_runner import ToolRunner, ToolRunnerError
from loa_v3.tool_selector import ToolSelector
from loa_v3.types import ExecutionRecord, PlanStep, RunResult, StepOutcome


class Orchestrator:
    def __init__(
        self,
        *,
        planner: Planner,
        tool_selector: ToolSelector,
        tool_runner: ToolRunner,
        evaluator: Evaluator,
        reporter: Reporter,
        logger: SessionLogger,
        runtime_limits,
    ) -> None:
        self.planner = planner
        self.tool_selector = tool_selector
        self.tool_runner = tool_runner
        self.evaluator = evaluator
        self.reporter = reporter
        self.logger = logger
        self.runtime_limits = runtime_limits

    def run(self, user_prompt: str, *, debug: bool = False) -> RunResult:
        paths = self.logger.create_session(user_prompt[:40] or 'session')
        plan = self.planner.build_plan(
            user_prompt,
            runtime_limits=self.runtime_limits,
            tools=self.tool_selector.registry.build_planning_metadata(),
        )
        self.tool_selector.validate_plan_tools(plan)
        self.logger.log_summary(paths, f'user_prompt: {user_prompt}')
        self.logger.log_decision(paths, {'stage': 'plan_created', 'plan': plan.to_dict()})
        planner_debug = getattr(self.planner, 'debug_snapshot', None)
        if callable(planner_debug):
            self.logger.log_debug(paths, {'stage': 'planner_model_debug', 'payload': planner_debug()})

        records: list[ExecutionRecord] = []
        last_signature = None
        for index, step in enumerate(plan.steps, start=1):
            if index > self.runtime_limits.max_steps:
                self.logger.log_decision(paths, {'stage': 'stop', 'reason': 'max_steps_reached'})
                break

            signature = (step.tool_name, tuple(step.tool_input.get('command', [])) if isinstance(step.tool_input, dict) else ())
            if self.runtime_limits.stop_on_no_progress and signature == last_signature:
                self.logger.log_decision(paths, {'stage': 'stop', 'reason': 'no_progress_repeat_guard', 'step_id': step.id})
                break
            last_signature = signature

            record = self._execute_step(step)
            records.append(record)
            self.logger.log_execution(paths, record.to_dict())
            self._refresh_registry_if_needed(step, record)
            if debug:
                self.logger.log_debug(paths, {'step': step.to_dict(), 'record': record.to_dict()})
            if record.status == 'failed' and self.runtime_limits.stop_on_step_failure:
                self.logger.log_decision(paths, {'stage': 'stop', 'reason': 'step_failure', 'step_id': step.id})
                break

        evaluation = self.evaluator.evaluate(plan, records, self.runtime_limits)
        self.logger.log_decision(paths, {'stage': 'evaluation', 'evaluation': evaluation.to_dict()})
        report = self.reporter.build_report(plan, records, evaluation)
        self.logger.log_summary(paths, report)
        return RunResult(
            plan=plan,
            records=records,
            evaluation=evaluation,
            report=report,
            session_dir=str(paths.root),
        )

    def _refresh_registry_if_needed(self, step: PlanStep, record: ExecutionRecord) -> None:
        if record.status != 'success':
            return
        try:
            tool = self.tool_selector.registry.get(step.tool_name)
        except KeyError:
            return
        capabilities = (tool.metadata or {}).get('capabilities', {})
        if capabilities.get('writes_tool_manifests'):
            self.tool_selector.registry.reload()

    def _execute_step(self, step: PlanStep) -> ExecutionRecord:
        step.status = 'running'
        step.attempts += 1
        anomalies: list[str] = []
        try:
            outcome = self.tool_runner.run_step(step)
        except ToolRunnerError as exc:
            anomalies.append(str(exc))
            outcome = StepOutcome(
                exit_code=-1,
                stdout='',
                stderr=str(exc),
                command=[],
                duration_sec=0.0,
                timed_out=False,
            )
        step.result = outcome
        if outcome.timed_out:
            anomalies.append('timed_out')
        if outcome.exit_code != 0:
            step.status = 'failed'
            anomalies.append('non_zero_exit')
        else:
            step.status = 'success'
        step.anomalies = anomalies
        return ExecutionRecord(
            step_id=step.id,
            tool_name=step.tool_name,
            status=step.status,
            outcome=outcome,
            anomalies=anomalies,
        )
