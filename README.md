# LOA_v3

LOA_v3 is a local LLM-focused tool orchestrator built as a clean rewrite of LOA_v2.
It is designed to reason about a user request, produce a structured plan, execute bounded local actions, evaluate outcomes, and return a final natural-language report with detailed logs.

## Goals

- Keep planning, execution, evaluation, reporting, and logging as separate modules.
- Use structured plan data instead of free-form planning text.
- Keep `llama-server` as the primary model backend behind a clean client interface.
- Support bounded autonomy with explicit limits and stop conditions.
- Stay Linux-first while remaining practical to develop and test on Windows.
- Make debugging easy with traceable decisions and per-session logs.

## Current Status

The current scaffold implements the first working vertical slice:

1. accept a user prompt
2. build a structured plan
3. validate tool availability
4. execute a minimal step flow with runtime controls
5. evaluate completion and anomalies
6. write logs
7. produce a final report

The planner is model-backed, but there is also a deterministic fallback planner so the flow remains testable even if `llama-server` is offline.

## What Was Reused From LOA_v2

The rewrite keeps a few ideas from LOA_v2 because they were useful and stable:

- `llama-server` through the OpenAI-compatible `POST /v1/chat/completions` endpoint
- deterministic request settings such as `seed`, `temperature`, `timeout`, and `max_tokens`
- JSON-oriented prompt envelopes for planner and reporter interactions
- defensive extraction of the first valid JSON object from model output

## What Was Intentionally Changed

LOA_v3 does not reuse the old architecture directly.
Instead, it changes the design in a few important ways:

- prompts are stored on disk and loaded through a prompt registry
- planning is separated from execution
- tool selection is separated from tool execution
- evaluation and reporting are separate phases
- logging is its own concern instead of being mixed into control flow
- the runtime is built for future autonomy controls such as privilege, file, and network limits

## Project Structure

```text
LOA_v3/
  config/
    defaults.json
    settings.json
  docs/
    migration_note.md
    structure.md
  loa_v3/
    app.py
    config_loader.py
    evaluator.py
    llama_server_client.py
    logger.py
    model_client.py
    orchestrator.py
    planner.py
    prompt_registry.py
    reporter.py
    tool_registry.py
    tool_runner.py
    tool_selector.py
    types.py
  prompts/
    planner_prompt.txt
    report_prompt.txt
  tests/
  tool_manifests/
  main.py
```

## Module Responsibilities

- `app.py`: menu entrypoint and local UX for tests, settings, conversation flow, and debug mode
- `orchestrator.py`: top-level runtime coordinator
- `planner.py`: planner interface, model-backed planner, and deterministic fallback planner
- `tool_selector.py`: verifies that planned tools are known and allowed
- `tool_runner.py`: executes tool commands under runtime restrictions
- `evaluator.py`: decides whether the run completed successfully or needs replanning
- `reporter.py`: builds the final natural-language report
- `logger.py`: writes user summary, execution log, decision log, and debug trace
- `model_client.py`: model abstraction and JSON extraction logic
- `llama_server_client.py`: concrete `llama-server` integration
- `config_loader.py`: settings loading and runtime/model construction
- `prompt_registry.py`: prompt loading and rendering from disk
- `tool_registry.py`: tool metadata for master tools, CLI tools, and script tools
- `types.py`: shared runtime data structures

## Runtime Flow

The intended orchestration flow is:

1. receive user prompt
2. inspect runtime settings and available tools
3. create a structured plan
4. validate tool references
5. execute steps through the controlled runner
6. log each decision and execution result
7. evaluate completion and anomalies
8. replan when needed
9. generate a final report

The current implementation covers the minimal working version of that flow and leaves room for a richer replanning loop.

## Tool Model

LOA_v3 is structured around three tool categories:

- Type 0: master tools such as shell-level execution primitives
- Type 1: CLI tools with structured metadata and future help/version parsing support
- Type 2: script tools backed by manifests or structured descriptions

The current registry includes:

- `shell` as the master execution tool
- `python` as a CLI metadata entry
- `echo_script` as an example manifest-backed script tool

## Menu

Run the project with:

```bash
python main.py
```

Menu options:

1. `Tests`
2. `Settings`
3. `Conversation flow`
4. `Debug mode`
5. `Exit`

## Configuration

Default settings live in `config/defaults.json` and local overrides live in `config/settings.json`.

Important model settings include:

- `endpoint`
- `model_name`
- `timeout_sec`
- `max_tokens`
- `temperature`
- `seed`
- `use_schema`

Relevant environment overrides are also supported for the `llama-server` path used in LOA_v2:

- `LOA_LLAMA_SERVER_URL`
- `LOA_LLAMA_SERVER_MODEL`
- `LOA_LLM_TIMEOUT_SEC`
- `LOA_LLM_MAX_TOKENS`
- `LOA_TEMP`
- `LOA_SEED`

## Logging

Each run creates a session directory under `runs/` and writes:

- `user_summary.log`
- `execution_log.jsonl`
- `decision_log.jsonl`
- `debug_trace.jsonl`

These logs are meant to support both quick inspection and future richer debugging tools.

## Tests

Run the test suite with:

```bash
python -m pytest tests -q -p no:cacheprovider
```

The current scaffold includes tests for:

- prompt loading
- settings loading
- fallback orchestration flow
- tool registry coverage across the three tool types

## Roadmap

Near-term next steps for LOA_v3:

- implement richer planner schemas and plan validation
- expand the tool registry and structured tool metadata
- add real continuation and replanning behavior
- add stronger runtime restrictions for files, network, and privilege use
- improve the reporter with model-backed final summaries
- add Linux-first command presets while keeping Windows development support

## Notes

- LOA_v2 was used as reference only for `llama-server` integration details, request settings, and prompt-formatting patterns.
- LOA_v3 is a rewrite, not a refactor.
- Existing workspace projects are intentionally kept separate from this new repo.
