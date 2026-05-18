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

The package directory contains:

- the suite manifest
- existing referenced artifacts
- `resident-suite-evidence-index.json`
- missing artifact references when optional steps were skipped

## Dax Operator Workflow

Open the Dax MLX panel:

```bash
cd /Users/jeffreycruz/Development/AI_AGENTS/dax-stereo
npm --prefix packages/coding-agent run build
node packages/coding-agent/dist/cli.js mlx-engine \
  --base-url http://127.0.0.1:8773 \
  --interactive
```

Inside the panel:

```text
/bench summary /Users/jeffreycruz/Development/LLM_INFERENCE/mlx/.worktrees/prompt-processing-bench/artifacts/m64-real-suite/resident-regression-suite-m64-qwen-a3b.json
```

Run a bounded suite from Dax:

```text
/bench run /Users/jeffreycruz/Development/LLM_INFERENCE/mlx/.worktrees/prompt-processing-bench /private/tmp/dax-resident-suite dax-qwen-a3b
```

Dax will run the resident suite, write artifacts, then summarize the generated
manifest in the operator panel.

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
  --presets sync-safe,async-experimental
```

This runs the same benchmark under each preset and attaches a cache-create
optimization report for each result.

Dry-run the planned commands without touching the engine:

```bash
python3 benchmarks/python/runtime_profile_comparison_suite.py \
  --dry-run \
  --output-dir /private/tmp/m69-profile-suite \
  --tag dryrun \
  --presets sync-safe,async-experimental \
  --base-url http://127.0.0.1:8773
```

## Calibrate Regression Thresholds

```bash
python3 benchmarks/python/calibrate_resident_thresholds.py \
  artifacts/m64-real-suite/resident-regression-gate-m64-qwen-a3b.json \
  --output-json artifacts/m64-real-suite/resident-threshold-calibration-m64-qwen-a3b.json
```

Apply the emitted threshold flags to future `run_resident_regression_suite.py`
runs after enough repeated evidence exists for the target model and preset.

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

The next engine optimization should reduce foreground cache-create cost:

- prefer async/deferred prefix construction for cache candidates
- deduplicate pending builds for duplicate or near-duplicate prompts
- keep cache-hit correctness and suffix-only prefill as non-negotiable gates
- compare presets through `runtime_profile_comparison_suite.py`
- recalibrate thresholds after each stable model/preset baseline
