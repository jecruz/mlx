# Resident MLX Operator Runbook

This runbook captures the current M64-M70 resident-engine workflow for local
operator validation on a Mac with MLX GPU access.

## Assumptions

- Worktree:
  `/Users/jeffreycruz/Development/LLM_INFERENCE/mlx/.worktrees/prompt-processing-bench`
- Dax repo:
  `/Users/jeffreycruz/Development/AI_AGENTS/dax-stereo`
- Resident engine URL:
  `http://127.0.0.1:8773`
- Current bounded Qwen test model:
  `/Volumes/StudioStackSSD4TB/Development/LLM/lmstudio/models/unsloth/Qwen3.6-35B-A3B-UD-MLX-4bit`

## Start Or Verify The Engine

Use a terminal context that has permission to read the external model volume.
Detached tmux server processes may not have that permission.

```bash
cd /Users/jeffreycruz/Development/LLM_INFERENCE/mlx/.worktrees/prompt-processing-bench
MODEL="/Volumes/StudioStackSSD4TB/Development/LLM/lmstudio/models/unsloth/Qwen3.6-35B-A3B-UD-MLX-4bit"
bin/mlx-engine serve --model "$MODEL" --port 8773
```

Readiness check:

```bash
bin/mlx-engine ready \
  --base-url http://127.0.0.1:8773 \
  --require-gpu \
  --require-warmup
```

Expected readiness characteristics:

- `Device(gpu, 0)`
- `metal_available=true`
- resident model loaded
- warmup complete when warmed latency matters

## Product Client Request Metadata

Product clients should send workload intent on the request body instead of
changing global runtime profile before each request.

Contract:

- `docs/mac-local-inference-platform/request-metadata-client-contract.md`

Minimal completion example:

```json
{
  "model": "local-mlx",
  "prompt": "Summarize this workspace context.",
  "max_tokens": 128,
  "workload_intent": "first-hit",
  "immediate_second_turn": true
}
```

Expected `engine_metrics` fields:

- `request_runtime_profile`
- `request_runtime_profile_source=request_metadata`
- `request_runtime_profile_applied=true`

Manual `runtime_profile` remains the highest-priority operator override.

## Run The Bounded Regression Suite

```bash
python3 benchmarks/python/run_resident_regression_suite.py \
  --base-url http://127.0.0.1:8773 \
  --output-dir artifacts/m64-real-suite \
  --tag m64-qwen-a3b \
  --requests 3 \
  --prefill-runs 3 \
  --prefix-repeats 8 \
  --max-tokens 6 \
  --prefill-max-tokens 2 \
  --max-cache-hit-service-ms 300 \
  --max-cache-hit-prefill-tokens 16 \
  --max-cache-create-service-ms 900 \
  --max-cache-create-prepare-share 0.85 \
  --max-warm-prefill-service-ms 5000 \
  --min-warm-prefill-tokens 80 \
  --max-cold-to-warm-ratio 30 \
  --min-cache-hit-speedup-vs-full-prefill 4 \
  --min-cache-hit-prefill-reduction-vs-full-prefill 0.90 \
  --skip-generated-cache-safety \
  --skip-generated-cache-edges \
  --skip-concurrent-cancel-pressure \
  --skip-async-cache-priority \
  --print-manifest-summary
```

Primary outputs:

- `resident-benchmark-sync-safe-<tag>.jsonl`
- `resident-prefill-isolation-sync-safe-<tag>.jsonl`
- `resident-regression-gate-<tag>.json`
- `resident-regression-suite-<tag>.json`

## Run The Dax Product-Path Gate

Use this when the target is the product-facing Dax coding-agent path rather
than the lower-level resident benchmark harness:

```bash
python3 benchmarks/python/run_resident_regression_suite.py \
  --base-url http://127.0.0.1:8773 \
  --output-dir artifacts/m86-dax-suite-product-path \
  --tag m86-qwen-a3b-dax-product \
  --skip-benchmarks \
  --skip-compare \
  --skip-gate \
  --skip-generated-cache-safety \
  --skip-generated-cache-edges \
  --skip-concurrent-cancel-pressure \
  --skip-async-cache-priority \
  --include-dax-repeated-context \
  --print-manifest-summary
```

