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
- `M182` operator readiness bundle with quality, memory, and model-swap status
- `M183` UI/TUI contract for consuming operator readiness bundles
- `M184` shared renderer for operator readiness bundle status cards
- `M185` packaged `bin/mlx-engine operator-readiness` command
- `M186` live `/engine/operator-readiness` endpoint
- `M187` live operator readiness endpoint contract probe
- `M188` packaged `bin/mlx-engine operator-readiness-refresh` command
- `M189` model candidate registry
- `M190` lower-memory candidate gate
- `M191` operator UI field map
- `M192` prompt-processing next-target gate with quality threshold
- `M193` milestone completion audit for M186-M193
- `M194` prompt-processing performance report
- `M195` prompt-processing optimization matrix
- `M196` performance budget gate
- `M197` live performance snapshot
- `M198` performance report contract probe
- `M199` performance report renderer
- `M200` next milestone plan
- `M201` performance batch report and completion audit
- `M202` cache lookup fast-path implementation
- `M203` tokenized prompt reuse probe
- `M204` async cache completion wait sweep
- `M205` response metrics trim experiment

Only after the relevant quality gates pass should the engine continue deeper
speed work such as first reusable-turn tuning, cache admission sweeps, transport
overhead reduction, or smaller-model substitution.

## M202 Quality Boundary

M202 is intentionally limited to prefix-lookup bookkeeping:

- exact repeated prompts use an exact token-hash fast path
- near-match prompts still use the existing longest-prefix scan
- cache scope and prompt-cache reuse semantics are unchanged
- the M194 quality threshold baseline remains `PASS`

Artifact:

- `artifacts/m202-cache-lookup-fast-path/cache-lookup-fast-path-m202-qwen-a3b.json`

This keeps the speed work inside the existing quality envelope: no decoding
parameters, prompt-cache mutation behavior, RoPE/IMRoPE handling, or output
quality gates were changed.

## M203 Quality Boundary

M203 caches tokenized prompt IDs only when the normalized prompt and tokenizer
scope match exactly.

Artifact:

- `artifacts/m203-tokenized-prompt-reuse/tokenized-prompt-reuse-m203-qwen-a3b.json`

The probe verifies:

- identical prompts hit the tokenized cache
- returned token lists are copies, so callers cannot mutate cached entries
- tokenizer/template scope changes do not reuse token IDs
- LRU eviction bounds memory growth

This changes prompt preprocessing only; decoding settings, generated output
handling, prompt-cache mutation behavior, and RoPE/IMRoPE behavior are unchanged.

## M204 Quality Boundary

M204 does not alter model output, decoding parameters, or prompt-cache contents.
It only documents and gates a bounded pending wait for duplicate requests when an
async prefix build is already pending.

Artifact:

- `artifacts/m204-async-cache-completion-wait/async-cache-completion-wait-m204-qwen-a3b.json`

The quality boundary is:

- pending waits are conditional on an existing async build
- the recommendation remains bounded at `1000 ms`
- actual prefill after the wait-hit path remains low at `10` tokens
- the source async maturation gate is `PASS`

## M205 Quality Boundary

M205 changes response metadata shape only when clients explicitly request it.
The default response still includes full `engine_metrics`, and diagnostics
workloads force full metrics even if compact mode is requested.

Artifact:

- `artifacts/m205-response-metrics-trim/response-metrics-trim-m205-qwen-a3b.json`

The probe verifies:

- compact metrics drop heavy debug fields
- full metrics preserve the complete row
- off mode omits the metrics payload
- diagnostics workloads force full metrics

No model execution, prompt processing, cache behavior, or decoding quality logic
is changed by this milestone.

## M206 Quality Boundary

M206 is a live regression rerun, not a new decoding or prompt-cache behavior
change.

Artifacts:

- `artifacts/m206-live-performance-suite/live-product-regression-suite-m206-qwen-a3b.json`
- `artifacts/m206-live-performance-suite/quality-threshold-gate-m206-qwen-a3b.json`
- `artifacts/m206-live-performance-suite/quality-checkpoint-m206-qwen-a3b.json`

The live suite verifies:

- deterministic quality regression: `PASS`
- cache quality comparison: `PASS`
- streaming quality parity: `PASS`
- loop/repetition quality gate: `PASS`
- long-context RoPE/IMRoPE quality: `PASS`
- cross-engine quality comparison: `PASS`
- quality threshold gate: `PASS`

