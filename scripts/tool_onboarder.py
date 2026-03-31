from __future__ import annotations

import json
from pathlib import Path
import shutil
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from loa_v3.tool_introspection import build_cli_metadata, capture_first_output


def _onboard_one(tool_name: str, project_root: Path) -> dict[str, object]:
    resolved = shutil.which(tool_name)
    if not resolved:
        return {'ok': False, 'tool_name': tool_name, 'error': f"tool '{tool_name}' was not found on PATH"}

    manifest_root = project_root / 'tool_manifests'
    manifest_root.mkdir(parents=True, exist_ok=True)
    manifest_path = manifest_root / f'{tool_name}.json'

    version_probe = capture_first_output([resolved, '--version'], [resolved, '-V'], [resolved, 'version'])
    help_probe = capture_first_output([resolved, '--help'], [resolved, '-h'], [resolved, 'help'])
    version_output = str(version_probe.get('output', ''))
    help_output = str(help_probe.get('output', ''))

    metadata = build_cli_metadata(
        tool_name=tool_name,
        resolved_path=resolved,
        help_output=help_output,
        version_output=version_output,
        probes={
            'version_command': version_probe.get('command', []),
            'help_command': help_probe.get('command', []),
        },
    )

    manifest_payload = {
        'name': tool_name,
        'tool_type': 1,
        'description': f'CLI tool manifest for {tool_name}.',
        'command_template': [tool_name],
        'metadata': metadata,
    }
    manifest_path.write_text(json.dumps(manifest_payload, ensure_ascii=False, indent=2), encoding='utf-8')
    return {'ok': True, 'tool_name': tool_name, 'manifest_path': str(manifest_path)}


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(json.dumps({'ok': False, 'error': 'usage: tool_onboarder.py <tool_name> [tool_name ...]'}, ensure_ascii=False))
        return 2

    tool_names = [str(item).strip() for item in argv[1:] if str(item).strip()]
    if not tool_names:
        print(json.dumps({'ok': False, 'error': 'at least one tool name is required'}, ensure_ascii=False))
        return 2

    project_root = Path(__file__).resolve().parents[1]
    results = [_onboard_one(tool_name, project_root) for tool_name in tool_names]
    success = all(bool(item.get('ok')) for item in results)
    payload = {
        'ok': success,
        'requested_tools': tool_names,
        'results': results,
    }
    print(json.dumps(payload, ensure_ascii=False))
    return 0 if success else 1


if __name__ == '__main__':
    raise SystemExit(main(sys.argv))
