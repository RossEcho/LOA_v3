from __future__ import annotations

import json
from pathlib import Path
import shutil
import sys

from loa_v3.types import ToolDefinition


GENERIC_CLI_USAGE_HINT = (
    'Generic CLI tool. Use metadata.input_contract to supply required positional values '
    'and honor metadata.execution.safe_default_flags when the tool is long-running by default.'
)


def _enrich_tool_metadata(tool: ToolDefinition) -> ToolDefinition:
    metadata = dict(tool.metadata)
    if tool.tool_type == 1 and 'input_contract' not in metadata:
        metadata['input_contract'] = {'arg_1': 'string'}
    if tool.tool_type == 1 and 'argument_order' not in metadata:
        metadata['argument_order'] = list((metadata.get('input_contract') or {}).keys())
    if tool.tool_type == 1 and 'required_args' not in metadata:
        metadata['required_args'] = list((metadata.get('input_contract') or {}).keys())
    if tool.tool_type == 1 and 'optional_args' not in metadata:
        metadata['optional_args'] = []
    if tool.tool_type == 1 and 'platform_variants' not in metadata:
        metadata['platform_variants'] = []
    if tool.tool_type == 1 and 'execution' not in metadata:
        metadata['execution'] = {
            'long_running_by_default': False,
            'safe_default_flags': [],
        }
    if tool.tool_type == 1 and 'usage_hint' not in metadata:
        metadata['usage_hint'] = GENERIC_CLI_USAGE_HINT
    if tool.tool_type == 2 and 'usage_hint' not in metadata:
        metadata['usage_hint'] = 'Script tool with structured inputs defined in metadata.input_contract.'
    return ToolDefinition(
        name=tool.name,
        tool_type=tool.tool_type,
        description=tool.description,
        command_template=list(tool.command_template),
        metadata=metadata,
        manifest_path=tool.manifest_path,
    )


class ToolRegistry:
    def __init__(self, project_root: Path) -> None:
        self.project_root = project_root
        self._tools: dict[str, ToolDefinition] = {}
        self._register_builtin_tools()
        self._load_script_manifests()

    def reload(self) -> None:
        self._tools = {}
        self._register_builtin_tools()
        self._load_script_manifests()

    def _register_builtin_tools(self) -> None:
        self._tools['shell'] = ToolDefinition(
            name='shell',
            tool_type=0,
            description='Master shell tool for controlled local commands.',
            command_template=[],
            metadata={'restricted': True},
        )
        self._tools['python'] = ToolDefinition(
            name='python',
            tool_type=1,
            description='Python CLI tool metadata entry.',
            command_template=[sys.executable],
            metadata={
                'detected': sys.executable,
                'version': sys.version.split()[0],
                'help_hint': '--help',
                'input_contract': {'arg_1': 'string'},
                'argument_order': ['arg_1'],
                'required_args': ['arg_1'],
                'optional_args': [],
                'platform_variants': [sys.platform],
                'execution': {
                    'long_running_by_default': False,
                    'safe_default_flags': [],
                },
                'usage_hint': GENERIC_CLI_USAGE_HINT,
            },
        )

    def _load_script_manifests(self) -> None:
        manifest_root = self.project_root / 'tool_manifests'
        if not manifest_root.exists():
            return
        for path in sorted(manifest_root.glob('*.json')):
            payload = json.loads(path.read_text(encoding='utf-8-sig'))
            tool = ToolDefinition(
                name=payload['name'],
                tool_type=int(payload['tool_type']),
                description=payload['description'],
                command_template=list(payload.get('command_template', [])),
                metadata=dict(payload.get('metadata', {})),
                manifest_path=str(path),
            )
            self._tools[payload['name']] = _enrich_tool_metadata(tool)

    def list_tools(self) -> list[ToolDefinition]:
        return [self._tools[name] for name in sorted(self._tools)]

    def get(self, name: str) -> ToolDefinition:
        if name not in self._tools:
            raise KeyError(f'unknown tool: {name}')
        return self._tools[name]

    def build_planning_metadata(self) -> list[dict]:
        return [tool.to_dict() for tool in self.list_tools()]

    def detect_cli_tool(self, command_name: str) -> dict[str, str | bool]:
        resolved = shutil.which(command_name)
        return {
            'name': command_name,
            'detected': bool(resolved),
            'path': resolved or '',
        }
