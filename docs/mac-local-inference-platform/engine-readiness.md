# MLX Engine Readiness

This checklist captures the current operator-facing readiness surface for the
resident MLX engine work through M23.

## Runtime Target

- Model:
  `/Volumes/StudioStackSSD4TB/Development/LLM/lmstudio/models/unsloth/Qwen3.6-35B-A3B-UD-MLX-4bit`
- Server:
  `bin/mlx-engine serve --model <model> --port 8773 --warmup-mode async --require-gpu`
- Expected device:
  `Device(gpu, 0)` with Metal available
- Tested `mlx-lm`:
  `0.30.7`

## Controls

Use `/engine/profiles` to discover product-facing runtime profiles:

- `interactive`
- `agent-workspace`
- `memory-saver`
- `diagnostics`

Use `/engine/config` to apply a named profile or tune lower-level behavior
without reloading the model:

- `runtime_profile`
- `engine_preset`
- `prefix_cache_population_mode`
- `prefix_cache_async_idle_timeout_ms`
- `prefix_cache_async_idle_grace_ms`
- `prefix_cache_pending_wait_ms`
- `prefix_cache_memory_limit_mb`
- `prefix_cache_min_entries`
- `max_concurrent_requests`
- `max_queued_requests`
- `queue_timeout_ms`

Use `/engine/ui` for UI and product integrations. It returns a single snapshot
with:

- model/load state
- current `runtime_profile`
- profile catalog
- readiness flags
- generation controls
- cache strategy and counters
- scheduler state
- memory summary
- request metrics

Python integrations can use `mlx_engine.ui_client.EngineUiClient` to consume the
same contract and normalize it into `EngineUiSummary`.

Recommended product profiles:

- Low-latency interactive:
  `runtime_profile=interactive`
- Repeated-agent-context:
  `runtime_profile=agent-workspace`
- Memory constrained:
  `runtime_profile=memory-saver`
- Operational diagnostics:
  `runtime_profile=diagnostics`

## Readiness Probes

Run these against a live server:

```bash
python3 benchmarks/python/async_prefix_build_amortization_probe.py \
  --base-url http://127.0.0.1:8773

python3 benchmarks/python/async_prefix_pending_wait_probe.py \
  --base-url http://127.0.0.1:8773

python3 benchmarks/python/cache_continuation_capabilities_probe.py \
  --base-url http://127.0.0.1:8773

python3 benchmarks/python/engine_readiness_probe.py \
  --base-url http://127.0.0.1:8773

python3 benchmarks/python/runtime_profile_probe.py \
  --base-url http://127.0.0.1:8773

python3 benchmarks/python/ui_status_contract_probe.py \
  --base-url http://127.0.0.1:8773

python3 benchmarks/python/ui_client_adapter_probe.py \
  --base-url http://127.0.0.1:8773

cd /Users/jeffreycruz/Development/AI_AGENTS/dax-stereo/packages/coding-agent
npx tsx src/cli.ts mlx-engine --base-url http://127.0.0.1:8773 --once
npx tsx src/cli.ts mlx-engine --base-url http://127.0.0.1:8773 \
  --prompt "Reply with exactly three words about MLX speed." \
  --max-tokens 8
npx tsx src/cli.ts mlx-engine --base-url http://127.0.0.1:8773 \
  --prompt "Stream exactly four words about MLX." \
  --max-tokens 8 \
  --stream
npx tsx src/cli.ts mlx-engine --base-url http://127.0.0.1:8773 \
  --interactive \
  --max-tokens 128
```

## Go Criteria

- `/health.ok` is `true`
- `/health.device.metal_available` is `true`
- `/health.device.default_device` contains `gpu`
- `prefix_cache_policy` includes:
  - `existing_build_reuses`
  - `pending_build_deduplications`
  - `pending_wait_ms`
  - `pending_wait_hits`
- `prompt_cache_continuation` includes:
  - `native_replay_free_prefix_store_supported`
  - `safe_request_prefix_store_strategy`
  - `required_lower_level_work`
