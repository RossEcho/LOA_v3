from __future__ import annotations

import json
from typing import Any

from loa_v3.model_client import ModelClient, ModelClientError
from loa_v3.prompt_registry import PromptRegistry
from loa_v3.types import Plan, PlanStep, RuntimeLimits, new_id


PLAN_SCHEMA: dict[str, Any] = {
    'type': 'object',
    'required': ['id', 'goal', 'rationale', 'steps'],
}


class Planner:
    def build_plan(self, user_prompt: str, *, runtime_limits: RuntimeLimits, tools: list[dict]) -> Plan:
        raise NotImplementedError


class FallbackPlanner(Planner):
    def build_plan(self, user_prompt: str, *, runtime_limits: RuntimeLimits, tools: list[dict]) -> Plan:
        step = PlanStep(
            id='step_1',
            title='Inspect working directory',
            objective='Gather basic local context before deeper actions.',
            tool_name='shell',
            tool_input={'command': ['powershell', '-Command', 'Get-Location']},
            expected_outcome='Current working directory is printed successfully.',
        )
        return Plan(
            id=new_id('plan'),
            goal=user_prompt,
            rationale='Fallback planner used a safe local inspection step because model planning was unavailable.',
            steps=[step],
        )


class ModelBackedPlanner(Planner):
    def __init__(self, model_client: ModelClient, prompt_registry: PromptRegistry) -> None:
        self.model_client = model_client
        self.prompt_registry = prompt_registry
        self.fallback = FallbackPlanner()

    def build_plan(self, user_prompt: str, *, runtime_limits: RuntimeLimits, tools: list[dict]) -> Plan:
        envelope = {
            'user_prompt': user_prompt,
            'runtime_limits': {
                'max_steps': runtime_limits.max_steps,
                'allow_network': runtime_limits.allow_network,
                'allow_file_write': runtime_limits.allow_file_write,
                'allow_privilege_escalation': runtime_limits.allow_privilege_escalation,
            },
            'tools': tools,
        }
        prompt = self.prompt_registry.render('planner_prompt', input_json=json.dumps(envelope, ensure_ascii=False, indent=2))
        try:
            payload = self.model_client.generate_json(prompt, schema=PLAN_SCHEMA)
            return self._plan_from_payload(payload, user_prompt)
        except (ModelClientError, KeyError, TypeError, ValueError):
            return self.fallback.build_plan(user_prompt, runtime_limits=runtime_limits, tools=tools)

    def _plan_from_payload(self, payload: dict[str, Any], user_prompt: str) -> Plan:
        steps: list[PlanStep] = []
        for index, raw in enumerate(payload.get('steps', []), start=1):
            if not isinstance(raw, dict):
                continue
            steps.append(
                PlanStep(
                    id=str(raw.get('id') or f'step_{index}'),
                    title=str(raw.get('title') or f'Step {index}'),
                    objective=str(raw.get('objective') or 'Execute requested action.'),
                    tool_name=str(raw.get('tool_name') or 'shell'),
                    tool_input=dict(raw.get('tool_input') or {'command': ['powershell', '-Command', 'Get-Location']}),
                    expected_outcome=str(raw.get('expected_outcome') or 'Command exits successfully.'),
                )
            )

        if not steps:
            return self.fallback.build_plan(user_prompt, runtime_limits=RuntimeLimits(), tools=[])

        return Plan(
            id=str(payload.get('id') or new_id('plan')),
            goal=str(payload.get('goal') or user_prompt),
            rationale=str(payload.get('rationale') or 'Model-generated plan.'),
            requires_replan=bool(payload.get('requires_replan', False)),
            steps=steps,
        )