This keeps the current speed work inside the quality envelope: performance
changes are acceptable only while deterministic behavior, cache parity,
streaming parity, loop control, and RoPE/IMRoPE checks remain green.

## M209 Quality Boundary

M209 is a report-only milestone. It does not change runtime behavior.

Artifacts:

- `artifacts/m209-performance-delta/prompt-processing-delta-report-m209-qwen-a3b.json`
- `artifacts/m209-performance-delta/milestone-completion-audit-m202-m209.json`
- `artifacts/m206-live-performance-suite/quality-threshold-gate-m206-qwen-a3b.json`

The report keeps quality as a hard constraint:

- live product regression suite: `PASS`
- quality threshold gate: `PASS`
- M202-M209 completion audit: `PASS`

The performance warning is intentional: mature repeated-context latency remains
above target, but quality is still green. Future latency work must continue to
carry these quality gates forward.

## M210 Quality Boundary

M210 changes the repeated-context benchmark's mature-hit selection rule. It does
not change model execution, prompt-cache contents, decoding settings, or
RoPE/IMRoPE behavior.

Artifacts:

- `artifacts/m210-mature-hit-latency/mature-hit-latency-report-m210-qwen-a3b.json`
- `artifacts/m210-mature-hit-latency/quality-threshold-gate-m210-qwen-a3b.json`

Quality result:

- quality threshold gate: `PASS`
- deterministic quality source: M206 deterministic quality artifact
- loop quality source: M206 loop quality artifact

Future M211 model-swap work must run fresh quality acceptance for the candidate
model rather than relying only on M210's report-only quality boundary.

## M211 Quality Boundary

M211 ran fresh candidate quality for `gpt-oss-20b-MXFP4-Q8`.

Artifacts:

- `artifacts/m211-gpt-oss-candidate/deterministic-quality-m211-gpt-oss.json`
- `artifacts/m211-gpt-oss-candidate/model-quality-comparison-m211-gpt-oss.json`
- `artifacts/m211-gpt-oss-candidate/model-swap-acceptance-m211-gpt-oss.json`

Quality result:

- current Qwen deterministic quality source: `PASS`
- candidate deterministic quality: `FAIL`
- candidate deterministic failures: `7`
- model-swap decision: `REJECT`

This is the intended quality gate behavior: a smaller model that loads and
generates is still blocked if coding quality regresses.

## M257 Response Quality Regression Harness

M257 adds a baseline-versus-candidate response-quality comparison harness:

- script: `benchmarks/python/response_quality_regression_harness.py`
- live capture mode: records deterministic completion outputs, quality markers,
  repetition score, visible-thinking state, length, and latency
- comparison mode: fails when the candidate loses required markers, introduces
  task failures, increases repetition beyond threshold, or drops quality points
- performance is reported beside quality, but faster latency does not override a
  quality failure

Commands:

```bash
python3 benchmarks/python/response_quality_regression_harness.py capture \
  --base-url http://127.0.0.1:8773 \
  --model local-mlx \
  --runtime-profile interactive \
  --temperature 0.0 \
  --top-p 1.0 \
  --seed 257 \
  --output-json artifacts/m257-response-quality-regression-harness/baseline.json \
  --output-md artifacts/m257-response-quality-regression-harness/baseline.md \
  --fail-on-fail

python3 benchmarks/python/response_quality_regression_harness.py compare \
  --baseline-json artifacts/m257-response-quality-regression-harness/baseline.json \
  --candidate-json artifacts/m257-response-quality-regression-harness/candidate.json \
  --output-json artifacts/m257-response-quality-regression-harness/response-quality-regression-comparison-m257.json \
  --output-md artifacts/m257-response-quality-regression-harness/response-quality-regression-comparison-m257.md \
  --fail-on-fail
```

Initial non-live verification:

- unit tests: `PASS`
- py_compile: `PASS`
- fixture comparison: `PASS`

Artifacts:

- `artifacts/m257-response-quality-regression-harness/m257-fixture-baseline.json`
- `artifacts/m257-response-quality-regression-harness/m257-fixture-candidate.json`
- `artifacts/m257-response-quality-regression-harness/response-quality-regression-comparison-m257.json`

Next live quality step: capture a baseline from the current accepted engine and
compare future optimization branches against it before promotion.

## M258 Live Response Quality Baseline

M258 captured the first live response-quality baseline from the accepted Qwen
A3B runtime:

- model:
  `/Volumes/StudioStackSSD4TB/Development/LLM/lmstudio/models/unsloth/Qwen3.6-35B-A3B-UD-MLX-4bit`
