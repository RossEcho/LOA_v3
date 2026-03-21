# LOA_v3 Structure

- `loa_v3/orchestrator.py`: coordinates the end-to-end runtime.
- `loa_v3/planner.py`: model-backed planner plus deterministic fallback planner.
- `loa_v3/tool_selector.py`: narrows execution to allowed/known tools.
- `loa_v3/tool_registry.py`: master, CLI, and script tool registration.
- `loa_v3/tool_runner.py`: controlled subprocess execution and step-level results.
- `loa_v3/evaluator.py`: checks completion, failures, no-progress conditions, and replan need.
- `loa_v3/reporter.py`: produces the final user-facing report.
- `loa_v3/logger.py`: writes summary, execution, decision, and debug logs.
- `loa_v3/model_client.py`: abstract model client interface and JSON extraction helper.
- `loa_v3/llama_server_client.py`: concrete llama-server implementation.
- `loa_v3/config_loader.py`: local settings/default loading.
- `loa_v3/prompt_registry.py`: loads prompts from disk by key.
- `loa_v3/app.py`: menu entrypoint, settings flow, tests hook, and conversation mode.
