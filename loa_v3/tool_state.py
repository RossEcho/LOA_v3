from __future__ import annotations

from dataclasses import asdict, dataclass, field
import os
import shutil
from typing import Any

from loa_v3.tool_introspection import capture_first_output
from loa_v3.types import ToolDefinition


@dataclass(slots=True)
class ToolState:
    name: str
    tool_type: int
    detected: bool
    manifest_present: bool
    resolved_path: str
    recorded_path: str
    path_matches: bool
    version_recorded: bool
    version_matches: bool | None
    metadata_complete: bool
    ready: bool
    needs_onboarding: bool
    stale: bool
    reasons: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _version_preview_for(tool: ToolDefinition, resolved_path: str, metadata: dict[str, Any]) -> tuple[bool, bool | None]:
    recorded_preview = str(metadata.get('version_preview') or '').strip()
    if not recorded_preview:
        return False, None

    stored_probes = metadata.get('help_probe') or {}
    candidate_commands: list[list[str]] = []
    for key in ('version_command', 'help_command'):
        raw = stored_probes.get(key) or []
        if isinstance(raw, list) and raw:
            command = [resolved_path if index == 0 else str(part) for index, part in enumerate(raw)]
            candidate_commands.append(command)
    candidate_commands.extend([
        [resolved_path, '--version'],
        [resolved_path, '-V'],
        [resolved_path, 'version'],
    ])
    probe = capture_first_output(*candidate_commands, timeout=4)
    current_preview = str(probe.get('output') or '').strip()[:200]
    if not current_preview:
        return True, None
    return True, current_preview == recorded_preview


def _metadata_quality_reasons(metadata: dict[str, Any]) -> list[str]:
    reasons: list[str] = []
    if not metadata.get('input_contract'):
        reasons.append('manifest lacks input_contract')
    if not metadata.get('argument_order'):
        reasons.append('manifest lacks argument_order')
    if not metadata.get('required_args'):
        reasons.append('manifest lacks required_args')
    execution = metadata.get('execution')
    if not isinstance(execution, dict):
        reasons.append('manifest lacks execution metadata')
    else:
        if 'long_running_by_default' not in execution:
            reasons.append('manifest lacks long_running_by_default metadata')
        if 'safe_default_flags' not in execution:
            reasons.append('manifest lacks safe_default_flags metadata')
    if not metadata.get('usage_hint'):
        reasons.append('manifest lacks usage_hint')
    if not metadata.get('help_probe') and not metadata.get('help_preview'):
        reasons.append('manifest lacks help-derived probe metadata')
    return reasons


def _same_path(left: str, right: str) -> bool:
    if not left or not right:
        return left == right
    return os.path.normcase(left) == os.path.normcase(right)


def evaluate_tool_state(tool: ToolDefinition) -> ToolState:
    metadata = dict(tool.metadata or {})
    manifest_present = bool(tool.manifest_path)
    resolved_path = shutil.which(tool.name) or ''
    recorded_path = str(metadata.get('path') or '')
    path_matches = not recorded_path or _same_path(recorded_path, resolved_path)
    detected = bool(resolved_path)
    version_recorded, version_matches = _version_preview_for(tool, resolved_path, metadata) if detected else (bool(metadata.get('version_preview')), None)
    metadata_quality_reasons = _metadata_quality_reasons(metadata) if manifest_present and tool.tool_type == 1 else []

    reasons: list[str] = []
    if tool.tool_type != 1:
        reasons.append('tool_state is primarily meaningful for CLI tools')
    if not detected:
        reasons.append('command not found on PATH')
    if not manifest_present:
        reasons.append('no manifest present')
    if detected and not path_matches:
        reasons.append('resolved path differs from recorded manifest path')
    if version_recorded and version_matches is False:
        reasons.append('current version preview differs from recorded manifest version preview')
    reasons.extend(metadata_quality_reasons)

    metadata_complete = not metadata_quality_reasons
    ready = bool(
        tool.tool_type == 1
        and detected
        and manifest_present
        and path_matches
        and version_matches is not False
        and metadata_complete
    )
    stale = bool(manifest_present and (not path_matches or version_matches is False or not metadata_complete))
    needs_onboarding = bool(tool.tool_type == 1 and (not ready))

    return ToolState(
        name=tool.name,
        tool_type=int(tool.tool_type),
        detected=detected,
        manifest_present=manifest_present,
        resolved_path=resolved_path,
        recorded_path=recorded_path,
        path_matches=path_matches,
        version_recorded=version_recorded,
        version_matches=version_matches,
        metadata_complete=metadata_complete,
        ready=ready,
        needs_onboarding=needs_onboarding,
        stale=stale,
        reasons=reasons,
    )
