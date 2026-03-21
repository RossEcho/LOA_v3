from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess
import time

from loa_v3.tool_registry import ToolRegistry
from loa_v3.types import PlanStep, RuntimeLimits, StepOutcome, ToolDefinition


class ToolRunnerError(RuntimeError):
    pass


class ToolRunner:
    def __init__(self, project_root: Path, registry: ToolRegistry, limits: RuntimeLimits) -> None:
        self.project_root = project_root
        self.registry = registry
        self.limits = limits

    def run_step(self, step: PlanStep) -> StepOutcome:
        tool = self.registry.get(step.tool_name)
        if tool.name == 'tool_manager':
            return self._run_tool_manager(step)

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
            stdout = proc.stdout
            stderr = proc.stderr
            exit_code = proc.returncode
        except subprocess.TimeoutExpired as exc:
            timed_out = True
            stdout = exc.stdout or ''
            stderr = (exc.stderr or '') + '\nTimed out after 30s'
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

    def _run_tool_manager(self, step: PlanStep) -> StepOutcome:
        operation = str(step.tool_input.get('operation') or '').strip().lower()
        if operation != 'register_cli':
            raise ToolRunnerError(f'unsupported tool_manager operation: {operation}')

        tool_name = str(step.tool_input.get('tool_name') or '').strip()
        if not tool_name:
            raise ToolRunnerError('tool_manager register_cli requires tool_name')

        started = time.perf_counter()
        resolved = shutil.which(tool_name)
        if not resolved:
            raise ToolRunnerError(f"tool '{tool_name}' was not found on PATH")

        version_output = self._capture_first_success([resolved, '--version'], [resolved, '-V'])
        help_output = self._capture_first_success([resolved, '--help'], [resolved, '-h'])

        manifest_root = self.project_root / 'tool_manifests'
        manifest_root.mkdir(parents=True, exist_ok=True)
        manifest_path = manifest_root / f'{tool_name}.json'
        manifest_payload = {
            'name': tool_name,
            'tool_type': 1,
            'description': f'CLI tool manifest for {tool_name}.',
            'command_template': [tool_name],
            'metadata': {
                'detected': True,
                'path': resolved,
                'version_preview': version_output[:200],
                'help_preview': help_output[:400],
            },
        }
        manifest_path.write_text(json.dumps(manifest_payload, ensure_ascii=False, indent=2), encoding='utf-8')

        stdout = json.dumps({'ok': True, 'tool_name': tool_name, 'manifest_path': str(manifest_path)}, ensure_ascii=False)
        return StepOutcome(
            exit_code=0,
            stdout=stdout,
            stderr='',
            command=['internal:tool_manager', 'register_cli', tool_name],
            duration_sec=time.perf_counter() - started,
            timed_out=False,
        )

    def _capture_first_success(self, *commands: list[str]) -> str:
        for command in commands:
            try:
                proc = subprocess.run(
                    command,
                    cwd=str(self.project_root),
                    capture_output=True,
                    text=True,
                    timeout=10,
                    check=False,
                )
            except OSError:
                continue
            if proc.returncode == 0:
                output = (proc.stdout or proc.stderr or '').strip()
                if output:
                    return output
        return ''

    def _build_command(self, tool: ToolDefinition, step: PlanStep) -> list[str]:
        if tool.name == 'shell':
            command = step.tool_input.get('command')
            if not isinstance(command, list) or not command or any(not isinstance(item, str) for item in command):
                raise ToolRunnerError('shell tool requires tool_input.command as a string list')
            return command

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
