from __future__ import annotations

import json

from loa_v3.model_client import ModelClient, ModelClientError
from loa_v3.prompt_registry import PromptRegistry
from loa_v3.types import Evaluation, ExecutionRecord, Plan


class Reporter:
    def __init__(self, prompt_registry: PromptRegistry, model_client: ModelClient | None = None) -> None:
        self.prompt_registry = prompt_registry
        self.model_client = model_client

    def build_report(self, plan: Plan, records: list[ExecutionRecord], evaluation: Evaluation) -> str:
        summary = {
            'goal': plan.goal,
            'plan_id': plan.id,
            'planning_mode': plan.planning_mode,
            'planner_note': plan.planner_note,
            'steps_total': len(plan.steps),
            'steps_executed': len(records),
            'evaluation': evaluation.to_dict(),
            'records': [record.to_dict() for record in records],
        }
        if self.model_client is not None:
            prompt = self.prompt_registry.render('report_prompt', input_json=json.dumps(summary, ensure_ascii=False, indent=2))
            try:
                text = self.model_client.generate_text(prompt)
                if isinstance(text, str) and text.strip():
                    return text.strip()
            except ModelClientError:
                pass

        lines = [
            f"Goal: {plan.goal}",
            f"Status: {'success' if evaluation.success else 'failure'}",
            f"Reason: {evaluation.reason}",
            f"Planning mode: {plan.planning_mode}",
        ]
        if plan.planner_note:
            lines.append(f"Planner note: {plan.planner_note}")
        for record in records:
            outcome = record.outcome
            if outcome is None:
                lines.append(f'- {record.step_id}: no outcome recorded')
                continue
            lines.append(f"- {record.step_id} [{record.status}] command={' '.join(outcome.command)} exit={outcome.exit_code}")
            if record.anomalies:
                lines.append(f"  anomalies: {', '.join(record.anomalies)}")
        return '\n'.join(lines)