Product-path outputs:

- `dax-repeated-context-<tag>.jsonl`
- `dax-repeated-context-<tag>.json`
- `dax-repeated-context-gate-<tag>.json`
- `resident-regression-suite-<tag>.json`

The suite manifest embeds `dax_repeated_context_report` and
`dax_repeated_context_gate_report`. The summary prints
`dax_repeated_context_gate PASS|FAIL` separately from the lower-level
resident regression gate.

## Summarize A Suite Manifest

```bash
python3 benchmarks/python/summarize_resident_suite_manifest.py \
  artifacts/m64-real-suite/resident-regression-suite-m64-qwen-a3b.json \
  --fail-on-fail
```

Use this in CI or local gates when the suite manifest already exists.

## Package Evidence

```bash
python3 benchmarks/python/package_resident_suite_evidence.py \
  artifacts/m64-real-suite/resident-regression-suite-m64-qwen-a3b.json \
  --output-dir /private/tmp/mlx-m64-evidence-package
```

Package the Dax product-path suite evidence:

```bash
python3 benchmarks/python/package_resident_suite_evidence.py \
  artifacts/m86-dax-suite-product-path/resident-regression-suite-m86-qwen-a3b-dax-product.json \
  --output-dir artifacts/m87-dax-product-evidence-package
```

The package directory contains:

- the suite manifest
- existing referenced artifacts
- `resident-suite-evidence-index.json`
- missing artifact references when optional steps were skipped

For product-path suites, the index also includes `dax_repeated_context` with
the benchmark verdict, gate verdict, hit count, speedup, prefill reduction, and
best-hit service latency.

## Dax Operator Workflow

Open the Dax MLX panel:

```bash
cd /Users/jeffreycruz/Development/AI_AGENTS/dax-stereo
npm --prefix packages/coding-agent run build
node packages/coding-agent/dist/cli.js mlx-engine \
  --base-url http://127.0.0.1:8773 \
  --interactive
```

Generation routing:

- `--prompt` and `--interactive` send per-request metadata to MLX.
- Without `--intent`, those generation paths default to
  `workload_intent=coding-agent`, `agentic_workload=true`, and
  `repeated_workspace=true`.
- `--intent first-hit`, `--intent low-memory`, `--intent interactive`, and
  `--intent diagnostics` are request-level product hints for generation.
- `--product-mode chat|coding-agent|coding-agent-first-hit|coding-agent-low-memory|diagnostics`
  is the product-facing shortcut for those request-level hints.
- `--profile <name>` with generation is sent as a request-level
  `runtime_profile` override.
- status-only `--profile` and `--intent` still mutate `/engine/config` for
  operator control.
- interactive `/profile` remains a deliberate global runtime-profile override.

Live Dax request-metadata smoke:

```bash
node packages/coding-agent/dist/cli.js mlx-engine \
  --base-url http://127.0.0.1:8773 \
  --prompt "M128 Dax request metadata artifact. Reply with one short sentence." \
  --max-tokens 8 \
  --json
```

Expected `engine_metrics`:

- `request_runtime_profile_source=request_metadata`
- `request_runtime_profile_applied=true`
- `workload_intent=coding-agent`
- `agentic_workload=true`
- `repeated_workspace=true`

Inside the panel:

```text
/bench summary /Users/jeffreycruz/Development/LLM_INFERENCE/mlx/.worktrees/prompt-processing-bench/artifacts/m64-real-suite/resident-regression-suite-m64-qwen-a3b.json
```

Inspect runtime profile comparison evidence:

```text
/bench profiles /Users/jeffreycruz/Development/LLM_INFERENCE/mlx/.worktrees/prompt-processing-bench/artifacts/m73-profile-comparison/runtime-profile-comparison-qwen-a3b-m73b.json
```