- `/engine/config` dry-run returns planned state for pending-wait controls
- `/engine/profiles` returns all named runtime profiles
- `/engine/config` can apply `runtime_profile=agent-workspace`
- `/engine/ui` returns the stable UI integration contract
- `EngineUiClient.summary()` returns a normalized UI summary
- `dax mlx-engine --once` displays live model, GPU, generation, cache, scheduler,
  metrics, and runtime-profile state from the resident engine
- `dax mlx-engine --prompt ...` returns a non-streaming generation response and
  usage counters through the resident engine HTTP API
- `dax mlx-engine --prompt ... --stream` prints streamed chunks from the
  OpenAI-compatible SSE API and reports usage counters when the final event
  arrives
- `dax mlx-engine --interactive` opens a focused Dax TUI prompt panel that
  streams responses into a short terminal transcript
- completed interactive generations append elapsed timing and completion
  tokens-per-second feedback when completion-token usage is available
- `/export` and `/snapshot` include structured `generation_metrics` records for
  elapsed milliseconds, completion throughput, and returned usage counters
- `/export` and `/snapshot` include `generation_metrics_summary` aggregates for
  count, elapsed milliseconds, and completion throughput
- inside the interactive panel, `/metrics`, `/metrics all`, `/metrics clear`,
  and `/metrics export [path]` review, reset, or export generation timing
  evidence without prompt text
- inside the interactive panel, `/profiles`, `/profile <name>`, and `/profile
  next` list and apply runtime profiles without leaving the TUI
- inside the interactive panel, the configured stop key aborts in-flight
  generation without exiting the TUI
- inside the interactive panel, live engine status refresh shows active/queued
  requests, cache mode, failed requests, and total request count
- inside the interactive panel, `/export [path]` writes an evidence JSON file
  with the latest engine snapshot, profile catalog, mode, max token cap, and
  plain-text transcript
- inside the interactive panel, `/reload [model-path]` and `/unload` control
  resident model lifecycle through the MLX engine HTTP API and refresh the
  panel from `/engine/ui`
- inside the interactive panel, `/cache prune [target_entries]` performs manual
  prefix-cache recovery through `/engine/cache/prune` and refreshes the panel
  from `/engine/ui`
- inside the interactive panel, `/config [--dry-run] key=value ...` applies
  guarded runtime config through `/engine/config` and refreshes the panel from
  `/engine/ui`
- inside the interactive panel, `/help` shows available controls and `/status`
  appends a compact engine summary to the transcript
- inside the interactive panel, `/find <text>` searches prior transcript lines
  and appends compact recent matches or a no-match result
- inside the interactive panel, `/view recent`, `/view all`, and `/clear`
  control long transcript rendering and cleanup without deleting prompt history
- inside the interactive panel, `/history` lists recent natural-language
  prompts and `/again [n]` reruns the latest or numbered prompt
- inside the interactive panel, `/snapshot [path]` writes a diagnostic JSON
  bundle with compact status, raw engine snapshot, profiles, prompt history,
  and transcript
- snapshot export also writes an attach-ready Markdown sidecar with compact
  status, recent prompts, and recent transcript excerpt
- `/snapshot --redact [path]` replaces prompt history and transcript content
  with redaction markers while preserving engine status and configuration
  context
- `/snapshot --safe [path]` implies prompt/transcript redaction and also scrubs
  local filesystem-style model paths from status, raw snapshot payloads,
  profiles, and Markdown sidecars
- `/snapshot --no-raw [path]` omits the raw engine snapshot payload while
  preserving compact status, profiles, metadata, and prompt/transcript fields;
  combine with `--safe` for compact external handoff artifacts
- `/snapshot ticket|internal|full [path]` provides named privacy presets:
  `ticket` maps to `--safe --no-raw`, `internal` maps to `--redact`, and
  `full` preserves the complete raw snapshot behavior

## Latest Resident Benchmark Evidence

M54 captured a live resident benchmark against
`Qwen3.6-35B-A3B-UD-MLX-4bit` on `Device(gpu, 0)`.

Key result:

