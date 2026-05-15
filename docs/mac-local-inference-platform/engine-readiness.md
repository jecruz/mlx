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
