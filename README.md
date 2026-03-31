# LOA_v3

LOA_v3 is a Linux-first semi-autonomous local operations agent.

It is being shaped as a practical machine-side operator for cybersecurity, system inspection, and controlled tool execution, with a strong focus on bounded autonomy, debuggability, and low-resource hardware support. The current real-world test target is a rooted Android running Termux.

## Project Direction

The intended end state is closer to a semi-autonomous agent than a simple prompt-to-command wrapper.

LOA_v3 is meant to:

- receive a user goal
- reason about what information and tools are needed
- inspect local capabilities and tool state
- build a structured plan
- execute bounded steps through a controlled runtime
- evaluate progress and anomalies after each step
- replan when needed
- produce a final natural-language report backed by logs

The design target is:

- Linux-first runtime behavior
- Windows-compatible development workflow
- usable on both low-end and high-end hardware
- explicit control over network, privilege, file, and tool usage
- reliable structured planning instead of free-form hidden state

## Current Runtime Reality

LOA_v3 is already functional, but it is still early in its agent lifecycle.

What it does well today:

- model-backed structured planning through `llama-server`
- bounded tool execution with logging and evaluation
- CLI tool onboarding through help/version inspection
- manifest-based tool cataloging
- debug traces that make planner and execution behavior inspectable

What is still evolving:

- stronger replanning loops
- richer tool-state freshness checks
- better handling for long-running and interactive tools
- tighter low-token prompt design for weaker local models
- more robust cyber/security-oriented capability groups

## Model Constraints

The current working model is intentionally modest:

- `Qwen2.5-1.5B-Instruct-Q4_K_M.gguf`

That model is useful for lightweight structured planning, but it is not strong enough to carry large rolling prompts reliably. Because of that, LOA_v3 is moving toward a pulse-based prompt strategy:

- many smaller prompts
- compact structured state between phases
- logged evidence instead of one ever-growing conversation
- selective retrieval of only the context needed for the next decision

Functionality comes first. Prompt and runtime optimization follow after the behavior is correct.

## Core Goals

- Keep planning, execution, evaluation, reporting, and logging as separate modules.
- Use structured plan data instead of free-form planning text.
- Keep `llama-server` as the primary model backend behind a clean client interface.
- Support bounded autonomy with explicit limits and stop conditions.
- Keep Linux and Termux behavior as the primary runtime truth.
- Make debugging easy with traceable decisions, session logs, and raw planner exchanges.
- Build toward a cyber-operations-oriented local agent instead of a generic assistant shell.

## What Was Reused From LOA_v2

Only stable, useful pieces were carried forward:

- `llama-server` through the OpenAI-compatible `POST /v1/chat/completions` endpoint
- deterministic request settings such as `seed`, `temperature`, `timeout`, and `max_tokens`
- JSON-oriented prompt envelopes for planning and reporting
- defensive extraction of valid structured output from imperfect model responses

## What Was Intentionally Changed

LOA_v3 does not reuse the LOA_v2 architecture directly.

Important changes in the rewrite:

- prompts are stored on disk and loaded through a prompt registry
- planning is separated from execution
- tool selection is separated from tool execution
- evaluation and reporting are separate phases
- logging is its own concern instead of being mixed into control flow
- onboarding writes manifests so CLI tools can be reused consistently
- the runtime is built for future privilege, network, file, and device controls

## Architecture

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
  scripts/
  tests/
  tool_manifests/
  main.py
```

## Module Responsibilities

- `app.py`: local menu UX for tests, settings, conversation flow, debug mode, and log handling
- `orchestrator.py`: top-level runtime coordinator
- `planner.py`: structured planning and planner-side normalization
- `tool_selector.py`: validates that planned tools are known and allowed
- `tool_runner.py`: executes CLI and script tools under runtime restrictions
- `evaluator.py`: decides whether the run completed, failed, or needs replanning
- `reporter.py`: builds the final user-facing report
- `logger.py`: writes summary, execution, decision, and debug logs per session
- `model_client.py`: model abstraction and structured output extraction
- `llama_server_client.py`: concrete `llama-server` integration
- `config_loader.py`: settings loading and runtime/model construction
- `prompt_registry.py`: prompt loading and rendering from disk
- `tool_registry.py`: tool metadata, manifest loading, and registry refresh logic
- `types.py`: shared runtime data structures

## Runtime Flow

The intended orchestration flow is:

1. receive the user goal
2. inspect runtime settings, capabilities, and tool state
3. create a structured plan
4. validate tool references
5. execute steps through the controlled runner
6. log each decision and execution result
7. evaluate completion and anomalies
8. replan when needed
9. generate a final report

The current implementation already covers a working vertical slice of this loop.

## Tool System

LOA_v3 is structured around three tool categories:

- Type 0: master tools such as shell-level execution primitives
- Type 1: CLI tools discovered from the local system and described through manifests
- Type 2: script tools backed by manifests or structured descriptions

CLI onboarding is based on probing the tool with help/version commands such as `-h` or `--help`, then storing structured metadata including:

- path and basic identity
- input contract
- optional flags
- safe default flags
- long-running behavior hints
- platform variants when detectable

The long-term goal is for the agent to reason from tool capabilities and state, not from hardcoded command shortcuts.

## Menu

Run the project with:

```bash
python main.py
```

Menu options currently include:

1. `Tests`
2. `Settings`
3. `Conversation flow`
4. `Debug mode`
5. `Exit`

The local operator workflow is meant to stay simple and debuggable, especially on constrained hardware.

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

Relevant runtime settings include:

- `max_steps`
- `command_timeout_sec`
- `allow_network`
- future privilege and execution controls

Relevant environment overrides are also supported for the `llama-server` path inherited from LOA_v2:

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

These logs are not just debug noise. They are part of the intended memory and evidence trail for future pulse-based reasoning.

## Tests

Run the test suite with:

```bash
python -m pytest tests -q -p no:cacheprovider
```

The current tests cover:

- prompt loading
- settings loading
- planner behavior and normalization
- tool onboarding and manifest handling
- tool runner behavior
- fallback and logging behavior

## Near-Term Roadmap

The most important next steps are:

- move from heavier single prompts toward pulse-based prompting
- add better tool freshness and readiness checks before onboarding
- improve evaluator and replanning behavior
- add better handling for long-running, interactive, and privileged tools
- group tools around cyber/Linux capabilities such as recon, package, process, filesystem, and device operations
- decide whether `SmarTar` becomes part of the memory layer, stays a separate script tool, or is removed
