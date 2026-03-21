from __future__ import annotations

from pathlib import Path
import subprocess
import sys
import time

from loa_v3.tool_registry import ToolRegistry
from loa_v3.types import PlanStep, RuntimeLimits, StepOutcome, ToolDefinition


class ToolRunnerError(RuntimeError):
    pass


def _normalize_text(value) -> str:
    if isinstance(value, bytes):
        return value.decode('utf-8', errors='replace')
    if value is None:
        return ''
    return str(value)


class ToolRunner:
    def __init__(self, project_root: Path, registry: ToolRegistry, limits: RuntimeLimits) -> None:
        self.project_root = project_root
        self.registry = registry
        self.limits = limits

    def run_step(self, step: PlanStep) -> StepOutcome:
        tool = self.registry.get(step.tool_name)
        command = self._build_command(tool, step)
        self._enforce_command_policy(command)

        started = time.perf_counter()
        try:
            proc = subprocess.run(
                command,
                cwd=str(self.project_root),
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
            timed_out = False
            stdout = _normalize_text(proc.stdout)
            stderr = _normalize_text(proc.stderr)
            exit_code = proc.returncode
        except subprocess.TimeoutExpired as exc:
            timed_out = True
            stdout = _normalize_text(exc.stdout)
            stderr = _normalize_text(exc.stderr) + '\nTimed out after 30s'
            exit_code = -9
        except OSError as exc:
            raise ToolRunnerError(f'command execution failed: {exc}') from exc

        return StepOutcome(
            exit_code=exit_code,
            stdout=stdout,
            stderr=stderr,
            command=command,
            duration_sec=time.perf_counter() - started,
            timed_out=timed_out,
        )

    def _build_command(self, tool: ToolDefinition, step: PlanStep) -> list[str]:
        if tool.name == 'shell':
            command = step.tool_input.get('command')
            if not isinstance(command, list) or not command or any(not isinstance(item, str) for item in command):
                raise ToolRunnerError('shell tool requires tool_input.command as a string list')
            return command

        script_path = tool.metadata.get('script_path')
        if isinstance(script_path, str) and script_path.strip():
            resolved_script = (self.project_root / script_path).resolve()
            if not resolved_script.exists():
                raise ToolRunnerError(f'script tool path not found: {resolved_script}')
            args = [str(value) for value in step.tool_input.values()]
            return [sys.executable, str(resolved_script), *args]

        if tool.command_template:
            return list(tool.command_template) + [str(value) for value in step.tool_input.values()]

        raise ToolRunnerError(f'tool has no executable command template: {tool.name}')

    def _enforce_command_policy(self, command: list[str]) -> None:
        joined = ' '.join(command).lower()
        if not self.limits.allow_privilege_escalation and (' sudo ' in f' {joined}' or joined.startswith('sudo ')):
            raise ToolRunnerError('privilege escalation is disabled')
        if not self.limits.allow_network:
            blocked = ('curl ', 'wget ', 'ping ', 'ssh ', 'scp ')
            if any(token in f' {joined}' for token in blocked):
                raise ToolRunnerError('network access is disabled by runtime limits')
        if not self.limits.allow_file_write:
            write_tokens = ('>', '>>', 'rm ', 'del ', 'move ', 'copy ')
            if any(token in joined for token in write_tokens):
                raise ToolRunnerError('file-writing commands are disabled by runtime limits')