- endpoint: `http://127.0.0.1:8773`
- engine preset: `memory-saver`
- device: `Device(gpu, 0)`

Baseline result:

- verdict: `PASS`
- cases: `13`
- passed cases: `13`
- quality points: `130/130`
- failures: `0`
- max repetition score: `0.0`
- mean service request: `370.487 ms`

Artifacts:

- `artifacts/m258-live-response-quality-baseline/live-baseline-m258-qwen-a3b.json`
- `artifacts/m258-live-response-quality-baseline/live-baseline-m258-qwen-a3b.md`
- `artifacts/m258-live-response-quality-baseline/live-baseline-self-comparison-m258-qwen-a3b.json`
- `artifacts/m258-live-response-quality-baseline/live-response-quality-baseline-m258.md`

This live baseline is now the comparison anchor for future speed work. A future
candidate may be faster, but it must compare `PASS` against this artifact before
promotion.

## M259 Release Gate Response-Quality Requirement

M259 wires explicit current candidate-vs-baseline response-quality comparison
into the release-blocking quality-preserving gate:

- gate key: `response_quality_regression_candidate`
- category: `response_quality`
- baseline artifact:
  `artifacts/m258-live-response-quality-baseline/live-baseline-m258-qwen-a3b.json`
- current candidate artifact:
  `artifacts/m259-release-gate-response-quality/current-candidate-quality-capture-m259-qwen-a3b.json`
- comparison artifact:
  `artifacts/m259-release-gate-response-quality/current-candidate-vs-baseline-m259-qwen-a3b.json`

The release gate now checks:

- `--response-quality-comparison-json` is supplied
- response-quality comparison verdict is `PASS`
- comparison readiness is `response-quality-regression-ready`
- baseline and candidate both have `13` cases
- baseline and candidate both pass all `13` cases
- baseline and candidate both preserve full quality points
- max repetition score remains `0.0`
- candidate artifact is not the same path as the baseline artifact
- comparison artifact has no failures

M259 release gate result:

- verdict: `PASS`
- gates: `16`
- failures: `0`
- omitted response-quality comparison argument: `FAIL` by design
- current candidate quality points: `130/130`
- current candidate mean service request: `345.282 ms`

Artifacts:

- `artifacts/m259-release-gate-response-quality/current-candidate-quality-capture-m259-qwen-a3b.json`
- `artifacts/m259-release-gate-response-quality/current-candidate-vs-baseline-m259-qwen-a3b.json`
- `artifacts/m259-release-gate-response-quality/quality-preserving-release-gate-m259.json`
- `artifacts/m259-release-gate-response-quality/quality-preserving-release-gate-m259.md`

Future speed work is now blocked by response-quality regression evidence, not
just runtime correctness or performance evidence.

## M260 Response-Quality Release Runner

M260 adds a one-command runner for candidate quality capture, baseline
comparison, and release-gate execution:

- script: `benchmarks/python/run_response_quality_release_gate.py`
- default baseline:
  `artifacts/m258-live-response-quality-baseline/live-baseline-m258-qwen-a3b.json`
- output directory:
  `artifacts/m260-response-quality-release-runner`

Live candidate command:

```bash
python3 benchmarks/python/run_response_quality_release_gate.py \
  --base-url http://127.0.0.1:8773 \
  --output-dir artifacts/m260-response-quality-release-runner \
  --tag m260-response-quality-release-runner \
  --fail-on-fail
```

Existing candidate artifact command:

```bash
python3 benchmarks/python/run_response_quality_release_gate.py \
  --candidate-json artifacts/m259-release-gate-response-quality/current-candidate-quality-capture-m259-qwen-a3b.json \
  --output-dir artifacts/m260-response-quality-release-runner \
  --tag m260-response-quality-release-runner \
  --fail-on-fail
```

M260 runner result:

- verdict: `PASS`
- readiness: `response-quality-release-ready`
- candidate-vs-baseline comparison: `PASS`
- release gate: `PASS`
- release gate count: `16`
- failures: `0`

Artifacts:

- `artifacts/m260-response-quality-release-runner/response-quality-release-runner-m260-response-quality-release-runner.json`
- `artifacts/m260-response-quality-release-runner/candidate-vs-baseline-m260-response-quality-release-runner.json`
- `artifacts/m260-response-quality-release-runner/quality-preserving-release-gate-m260-response-quality-release-runner.json`

This removes the manual artifact-plumbing step introduced in M259.