- Full prefill path: 247 actual prefill tokens, 87728.97 ms service time.
- Prefix cache create path: 7.5 mean actual prefill tokens, 434.44 ms mean
  service time.
- Prefix cache hit path: 8 actual prefill tokens, 219.72 ms service time.

Readiness interpretation:

- The current resident engine can turn repeated long-context prompt processing
  from tens of seconds into hundreds of milliseconds when prefix reuse hits.
- Cache creation remains a visible cost and should be treated as the next
  prompt-processing optimization target.
- Dax operator metrics now have a concrete resident benchmark baseline to
  compare against future engine-profile and cache-policy changes.
- `benchmarks/python/compare_resident_benchmarks.py` now reports derived
  per-artifact service speedup, prefill-token reduction, and cache-prepare
  share versus full prefill, so later runs can be compared without manual JSONL
  parsing.
- `benchmarks/python/resident_regression_gate.py` now gates cache-hit service
  speedup and actual-prefill-token reduction versus full prefill, and
  `benchmarks/python/run_resident_regression_suite.py` exposes both thresholds
  as suite flags.
- The same gate now separately checks cache-create mean service time and
  cache-prepare share, so first-reuse overhead can regress independently of
  cache-hit behavior.
- `benchmarks/python/resident_regression_gate.py --output-json` emits a compact
  machine-readable report, and `benchmarks/python/run_resident_regression_suite.py`
  writes `resident-regression-gate-<tag>.json` next to the benchmark artifacts.
- `benchmarks/python/run_resident_regression_suite.py` also writes
  `resident-regression-suite-<tag>.json`, a suite manifest that records
  artifact paths, executed steps, and the embedded gate report when available.
- Failed suite subprocesses now write a `verdict=FAIL` suite manifest before
  exiting, preserving the failing command, return code, artifact existence
  state, and embedded gate report when available.
- `benchmarks/python/summarize_resident_suite_manifest.py` prints a stable
  line-based summary for `resident-regression-suite-<tag>.json` manifests,
  including suite verdict, artifact existence, gate failures, and failing
  subprocess details.
- `benchmarks/python/summarize_resident_suite_manifest.py --fail-on-fail` exits
  non-zero when the suite manifest verdict is not `PASS`, making the summary
  tool usable as a CI assertion step.
- `benchmarks/python/run_resident_regression_suite.py --print-manifest-summary`
  prints the same suite manifest summary inline on success and after child
  subprocess failure, while preserving existing output unless the flag is set.

## Current Qwen Result

- In-flight async prefix builds are deduplicated.
- Duplicate foreground requests can wait for a pending prefix build and convert
  into a cache hit when `prefix_cache_pending_wait_ms` is enabled.
- Qwen3.5/Next cache continuation remains blocked for generic replay-free
  prefix storage because `ArraysCache` carries recurrent state without offset or
  trim semantics.
- Safe strategy for this model family:
  `split_prefill_or_async_build`
- Required lower-level work:
  `model_specific_recurrent_state_continuation_for_arrays_cache`

## Product Implication

For a fast Mac local-inference product, expose these controls as named profiles
instead of raw internals:

- `Interactive`: prioritize immediate foreground latency.
- `Agent Workspace`: wait briefly for repeated context prefix builds.
- `Memory Saver`: cap cache entries and prune aggressively.
- `Diagnostics`: run the readiness probes and show cache continuation blockers.

## Tensor Parallelism Note

MLX has tensor-parallel and distributed primitives, but the current resident
engine does not use them.

- Framework support exists through `mlx.core.distributed`, distributed
  collectives, `shard_linear`, `shard_inplace`, `AllToShardedLinear`, and
  `ShardedToAllLinear`.
- MLX model format alone does not make inference tensor-parallel.
- The current `mlx_engine/` resident service should be treated as a
  single-process resident engine until an explicit distributed model-sharding
  milestone is added.
- Tensor parallelism is more relevant for multi-Mac or very large model work;
  the current single-Mac path should prioritize prompt processing, cache reuse,
  scheduling, warmup/JIT behavior, and quantized kernels first.
