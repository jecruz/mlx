# MLX Operator Readiness UI Contract

This document defines the file-based readiness bundle that UI, TUI, Dax, Prowl,
or future operator surfaces should consume when showing MLX engine readiness.

Validated by:

- `benchmarks/python/operator_readiness_bundle.py`
- `benchmarks/python/operator_readiness_contract_probe.py`
- `benchmarks/python/operator_readiness_render.py`

Current artifact:

- `artifacts/m182-operator-readiness/operator-readiness-bundle-m182-qwen-a3b.json`

Current contract probe:

- `artifacts/m183-operator-readiness-contract/operator-readiness-contract-m183-qwen-a3b.json`

Current renderer artifacts:

- `artifacts/m184-operator-readiness-render/operator-readiness-render-m184-qwen-a3b.json`
- `artifacts/m184-operator-readiness-render/operator-readiness-render-m184-qwen-a3b.txt`

## Scope

The readiness bundle is not a replacement for `/engine/ui`. Use `/engine/ui`
for live engine controls and instantaneous runtime state. Use the readiness
bundle when an operator surface needs the current release-quality answer:

- Is the active model ready?
- Did quality gates pass?
- Did the live product suite pass?
- Did lower-memory gating use request-local memory metrics?
- Is live model reload/restore safe?
- Is the tested candidate model accepted or blocked?

## Top-Level Shape

Required fields:

- `type`: must be `operator_readiness_bundle`.
- `tag`: milestone or run tag.
- `verdict`: `PASS` or `FAIL`.
- `readiness`: `operator-readiness-ready` or `operator-readiness-blocked`.
- `status_card`: compact status values for UI badges.
- `runtime`: current live runtime summary from `/engine/ui`.
- `model_decision`: active/candidate model decision.
- `memory`: lower-memory gate summary.
- `evidence`: source artifact paths.
- `warnings`: non-blocking warnings.
- `failures`: blocking failures.

## Status Card

Required `status_card` keys:

- `runtime`
- `quality`
- `live_suite`
- `lower_memory`
- `memory_source`
- `live_model_swap`
- `candidate_swap`

Each value is one of:

- `PASS`: safe/ready.
- `WARN`: visible operator warning, but not a release blocker.
- `FAIL`: release or runtime blocker.

Current expected M182 status:

```json
{
  "runtime": "PASS",
  "quality": "PASS",
  "live_suite": "PASS",
  "lower_memory": "PASS",
  "memory_source": "PASS",
  "live_model_swap": "PASS",
  "candidate_swap": "WARN"
}
```

`candidate_swap=WARN` is acceptable when the active model remains ready and the
candidate was intentionally rejected by the model-swap workflow.

## Runtime

Required `runtime` fields:

- `base_url`
- `ok`
- `loaded`
- `model`
- `backend`
- `engine_preset`
- `runtime_profile`
- `strategy`
- `gpu_ready`
- `warm`
- `can_generate`
- `can_reload`
- `can_unload`

UI guidance:

- Show `runtime.model` as the active model path.
- Show `engine_preset`, `runtime_profile`, and `strategy` as advanced details.
- Treat `can_generate=false` or `gpu_ready=false` as blocking.
- Treat `warm=false` as a warning unless `verdict=FAIL`.

## Model Decision

Required `model_decision` fields:

- `current_label`
- `active_model`
- `candidate_label`
- `candidate_model`
- `swap_decision`
- `readiness`
- `blockers`

Rendering guidance:

- If `swap_decision=ACCEPT`, the candidate is eligible for promotion.
- If `swap_decision=REJECT`, keep the active model and show blockers.
- A rejected candidate is not a runtime failure when `verdict=PASS`.

Current M182 decision:

- active model: `Qwen3.6-35B-A3B-UD-MLX-4bit`
- candidate model: `Qwen3.6-27B-UD-MLX-4bit`
- swap decision: `REJECT`
- blocker: candidate speed

## Memory

Required `memory` fields:

- `source`
- `max_active_memory_gb`
- `max_peak_memory_gb`
- `health_active_memory_gb`

Expected source:

- `request_metrics`

UI guidance:

- Prefer `max_active_memory_gb` for lower-memory readiness.
- Keep `max_peak_memory_gb` as diagnostic context only.
- If `source` is not `request_metrics`, show a warning or fail the contract
  depending on the surface.

## Evidence

Required `evidence` keys:

- `suite_json`
- `operator_quality_json`
- `model_swap_workflow_json`
- `lower_memory_json`
- `live_model_swap_json`

UI guidance:

- Keep evidence paths clickable where possible.
- Do not recompute readiness in the UI from every source artifact unless the
  operator explicitly opens a details view.
- Use the bundle's `verdict`, `readiness`, `status_card`, `warnings`, and
  `failures` as the primary display contract.

## Minimal UI Layout

Recommended compact display:

- Header: `MLX Operator Readiness: PASS`
- Active model: `runtime.model`
- Runtime badges: `runtime`, `quality`, `live_suite`, `lower_memory`
- Memory badge: `memory_source`, plus `max_active_memory_gb`
- Model swap badge: `candidate_swap`
- Warnings section: list `warnings`
- Failures section: list `failures`

## Shared Renderer

Clients that only need a terminal or compact card view can use the shared
renderer instead of formatting the readiness bundle directly:

```bash
python3 benchmarks/python/operator_readiness_render.py \
  --bundle-json artifacts/m182-operator-readiness/operator-readiness-bundle-m182-qwen-a3b.json \
  --output-json artifacts/m184-operator-readiness-render/operator-readiness-render-m184-qwen-a3b.json \
  --output-text artifacts/m184-operator-readiness-render/operator-readiness-render-m184-qwen-a3b.txt \
  --format text \
  --fail-on-fail
```

The text output is intentionally stable and compact:

```text
MLX Operator Readiness: PASS
operator-readiness-ready | Qwen3.6-35B-A3B-UD-MLX-4bit
runtime=PASS quality=PASS live_suite=PASS lower_memory=PASS memory_source=PASS live_model_swap=PASS candidate_swap=WARN
profile=interactive preset=async-experimental strategy=split_prefill_or_async_build
memory=request_metrics active=21.02259841GB peak=22.31961337GB
active=Qwen3.6-35B-A3B-UD-MLX-4bit candidate=Qwen3.6-27B-UD-MLX-4bit swap=REJECT
```

The JSON renderer output provides the same normalized display strings plus the
model names, memory values, warnings, failures, and swap blockers.

## Validation Command

```bash
python3 benchmarks/python/operator_readiness_contract_probe.py \
  --bundle-json artifacts/m182-operator-readiness/operator-readiness-bundle-m182-qwen-a3b.json \
  --output-json artifacts/m183-operator-readiness-contract/operator-readiness-contract-m183-qwen-a3b.json \
  --tag m183-qwen-a3b \
  --fail-on-fail
```

Expected result:

- `operator_readiness_contract_probe PASS`
- readiness: `operator-readiness-contract-ready`
- failures: `0`
