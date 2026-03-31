from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any


def capture_first_output(*commands: list[str], timeout: int = 10) -> dict[str, Any]:
    for command in commands:
        try:
            proc = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            continue
        output = (proc.stdout or proc.stderr or '').strip()
        if output:
            return {
                'command': command,
                'return_code': proc.returncode,
                'output': output,
            }
    return {
        'command': [],
        'return_code': None,
        'output': '',
    }


def _sanitize_name(raw: str, index: int) -> str:
    value = raw.strip().strip('<>[](){}').strip().casefold()
    value = re.sub(r'[^a-z0-9]+', '_', value).strip('_')
    if not value:
        return f'arg_{index}'
    if value[0].isdigit():
        value = f'arg_{index}_{value}'
    return value


def _extract_usage_line(help_output: str) -> str:
    for line in help_output.splitlines():
        stripped = line.strip()
        if stripped.casefold().startswith('usage:'):
            return stripped.split(':', 1)[1].strip()
    return ''


def infer_input_contract(tool_name: str, help_output: str) -> dict[str, str]:
    usage_line = _extract_usage_line(help_output)
    if not usage_line:
        return {'arg_1': 'string'}

    command_tokens = {tool_name.casefold(), Path(tool_name).name.casefold()}
    positionals: list[str] = []

    explicit_placeholders = re.findall(r'<[^>]+>', usage_line)
    for token in explicit_placeholders:
        positionals.append(token)

    if not positionals:
        cleaned_usage = re.sub(r'\[[^\]]*\]', ' ', usage_line)
        tokens = re.findall(r'\b[A-Z][A-Z0-9_-]*\b|\b[a-zA-Z][a-zA-Z0-9_.:-]*\b', cleaned_usage)
        for token in tokens:
            lowered = token.casefold()
            if lowered in command_tokens or lowered in {'usage', 'options', 'option'}:
                continue
            if token.startswith('-'):
                continue
            if token.isupper():
                positionals.append(token)

    if not positionals:
        return {'arg_1': 'string'}

    contract: dict[str, str] = {}
    for index, token in enumerate(positionals, start=1):
        name = _sanitize_name(token, index)
        if name in contract:
            name = f'{name}_{index}'
        contract[name] = 'string'
    return contract

def extract_option_specs(help_output: str) -> list[dict[str, Any]]:
    specs: list[dict[str, Any]] = []
    for line in help_output.splitlines():
        stripped = line.rstrip()
        if not stripped.lstrip().startswith('-'):
            continue
        parts = re.split(r'\s{2,}', stripped.strip(), maxsplit=1)
        option_part = parts[0]
        description = parts[1].strip() if len(parts) > 1 else ''
        flags = re.findall(r'--?[A-Za-z0-9][A-Za-z0-9-]*', option_part)
        if not flags:
            continue
        value_match = re.search(r'(--?[A-Za-z0-9][A-Za-z0-9-]*)(?:[ =]+([A-Z][A-Z0-9_-]*|<[^>]+>|\[[^\]]+\]))', option_part)
        takes_value = bool(value_match)
        value_name = value_match.group(2) if value_match else ''
        specs.append({
            'flags': flags,
            'takes_value': takes_value,
            'value_name': value_name.strip('<>[]').casefold() if value_name else '',
            'description': description,
        })
    return specs


def infer_safe_default_flags(option_specs: list[dict[str, Any]], help_output: str) -> list[str]:
    help_text = help_output.casefold()
    count_keywords = (
        'count',
        'number of requests',
        'number of packets',
        'packets to transmit',
        'stop after',
        'exit after',
    )
    for spec in option_specs:
        description = str(spec.get('description', '')).casefold()
        if not spec.get('takes_value'):
            continue
        if any(keyword in description for keyword in count_keywords):
            flags = spec.get('flags') or []
            if flags:
                return [str(flags[0]), '4']
    if 'until stopped' in help_text or 'until interrupted' in help_text:
        for spec in option_specs:
            description = str(spec.get('description', '')).casefold()
            if 'count' in description and spec.get('takes_value'):
                flags = spec.get('flags') or []
                if flags:
                    return [str(flags[0]), '4']
    return []


def infer_long_running_by_default(help_output: str, safe_default_flags: list[str]) -> bool:
    text = help_output.casefold()
    if safe_default_flags:
        return True
    long_running_markers = (
        'until stopped',
        'until interrupted',
        'continuous',
        'repeatedly',
        'forever',
    )
    return any(marker in text for marker in long_running_markers)


def detect_platform_variants(resolved_path: str, help_output: str) -> list[str]:
    variants: list[str] = []
    platform_name = sys.platform.casefold()
    variants.append(platform_name)
    prefix = os.environ.get('PREFIX', '').casefold()
    path_text = str(resolved_path).casefold()
    if 'termux' in prefix or 'com.termux' in path_text:
        variants.append('termux')
    if os.name == 'nt':
        variants.append('windows')
    elif platform_name.startswith('linux'):
        variants.append('linux')
    elif platform_name == 'darwin':
        variants.append('macos')

    help_text = help_output.casefold()
    if '-n' in help_text and 'windows' not in variants and 'icmp echo requests' in help_text:
        variants.append('windows_like_cli')
    return list(dict.fromkeys(variants))


def build_cli_metadata(tool_name: str, resolved_path: str, help_output: str, version_output: str, probes: dict[str, Any]) -> dict[str, Any]:
    input_contract = infer_input_contract(tool_name, help_output)
    option_specs = extract_option_specs(help_output)
    safe_default_flags = infer_safe_default_flags(option_specs, help_output)
    long_running_by_default = infer_long_running_by_default(help_output, safe_default_flags)
    required_args = list(input_contract.keys())
    optional_args = [spec for spec in option_specs if spec.get('flags')]
    positional_arg_names = required_args if required_args != ['arg_1'] else []
    usage_hint = 'Generic CLI tool.'
    if positional_arg_names:
        usage_hint = 'CLI tool requiring positional inputs: ' + ', '.join(positional_arg_names) + '.'
    elif required_args:
        usage_hint = 'Generic CLI tool. Use the declared input_contract keys to supply positional values.'

    return {
        'detected': True,
        'path': resolved_path,
        'version_preview': version_output[:200],
        'help_preview': help_output[:1200],
        'help_probe': probes,
        'input_contract': input_contract,
        'argument_order': required_args,
        'required_args': required_args,
        'optional_args': optional_args,
        'platform_variants': detect_platform_variants(resolved_path, help_output),
        'usage_hint': usage_hint,
        'execution': {
            'long_running_by_default': long_running_by_default,
            'safe_default_flags': safe_default_flags,
        },
    }