Run a bounded suite from Dax:

```text
/bench run /Users/jeffreycruz/Development/LLM_INFERENCE/mlx/.worktrees/prompt-processing-bench /private/tmp/dax-resident-suite dax-qwen-a3b
```

Dax will run the resident suite, write artifacts, then summarize the generated
manifest in the operator panel.

Run the product-path Dax repeated-context suite from Dax:

```text
/bench run product /Users/jeffreycruz/Development/LLM_INFERENCE/mlx/.worktrees/prompt-processing-bench /private/tmp/dax-product-suite dax-qwen-a3b-product
```

This maps to the resident suite's `--include-dax-repeated-context` mode and
prints the product gate verdict plus cache-hit speedup, prefill reduction, and
best-hit latency in the operator panel.

## Cache-Create Optimization Probe

```bash
python3 benchmarks/python/cache_create_optimization_probe.py \
  artifacts/m64-real-suite/resident-benchmark-sync-safe-m64-qwen-a3b.jsonl \
  --output-json artifacts/m64-real-suite/cache-create-optimization-m64-qwen-a3b.json \
  --min-prepare-share 0.40 \
  --fail-on-fail
```

Use this to decide whether the next performance target is foreground cache
preparation. A high prepare share means async/deferred prefix construction is
the right direction.

## Runtime Profile Comparison

```bash
python3 benchmarks/python/runtime_profile_comparison_suite.py \
  --base-url http://127.0.0.1:8773 \
  --output-dir artifacts/profile-comparison \
  --tag qwen-a3b-profile-sweep \
  --presets sync-safe,async-experimental,request-derived
```

This runs the same benchmark under each preset and attaches a cache-create
optimization report for each result.

Gate a profile comparison result:

```bash
python3 benchmarks/python/runtime_profile_comparison_gate.py \
  artifacts/m73-profile-comparison/runtime-profile-comparison-qwen-a3b-m73b.json \
  --include-presets sync-safe \
  --output-json artifacts/m73-profile-comparison/runtime-profile-comparison-gate-qwen-a3b-m73b.json \
  --fail-on-fail
```

Package profile comparison evidence:

```bash
python3 benchmarks/python/package_runtime_profile_evidence.py \
  artifacts/m73-profile-comparison/runtime-profile-comparison-qwen-a3b-m73b.json \
  --gate-report artifacts/m73-profile-comparison/runtime-profile-comparison-gate-qwen-a3b-m73b.json \
  --output-dir artifacts/m77-runtime-profile-evidence
```

Dry-run the planned commands without touching the engine:

```bash
python3 benchmarks/python/runtime_profile_comparison_suite.py \
  --dry-run \
  --output-dir /private/tmp/m69-profile-suite \
  --tag dryrun \
  --presets sync-safe,async-experimental,request-derived \
  --base-url http://127.0.0.1:8773
```

## Calibrate Regression Thresholds

```bash
python3 benchmarks/python/calibrate_resident_thresholds.py \
  artifacts/m64-real-suite/resident-regression-gate-m64-qwen-a3b.json \
  --output-json artifacts/m64-real-suite/resident-threshold-calibration-m64-qwen-a3b.json
```

Apply the emitted threshold flags to future `run_resident_regression_suite.py`
runs after enough repeated evidence exists for the target model and preset, or
pass the calibration JSON directly:

```bash
python3 benchmarks/python/run_resident_regression_suite.py \
  --base-url http://127.0.0.1:8773 \
  --output-dir artifacts/calibrated-suite \
  --tag qwen-a3b-calibrated \
  --threshold-calibration-json artifacts/m64-real-suite/resident-threshold-calibration-m64-qwen-a3b.json \
  --print-manifest-summary
```

## Current M64 Baseline

M64 bounded Qwen A3B baseline:

- suite verdict: `PASS`
- gate verdict: `PASS`
- gate checks: `11`
- gate failures: `0`
- `cache_hit` mean service: `236.74 ms`
- `cache_hit` speedup versus full prefill: `17.98x`
- `cache_create` mean service: `420.22 ms`
- `cache_create` prepare share: `43.9%`
- `cache_create` deferred-service estimate: `235.55 ms`

## Next Performance Target

The next engine optimization should make async cache construction useful for
the next related request:

- tune `prefix_cache_async_idle_grace_ms`
- tune `prefix_cache_pending_wait_ms`
- prove async turns scheduled builds into real cache hits
- keep cache-hit correctness and suffix-only prefill as non-negotiable gates
- compare presets through `runtime_profile_comparison_suite.py`
- recalibrate thresholds after each stable model/preset baseline

See:

- `docs/mac-local-inference-platform/next-performance-target.md`

## Dax Product-Mode Smoke Commands

Run these from `/Users/jeffreycruz/Development/AI_AGENTS/dax-stereo` while the
resident MLX server is listening on `127.0.0.1:8773`.

```bash
node packages/coding-agent/dist/cli.js mlx-engine \
  --base-url http://127.0.0.1:8773 \
  --product-mode chat \
  --prompt "Reply with a one sentence chat response." \
  --json

node packages/coding-agent/dist/cli.js mlx-engine \
  --base-url http://127.0.0.1:8773 \
  --product-mode coding-agent \
  --prompt "Summarize the current coding-agent route." \
  --json

node packages/coding-agent/dist/cli.js mlx-engine \
  --base-url http://127.0.0.1:8773 \
  --product-mode coding-agent-first-hit \
  --prompt "Summarize the first-hit workspace route." \
  --json

node packages/coding-agent/dist/cli.js mlx-engine \
  --base-url http://127.0.0.1:8773 \
  --product-mode coding-agent-low-memory \
  --prompt "Summarize the low-memory workspace route." \
  --json

node packages/coding-agent/dist/cli.js mlx-engine \
  --base-url http://127.0.0.1:8773 \
  --product-mode diagnostics \
  --prompt "Return the diagnostics route in one sentence." \
  --json
```

Automated smoke gate:

```bash
python3 benchmarks/python/dax_product_mode_smoke.py \
  --base-url http://127.0.0.1:8773 \
  --output-json artifacts/m148-dax-product-mode-smoke/dax-product-mode-smoke-m148-qwen-a3b.json \
  --tag m148-qwen-a3b \
  --fail-on-fail
```

## Operator Visibility Fields

The operator/TUI surface should display these request fields when present:

- `request_runtime_profile`
- `request_runtime_profile_source`
- `request_runtime_profile_applied`
- `request_runtime_profile_scoped`
- `workload_intent`
- `actual_prefill_tokens`
- `cached_prefix_tokens`
- `cache_hit`
- `cache_created`
- `cache_scheduled`
- `cache_population_mode`
- `service_request_ms`
- `scheduler_queue_wait_ms`
- `engine_lock_wait_ms`
- `prompt_progress_total_tokens`
- `prompt_progress_processed_tokens`
- `peak_memory_gb`

## Live Quality-Gated Suite

Run the live product suite with integrated quality gates:

```bash
python3 benchmarks/python/run_live_product_regression_suite.py \
  --base-url http://127.0.0.1:8773 \
  --output-dir artifacts/m167-live-quality-regression-suite \
  --tag m167-qwen-a3b \
  --turns 3 \
  --shared-repeats 48 \
  --max-tokens 3 \
  --prompt-tokens 512 \
  --prompt-sweep-max-tokens 1 \
  --fail-on-fail
```

Expected result:

- `live_product_regression_suite PASS`
- `23` artifacts
- `0` failures
- quality checkpoint: `PASS`

Create an operator-facing quality summary:

```bash
python3 benchmarks/python/quality_status_summary.py \
  --suite-json artifacts/m167-live-quality-regression-suite/live-product-regression-suite-m167-qwen-a3b.json \
  --output-json artifacts/m168-quality-status/quality-status-m168-qwen-a3b.json \
  --tag m168-qwen-a3b \
  --fail-on-fail
```

