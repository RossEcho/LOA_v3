from __future__ import annotations

from loa_v3.tool_registry import ToolRegistry
from loa_v3.types import Plan


class ToolSelector:
    def __init__(self, registry: ToolRegistry) -> None:
        self.registry = registry

    def validate_plan_tools(self, plan: Plan) -> None:
        for step in plan.steps:
            self.registry.get(step.tool_name)
