from __future__ import annotations

from typing import Any, Callable

from loa_v3.evaluator import Evaluator
from loa_v3.logger import SessionLogger
from loa_v3.planner import Planner
from loa_v3.reporter import Reporter
from loa_v3.tool_runner import ToolRunner, ToolRunnerError
from loa_v3.tool_selector import ToolSelector
from loa_v3.types import ExecutionRecord, Plan, PlanStep, RunResult, StepOutcome


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
        progress_callback: Callable[[str, dict[str, Any]], None] | None = None,
        planning_retry_limit: int = 1,
    ) -> None:
        self.planner = planner
        self.tool_selector = tool_selector
        self.tool_runner = tool_runner
        self.evaluator = evaluator
        self.reporter = reporter
        self.logger = logger
        self.runtime_limits = runtime_limits
        self.progress_callback = progress_callback
        self.planning_retry_limit = max(0, int(planning_retry_limit))

    def _can_retry_planning(self) -> bool:
        return self.planning_retry_limit > 0 and callable(getattr(self.planner, 'debug_snapshot', None))

    def run(self, user_prompt: str, *, debug: bool = False) -> RunResult:
        paths = self.logger.create_session(user_prompt[:40] or 'session')
        self.logger.log_summary(paths, f'user_prompt: {user_prompt}')

        plan = self._build_plan_with_retry(paths, user_prompt)
        self.tool_selector.validate_plan_tools(plan)
        self._emit_progress(
            paths,
            'plan_ready',
            f"Plan ready with {len(plan.steps)} step(s) in {plan.planning_mode} mode.",
            step_count=len(plan.steps),
            planning_mode=plan.planning_mode,
        )

        records: list[ExecutionRecord] = []
        last_signature = None
        for index, step in enumerate(plan.steps, start=1):
            if index > self.runtime_limits.max_steps:
                self.logger.log_decision(paths, {'stage': 'stop', 'reason': 'max_steps_reached'})
                self._emit_progress(paths, 'stopped', 'Stopped because max_steps was reached.', reason='max_steps_reached')
                break

            signature = (step.tool_name, tuple(step.tool_input.get('command', [])) if isinstance(step.tool_input, dict) else ())
            if self.runtime_limits.stop_on_no_progress and signature == last_signature:
                self.logger.log_decision(paths, {'stage': 'stop', 'reason': 'no_progress_repeat_guard', 'step_id': step.id})
                self._emit_progress(paths, 'stopped', f'Stopped repeated step: {step.id}.', reason='no_progress_repeat_guard', step_id=step.id)
                break
            last_signature = signature

            self._emit_progress(
                paths,
                'step_started',
                f'Running {step.id} with {step.tool_name}.',
                step_id=step.id,
                tool_name=step.tool_name,
                step_index=index,
                total_steps=len(plan.steps),
            )
            record = self._execute_step(step)
            records.append(record)
            self.logger.log_execution(paths, record.to_dict())
            self._refresh_registry_if_needed(step, record)
            self._emit_progress(
                paths,
                'step_completed',
                f'Finished {step.id} with status {record.status}.',
                step_id=step.id,
                tool_name=step.tool_name,
                status=record.status,
                exit_code=record.outcome.exit_code if record.outcome else None,
                duration_sec=record.outcome.duration_sec if record.outcome else None,
                anomalies=record.anomalies,
            )
            if debug:
                self.logger.log_debug(paths, {'step': step.to_dict(), 'record': record.to_dict()})
            if record.status == 'failed' and self.runtime_limits.stop_on_step_failure:
                self.logger.log_decision(paths, {'stage': 'stop', 'reason': 'step_failure', 'step_id': step.id})
                break

        self._emit_progress(paths, 'evaluating', 'Evaluating results.', executed_steps=len(records), planned_steps=len(plan.steps))
        evaluation = self.evaluator.evaluate(plan, records, self.runtime_limits)
        self.logger.log_decision(paths, {'stage': 'evaluation', 'evaluation': evaluation.to_dict()})
        report = self.reporter.build_report(plan, records, evaluation)
        self.logger.log_summary(paths, report)
        self._emit_progress(
            paths,
            'completed',
            f"Run completed with status {'success' if evaluation.success else 'failure'}.",
            success=evaluation.success,
            needs_replan=evaluation.needs_replan,
        )
        return RunResult(
            plan=plan,
            records=records,
            evaluation=evaluation,
            report=report,
            session_dir=str(paths.root),
        )

    def _build_retry_prompt(self, user_prompt: str, planner_note: str) -> str:
        retry_suffix = (
            '\n\nPlanner retry instruction: '
            'The previous planning attempt did not produce an executable JSON plan. '
            'Return exactly one JSON object with executable steps using known tools only. '
            'Use descriptive step ids and exact tool names from the catalog.'
        )
        if planner_note:
            retry_suffix += f' Previous planner note: {planner_note}.'
        return user_prompt + retry_suffix

    def _build_plan_with_retry(self, paths, user_prompt: str) -> Plan:
        prompt_for_attempt = user_prompt
        initial_failure_note = ''
        final_plan: Plan | None = None

        retry_limit = self.planning_retry_limit if self._can_retry_planning() else 0
        for attempt in range(1, retry_limit + 2):
            if attempt == 1:
                self._emit_progress(paths, 'planning_started', 'Planning started.', attempt=attempt)
            else:
                self._emit_progress(paths, 'planning_retry', 'Retrying plan generation after a non-executable planning result.', attempt=attempt)

            plan = self.planner.build_plan(
                prompt_for_attempt,
                runtime_limits=self.runtime_limits,
                tools=self.tool_selector.registry.build_planning_metadata(),
            )
            plan.goal = user_prompt
            self.logger.log_decision(paths, {'stage': 'plan_created', 'attempt': attempt, 'plan': plan.to_dict()})
            planner_debug = getattr(self.planner, 'debug_snapshot', None)
            if callable(planner_debug):
                self.logger.log_debug(paths, {'stage': 'planner_model_debug', 'attempt': attempt, 'payload': planner_debug()})

            final_plan = plan
            if attempt == 1:
                initial_failure_note = plan.planner_note

            if not self._should_retry_plan(plan) or attempt > self.planning_retry_limit:
                break

            prompt_for_attempt = self._build_retry_prompt(user_prompt, plan.planner_note)

        if final_plan is None:
            raise RuntimeError('planner did not return a plan')

        if self._can_retry_planning() and self._should_retry_plan(final_plan):
            final_plan.planner_note = (final_plan.planner_note + f' Retry attempted after initial planning failure: {initial_failure_note}').strip()
        elif self._can_retry_planning() and initial_failure_note and final_plan.planner_note != initial_failure_note:
            final_plan.planner_note = (final_plan.planner_note + f' Planning retry recovered after initial failure: {initial_failure_note}').strip()

        return final_plan

    def _should_retry_plan(self, plan: Plan) -> bool:
        return plan.planning_mode == 'fallback' and not plan.steps

    def _emit_progress(self, paths, stage: str, message: str, **payload: Any) -> None:
        event = {'stage': stage, 'message': message, **payload}
        self.logger.log_decision(paths, {'stage': 'progress', 'progress': event})
        if self.progress_callback is not None:
            self.progress_callback(stage, event)

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
            if outcome.stdout.strip():
                anomalies.append('produced_output_before_timeout')
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