Create the operator/TUI quality bundle:

```bash
python3 benchmarks/python/operator_quality_bundle.py \
  --base-url http://127.0.0.1:8773 \
  --quality-summary-json artifacts/m168-quality-status/quality-status-m168-qwen-a3b.json \
  --model-comparison-json artifacts/m170-model-quality-comparison/model-quality-comparison-m170-qwen.json \
  --output-json artifacts/m171-operator-quality-bundle/operator-quality-bundle-m171-qwen-a3b.json \
  --output-md artifacts/m171-operator-quality-bundle/operator-quality-bundle-m171-qwen-a3b.md \
  --tag m171-qwen-a3b \
  --fail-on-fail
```

The bundle is the preferred compact surface for operator UI:

- `status_card.engine`
- `status_card.gpu`
- `status_card.warmup`
- `status_card.quality`
- `status_card.model_comparison`
- `runtime.model`
- `runtime.runtime_profile`
- `runtime.cache_strategy`
- `models[].active`
- `models[].verdict`
- `models[].mean_quality_gate_ms`
- `warnings[]`

Create a CI-style quality threshold gate:

```bash
python3 benchmarks/python/quality_threshold_gate.py \
  --quality-artifact artifacts/m172-coding-agent-golden-set/deterministic-quality-m172-qwen-a3b.json \
  --quality-artifact artifacts/m172-coding-agent-golden-set/loop-quality-m172-qwen-a3b.json \
  --operator-bundle-json artifacts/m171-operator-quality-bundle/operator-quality-bundle-m171-qwen-a3b.json \
  --output-json artifacts/m173-quality-threshold-gate/quality-threshold-gate-m173-qwen-a3b.json \
  --tag m173-qwen-a3b \
  --allow-warnings \
  --fail-on-fail
```

The threshold gate is intended for automation. It fails when:

- any quality artifact verdict is not `PASS`
- artifact-level or row-level failures are present
- required markers are missing
- visible thinking appears
- repetition exceeds the configured threshold
- the operator quality bundle is not ready
- engine, GPU, suite quality, or model comparison status is not `PASS`

Run the expanded live regression suite:

```bash
python3 benchmarks/python/run_live_product_regression_suite.py \
  --base-url http://127.0.0.1:8773 \
  --output-dir artifacts/m175-live-expanded-quality-suite \
  --tag m175-qwen-a3b \
  --turns 3 \
  --shared-repeats 48 \
  --max-tokens 3 \
  --prompt-tokens 512 \
  --prompt-sweep-max-tokens 1 \
  --fail-on-fail
```

Expected result:

- `live_product_regression_suite PASS`
- `24` artifacts
- `0` failures
- `quality_threshold_gate PASS`

Lower-memory note:

- When `--base-url` is passed, `lower_memory_runtime_gate.py` checks current
  active MLX memory from `/health`. Historical `peak_memory_gb` remains
  diagnostic because peak memory can reflect earlier model reloads in the same
  process.

Run the model swap acceptance gate:

```bash
python3 benchmarks/python/model_swap_acceptance_gate.py \
  --model-comparison-json artifacts/m170-model-quality-comparison/model-quality-comparison-m170-qwen.json \
  --quality-threshold-json artifacts/m175-live-expanded-quality-suite/quality-threshold-gate-m175-qwen-a3b.json \
  --current-label qwen35b-a3b-ud-4bit \
  --candidate-label qwen27b-ud-4bit \
  --output-json artifacts/m176-model-swap-acceptance/model-swap-acceptance-m176-qwen27b.json \
  --output-md artifacts/m176-model-swap-acceptance/model-swap-acceptance-m176-qwen27b.md \
  --tag m176-qwen27b
```

Acceptance policy:

