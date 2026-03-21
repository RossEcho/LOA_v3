from __future__ import annotations

import json
from pathlib import Path
import shutil
import sys

from loa_v3.types import ToolDefinition


class ToolRegistry:
    def __init__(self, project_root: Path) -> None:
        self.project_root = project_root
        self._tools: dict[str, ToolDefinition] = {}
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
            },
        )

    def _load_script_manifests(self) -> None:
        manifest_root = self.project_root / 'tool_manifests'
        if not manifest_root.exists():
            return
        for path in sorted(manifest_root.glob('*.json')):
            payload = json.loads(path.read_text(encoding='utf-8-sig'))
            self._tools[payload['name']] = ToolDefinition(
                name=payload['name'],
                tool_type=int(payload['tool_type']),
                description=payload['description'],
                command_template=list(payload.get('command_template', [])),
                metadata=dict(payload.get('metadata', {})),
                manifest_path=str(path),
            )

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
