from __future__ import annotations

from loa_v3.types import Evaluation, ExecutionRecord, Plan, RuntimeLimits


class Evaluator:
    def evaluate(self, plan: Plan, records: list[ExecutionRecord], limits: RuntimeLimits) -> Evaluation:
        if not records:
            if plan.planning_mode == 'fallback':
                return Evaluation(
                    complete=False,
                    success=False,
                    needs_replan=True,
                    reason='Model planning did not produce an executable plan.',
                    anomalies=['planner_fallback', plan.planner_note or 'model_planning_unavailable'],
                )
            return Evaluation(
                complete=False,
                success=False,
                needs_replan=False,
                reason='No steps were executed.',
                anomalies=['empty_execution'],
            )

        failed = [record for record in records if record.status == 'failed']
        if failed:
            return Evaluation(
                complete=limits.stop_on_step_failure,
                success=False,
                needs_replan=not limits.stop_on_step_failure,
                reason=f'Step failure detected: {failed[0].step_id}',
                anomalies=[f'{failed[0].step_id}:step_failed'],
            )

        if len(records) < len(plan.steps):
            return Evaluation(
                complete=False,
                success=False,
                needs_replan=True,
                reason='Execution stopped before all planned steps finished.',
                anomalies=['partial_completion'],
            )

        return Evaluation(
            complete=True,
            success=True,
            needs_replan=plan.requires_replan,
            reason='All planned steps completed successfully.',
            anomalies=[],
        )
