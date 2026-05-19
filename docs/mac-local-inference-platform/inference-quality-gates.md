# Inference Quality Gates

Speed does not count as progress if response quality regresses.

This document defines the quality gates that must run alongside future MLX
prompt-processing and generation performance work.

## Rule

Any optimization that changes routing, cache behavior, prompt processing,
streaming, sampling defaults, context handling, tokenizer handling, RoPE,
IMRoPE, or KV-cache reuse must pass quality gates before it can be marked
production-ready.

Performance milestones may pass as engineering checkpoints, but they are not
release-ready until quality gates also pass.

## Required Gates

### Golden Prompt Set

Create a fixed prompt set covering:

- coding task execution
- code review
- reasoning
- summarization
- instruction following
- JSON/schema output
- long-context recall
- refusal/safety boundary behavior
- repeated workspace context
- RoPE/IMRoPE-sensitive long-context retrieval

Expected output should be rubric-based rather than exact text matching.

### Deterministic Regression Mode

Run quality probes with stable generation settings:

- fixed model
- fixed prompt
- fixed seed where supported
- low temperature or deterministic decode
- fixed max tokens
- fixed stop conditions

The gate should record:

- output text
- token counts
- stop reason
- repetition score
- schema validity
- rubric result
- cache mode
- runtime profile
- streaming mode

### Cache Correctness Gate

For each relevant prompt:

- run with cache disabled or bypassed
- run with cache enabled
- compare semantic output, stop reason, repetition rate, and task success

The cache path must not:

- drop context
- mix prior request state
- hallucinate missing context
- loop
- truncate early
- change schema validity

### Streaming Parity Gate

For OpenAI-compatible completion/chat routes:

- run non-stream
- run stream
- compare final text and quality metadata

Streaming must not degrade response quality or omit stop/usage/metrics fields
needed by the operator surface.

### Loop And Repetition Gate

Detect:

- repeated n-grams
- repeated paragraphs
- repeated code blocks
- repeated JSON keys/objects
- runaway filler
- failure to stop
- excessive refusal boilerplate

This gate should fail hard for loop signatures even if latency improves.

### Long-Context RoPE/IMRoPE Gate

Use prompts that place facts at:

- early context
- middle context
- late context
- repeated distractor context

The model must retrieve the correct facts after prompt-processing, cache reuse,
and route/profile changes.

### Cross-Engine Quality Comparison

For Qwen3.6 quality-sensitive prompts, compare MLX output against known-good
`puma.cpp` and `panthro.cpp` behavior where available.

The comparison is not an exact text match. It should check:

- task success
- retrieval accuracy
- hallucination rate
- repetition rate
- stop behavior
- schema validity
- long-context stability

## Blocking Milestones

The next milestone lane should change from performance-only to quality-gated
performance:

- `M159` quality golden-set harness
- `M160` deterministic quality regression runner
- `M161` cache-enabled vs cache-disabled quality comparison
- `M162` streaming vs non-stream quality parity
- `M163` loop/repetition detector
- `M164` long-context RoPE/IMRoPE quality probe
- `M165` cross-engine Qwen3.6 quality comparison
- `M166` quality-gated performance checkpoint
- `M167` quality gates inside the live product regression suite
- `M168` operator-facing quality status summary
- `M169` expanded coding-agent golden prompts
- `M170` model-to-model quality comparison before model swaps
- `M171` operator/TUI quality bundle
- `M172` coding-agent workspace/edit/test/debug golden prompts
- `M173` CI-style quality threshold output
- `M175` expanded live product regression suite with M172/M173 integrated
- `M176` model/profile swap acceptance gate
- `M177` per-request active memory metrics for lower-memory gates
- `M178` live proof of per-request memory metrics
- `M179` one-command model swap artifact workflow
- `M180` live product regression suite using request-local memory metrics
- `M181` live resident model swap lifecycle probe

Only after the relevant quality gates pass should the engine continue deeper
speed work such as first reusable-turn tuning, cache admission sweeps, transport
overhead reduction, or smaller-model substitution.
