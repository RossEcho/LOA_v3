# LOA_v3

`LOA_v3` is a clean rewrite of the local LLM orchestrator focused on:

- explicit module boundaries
- structured planning data
- controlled tool execution
- rich per-step logging
- llama-server as the primary model backend

## What carried over from LOA_v2

- `llama-server` via `POST /v1/chat/completions`
- deterministic request settings such as `seed`, `temperature`, and `max_tokens`
- strict JSON-oriented prompt envelopes
- defensive JSON extraction from model output

## What changed on purpose

- planning, selection, execution, evaluation, reporting, and logging are now isolated modules
- prompts live in a registry on disk instead of being scattered through runtime code
- tools are typed and described through a dedicated registry layer
- the runtime has explicit autonomy bounds and stop conditions
- a deterministic fallback planner keeps the basic flow testable without a live model

## Quick start

```bash
python main.py
```
# LOA_v3
