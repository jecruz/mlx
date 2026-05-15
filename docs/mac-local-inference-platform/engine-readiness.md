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
