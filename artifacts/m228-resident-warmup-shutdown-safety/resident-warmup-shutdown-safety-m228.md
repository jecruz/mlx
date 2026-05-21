# M228 Resident Warmup Shutdown Safety

## Result

M228 is complete. The resident engine now explicitly signals shutdown and joins tracked warmup/background cache-build threads during reload, unload, and server shutdown.

## Implementation

Changed files:

- `mlx_engine/resident_service.py`
- `benchmarks/python/resident_shutdown_safety_probe.py`

Runtime changes:

- added a per-engine `shutdown_requested` event
- tracks async prefix-cache build threads in `prefix_cache_build_threads`
- skips newly scheduled async prefix-cache builds after shutdown is requested
- makes async cache-build workers re-check shutdown before foreground GPU work
- joins warmup and async cache-build threads in `ResidentEngine.shutdown()`
- removes pending async-build keys for joined/dead tracked build threads
- marks warmup snapshots with `cancelled`
- calls old-engine shutdown during reload and unload
- calls manager shutdown through FastAPI lifespan shutdown

## Validation

Static shutdown probe:

```sh
python3 benchmarks/python/resident_shutdown_safety_probe.py
```

Result:

```json
{
  "type": "resident_shutdown_safety_probe",
  "verdict": "PASS",
  "result": {
    "shutdown_requested": true,
    "timeout_ms": 1000,
    "warmup_thread_present": true,
    "warmup_alive_before": true,
    "warmup_joined": true,
    "warmup_alive_after": false,
    "async_threads_before": 1,
    "async_threads_joined": 1,
    "async_threads_alive_after": 0,
    "pending_async_builds_after": 0,
    "tracked_async_threads_after": 0
  }
}
```

Compile validation:

```sh
python3 -m py_compile mlx_engine/resident_service.py benchmarks/python/resident_shutdown_safety_probe.py
```

Result: `PASS`

Live updated-code resident server validation:

```sh
python3 mlx_engine/resident_service.py --model /Volumes/StudioStackSSD4TB/Development/LLM/lmstudio/models/lmstudio-community/Qwen2.5-Coder-14B-Instruct-MLX-4bit --host 127.0.0.1 --port 8775 --warmup-mode async --warmup-prompt-tokens 64,512 --engine-preset async-experimental --prefix-cache-population-mode async --require-gpu
curl -sS http://127.0.0.1:8775/health
curl -sS -X POST http://127.0.0.1:8775/engine/reload -H 'Content-Type: application/json' -d '{"warmup_mode":"async","warmup_prompt_tokens":"64,512"}'
curl -sS -X POST http://127.0.0.1:8775/engine/unload
```

Observed:

- health: `True Device(gpu, 0)` with async warmup completed
- reload: `True True 1 async True False`
- unload: `True False 1`
- server shutdown completed cleanly

Lifespan shutdown validation:

```sh
python3 mlx_engine/resident_service.py --model /Volumes/StudioStackSSD4TB/Development/LLM/lmstudio/models/lmstudio-community/Qwen2.5-Coder-14B-Instruct-MLX-4bit --host 127.0.0.1 --port 8776 --warmup-mode off --warmup-prompt-tokens 64 --engine-preset async-experimental --prefix-cache-population-mode async --require-gpu
curl -sS http://127.0.0.1:8776/health
```

Observed:

- health: `True True off True`
- no deprecated FastAPI `on_event` warning
- Ctrl-C server shutdown completed cleanly through app lifespan shutdown

## Performance

This milestone is lifecycle safety work. It does not change prompt processing, generation, cache-hit math, model selection, or quality behavior.

Current relevant performance baseline remains M226:

- lower-memory turn-2 prefill: `11` tokens
- mature-hit service: `185.817 ms`
- mature-hit speedup: `21.390x`
- synchronous conversion cache prepare remains the next latency bottleneck: `3366.409 ms`

Lifecycle overhead is bounded to reload/unload/shutdown paths:

- shutdown probe elapsed: about `0.073 ms`
- live reload/unload remained operational with the Qwen2.5 Coder 14B MLX candidate

## Decision

M228 closes the lifecycle safety gap identified after the Metal startup crash work: old resident engines now get a shutdown signal and tracked background work is joined or cleaned up during reload, unload, and process shutdown.
