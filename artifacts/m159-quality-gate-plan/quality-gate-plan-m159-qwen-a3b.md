# M159 Quality Gate Plan

Policy:

- Speed does not count as progress if response quality regresses.
- Future performance work must be quality-gated before it is considered
  release-ready.

Next quality milestones:

- `M159` quality golden-set harness
- `M160` deterministic quality regression runner
- `M161` cache-enabled vs cache-disabled quality comparison
- `M162` streaming vs non-stream quality parity
- `M163` loop/repetition detector
- `M164` long-context RoPE/IMRoPE quality probe
- `M165` cross-engine Qwen3.6 quality comparison
- `M166` quality-gated performance checkpoint

Required checks:

- golden prompt set for coding, review, reasoning, summarization, JSON/schema,
  long-context recall, refusal boundaries, and RoPE/IMRoPE-sensitive retrieval
- deterministic output capture with stable decode settings
- cache-enabled versus cache-disabled semantic comparison
- streaming versus non-stream final answer comparison
- repeated n-gram, paragraph, code-block, and JSON-loop detection
- long-context retrieval across early, middle, and late context
- comparison against known-good `puma.cpp` / `panthro.cpp` Qwen3.6 behavior

Blocking rule:

- Any optimization touching routing, cache behavior, prompt processing,
  streaming, sampling defaults, tokenizer handling, RoPE/IMRoPE, or KV-cache
  reuse must pass quality gates before being treated as production-ready.
