from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal
import uuid


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:10]}"


ToolType = Literal[0, 1, 2]
StepStatus = Literal["pending", "running", "success", "failed", "skipped"]


@dataclass(slots=True)
class RuntimeLimits:
    max_steps: int = 6
    allow_network: bool = False
    allow_file_write: bool = False
    allow_privilege_escalation: bool = False
    stop_on_no_progress: bool = True
    stop_on_step_failure: bool = True


@dataclass(slots=True)
class StepOutcome:
    exit_code: int
    stdout: str
    stderr: str
    command: list[str]
    duration_sec: float
    timed_out: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class PlanStep:
    id: str
    title: str
    objective: str
    tool_name: str
    tool_input: dict[str, Any]
    expected_outcome: str
    status: StepStatus = "pending"
    attempts: int = 0
    result: StepOutcome | None = None
    anomalies: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        if self.result is not None:
            payload["result"] = self.result.to_dict()
        return payload


@dataclass(slots=True)
class Plan:
    id: str
    goal: str
    rationale: str
    requires_replan: bool = False
    steps: list[PlanStep] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "goal": self.goal,
            "rationale": self.rationale,
            "requires_replan": self.requires_replan,
            "steps": [step.to_dict() for step in self.steps],
        }


@dataclass(slots=True)
class ToolDefinition:
    name: str
    tool_type: ToolType
    description: str
    command_template: list[str]
    metadata: dict[str, Any] = field(default_factory=dict)
    manifest_path: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class ExecutionRecord:
    step_id: str
    tool_name: str
    status: StepStatus
    outcome: StepOutcome | None
    anomalies: list[str]

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        if self.outcome is not None:
            payload["outcome"] = self.outcome.to_dict()
        return payload


@dataclass(slots=True)
class Evaluation:
    complete: bool
    success: bool
    needs_replan: bool
    reason: str
    anomalies: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class SessionPaths:
    root: Path
    user_summary: Path
    execution_log: Path
    decision_log: Path
    debug_trace: Path


@dataclass(slots=True)
class RunResult:
    plan: Plan
    records: list[ExecutionRecord]
    evaluation: Evaluation
    report: str
    session_dir: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "plan": self.plan.to_dict(),
            "records": [record.to_dict() for record in self.records],
            "evaluation": self.evaluation.to_dict(),
            "report": self.report,
            "session_dir": self.session_dir,
        }