- quality comparison must pass
- CI quality threshold must pass
- current quality must pass
- candidate quality must pass
- candidate quality-gate latency must not be slower than the active model unless
  the operator intentionally changes `--max-candidate-slowdown-ratio`

The gate can return a successful report with `swap_decision=REJECT`; use
`--fail-on-reject` when automation should exit non-zero for blocked swaps.

Validate per-request memory metric wiring:

```bash
python3 benchmarks/python/request_memory_metrics_static_probe.py \
  --output-json artifacts/m177-request-memory-metrics/request-memory-metrics-static-probe-m177-qwen-a3b.json \
  --tag m177-qwen-a3b \
  --fail-on-fail
```

Expected request metric fields after the resident server is restarted onto this
commit:

- `active_memory_gb`
- `active_memory_bytes`
- `cache_memory_gb`
- `cache_memory_bytes`
- `mlx_peak_memory_gb`
- `peak_memory_bytes`

Compatibility note:

- Existing live server processes started before this commit will not emit these
  fields. `lower_memory_runtime_gate.py --base-url ...` still falls back to
  `/health` for those older processes.

Run the live memory metric probe after restarting the resident server:

```bash
python3 benchmarks/python/request_memory_metrics_live_probe.py \
  --base-url http://127.0.0.1:8773 \
  --output-json artifacts/m178-request-memory-live/request-memory-metrics-live-probe-m178-qwen-a3b.json \
  --tag m178-qwen-a3b \
  --fail-on-fail
```

Expected result:

- `request_memory_metrics_live_probe PASS`
- non-stream `engine_metrics` include all request memory fields
- stream final `engine_metrics` include all request memory fields

Run the model swap workflow:

```bash
python3 benchmarks/python/model_swap_workflow.py \
  --current-label qwen35b-a3b-ud-4bit \
  --current-model /Volumes/StudioStackSSD4TB/Development/LLM/lmstudio/models/unsloth/Qwen3.6-35B-A3B-UD-MLX-4bit \
  --current-artifact artifacts/m170-model-quality-comparison/current-a3b/deterministic-quality-m170-current-a3b.json \
  --current-artifact artifacts/m170-model-quality-comparison/current-a3b/cache-quality-m170-current-a3b.json \
  --current-artifact artifacts/m170-model-quality-comparison/current-a3b/long-context-quality-m170-current-a3b.json \
  --current-artifact artifacts/m170-model-quality-comparison/current-a3b/loop-quality-m170-current-a3b.json \
  --candidate-label qwen27b-ud-4bit \
  --candidate-model /Volumes/StudioStackSSD4TB/Development/LLM/lmstudio/models/unsloth/Qwen3.6-27B-UD-MLX-4bit \
  --candidate-artifact artifacts/m170-model-quality-comparison/qwen27b-ud-4bit/deterministic-quality-m170-qwen27b-ud-4bit.json \
  --candidate-artifact artifacts/m170-model-quality-comparison/qwen27b-ud-4bit/cache-quality-m170-qwen27b-ud-4bit.json \
  --candidate-artifact artifacts/m170-model-quality-comparison/qwen27b-ud-4bit/long-context-quality-m170-qwen27b-ud-4bit.json \
  --candidate-artifact artifacts/m170-model-quality-comparison/qwen27b-ud-4bit/loop-quality-m170-qwen27b-ud-4bit.json \
  --quality-artifact artifacts/m175-live-expanded-quality-suite/deterministic-quality-m175-qwen-a3b.json \
  --quality-artifact artifacts/m175-live-expanded-quality-suite/loop-quality-m175-qwen-a3b.json \
  --operator-bundle-json artifacts/m171-operator-quality-bundle/operator-quality-bundle-m171-qwen-a3b.json \
  --output-dir artifacts/m179-model-swap-workflow \
  --tag m179-qwen27b \
  --allow-warnings
```

Expected result:

- `model_swap_workflow PASS`
- `swap_decision=REJECT` for the tested 27B dense candidate
- the blocker should be `candidate_speed`
