from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess
import sys


def _capture_first_success(*commands: list[str]) -> str:
    for command in commands:
        try:
            proc = subprocess.run(
                command,
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


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(json.dumps({'ok': False, 'error': 'usage: tool_onboarder.py <tool_name>'}, ensure_ascii=False))
        return 2

    tool_name = str(argv[1]).strip()
    if not tool_name:
        print(json.dumps({'ok': False, 'error': 'tool_name cannot be empty'}, ensure_ascii=False))
        return 2

    resolved = shutil.which(tool_name)
    if not resolved:
        print(json.dumps({'ok': False, 'error': f"tool '{tool_name}' was not found on PATH"}, ensure_ascii=False))
        return 1

    project_root = Path(__file__).resolve().parents[1]
    manifest_root = project_root / 'tool_manifests'
    manifest_root.mkdir(parents=True, exist_ok=True)
    manifest_path = manifest_root / f'{tool_name}.json'

    version_output = _capture_first_success([resolved, '--version'], [resolved, '-V'])
    help_output = _capture_first_success([resolved, '--help'], [resolved, '-h'])

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
    print(json.dumps({'ok': True, 'tool_name': tool_name, 'manifest_path': str(manifest_path)}, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main(sys.argv))
