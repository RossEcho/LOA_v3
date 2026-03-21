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


def _build_planner_catalog(tools: list[dict]) -> dict[str, Any]:
    available_names = [str(tool.get('name')) for tool in tools if isinstance(tool, dict) and tool.get('name')]
    catalog = {
        'available_tool_names': available_names,
        'script_tools': [],
        'cli_tools': [],
        'master_tools': [],
        'planning_hints': [],
    }
    onboarding_tools: list[str] = []
    for tool in tools:
        if not isinstance(tool, dict):
            continue
        metadata = tool.get('metadata') or {}
        entry = {
            'name': tool.get('name'),
            'description': tool.get('description'),
            'input_contract': metadata.get('input_contract', {}),
            'usage_hint': metadata.get('usage_hint', ''),
            'capabilities': metadata.get('capabilities', {}),
        }
        tool_type = tool.get('tool_type')
        if tool_type == 2:
            catalog['script_tools'].append(entry)
            capabilities = metadata.get('capabilities') or {}
            if capabilities.get('adds_cli_tools'):
                onboarding_tools.append(str(tool.get('name')))
        elif tool_type == 1:
            catalog['cli_tools'].append(entry)
        else:
            catalog['master_tools'].append(entry)

    if onboarding_tools:
        catalog['planning_hints'].append(
            'If the user asks to add, install, or register a tool, prefer an onboarding-capable script tool first.'
        )
        catalog['planning_hints'].append(
            'If the requested command is not yet available but an onboarding script can add CLI tools, you may plan multiple steps: first onboard the command, then use it.'
        )
        catalog['planning_hints'].append(
            'Onboarding-capable script tools: ' + ', '.join(onboarding_tools)
        )
    return catalog


class Planner:
    def build_plan(self, user_prompt: str, *, runtime_limits: RuntimeLimits, tools: list[dict]) -> Plan:
        raise NotImplementedError


class FallbackPlanner(Planner):
    def build_plan(
        self,
        user_prompt: str,
        *,
        runtime_limits: RuntimeLimits,
        tools: list[dict],
        note: str = '',
    ) -> Plan:
        planner_note = note or 'Model planner unavailable; no executable fallback plan was produced.'
        return Plan(
            id=new_id('plan'),
            goal=user_prompt,
            rationale='Planning failed because the model backend was unavailable or returned an unusable plan.',
            requires_replan=True,
            planning_mode='fallback',
            planner_note=planner_note,
            steps=[],
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
            'catalog': _build_planner_catalog(tools),
            'tools': tools,
        }
        prompt = self.prompt_registry.render('planner_prompt', input_json=json.dumps(envelope, ensure_ascii=False, indent=2))
        try:
            payload = self.model_client.generate_json(prompt, schema=PLAN_SCHEMA)
            return self._plan_from_payload(payload, user_prompt, tools)
        except (ModelClientError, KeyError, TypeError, ValueError) as exc:
            return self.fallback.build_plan(user_prompt, runtime_limits=runtime_limits, tools=tools, note=f'model planning failed: {exc}')

    def _plan_from_payload(self, payload: dict[str, Any], user_prompt: str, tools: list[dict]) -> Plan:
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
                    tool_input=dict(raw.get('tool_input') or {}),
                    expected_outcome=str(raw.get('expected_outcome') or 'Command exits successfully.'),
                )
            )

        if not steps:
            return self.fallback.build_plan(user_prompt, runtime_limits=RuntimeLimits(), tools=tools, note='model returned no executable steps')

        return Plan(
            id=str(payload.get('id') or new_id('plan')),
            goal=str(payload.get('goal') or user_prompt),
            rationale=str(payload.get('rationale') or 'Model-generated plan.'),
            requires_replan=bool(payload.get('requires_replan', False)),
            planning_mode='model',
            planner_note='Plan generated by llama-server model backend.',
            steps=steps,
        )
