# LOA_v2 -> LOA_v3 Migration Note

## Keep

- `llama-server` as the primary backend using the OpenAI-compatible chat completions endpoint.
- Deterministic request controls: `seed`, `temperature`, `max_tokens`, timeout.
- JSON-only prompt envelopes with explicit requirements.
- Defensive recovery of the first valid JSON object from model output.
- Session-style logging as a first-class runtime behavior.

## Discard

- Mixed planning, execution, decision, and response logic in one runtime loop.
- Hard-coded prompt strings embedded across runtime modules.
- Tight coupling between plan validation and one specific tool registry shape.
- Large control-flow files that are difficult to debug or replace incrementally.

## Reframe For LOA_v3

- Planner returns structured `Plan` data only.
- Tool selector and tool runner are separate from planning.
- Evaluator determines completion and replanning signals.
- Reporter owns the final natural-language answer.
- Logger owns user summary, execution log, decision log, and debug trace.
- Model access sits behind a model client interface so `llama-server` remains swappable.
