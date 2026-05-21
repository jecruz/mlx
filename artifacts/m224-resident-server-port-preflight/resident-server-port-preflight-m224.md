# M224 Resident Server Port Preflight

## Result

M224 is complete. Duplicate resident server launches now fail before MLX runtime import, model validation, and warmup when the requested host/port is already bound.

This addresses the `crash_2.log` pattern where a second server process attempted to start on an occupied port, reached MLX GPU warmup, then crashed during shutdown after uvicorn reported address-in-use.

## Implementation

Changed files:

- `mlx_engine/resident_service.py`
- `benchmarks/python/resident_mlx_service.py`
- `benchmarks/python/resident_port_preflight_probe.py`

Behavior:

- `resident_service.py` no longer imports `mlx.core` at module import time.
- MLX-dependent imports are lazy-loaded through `ensure_mlx_runtime_imported()`.
- `main()` performs `assert_port_available(host, port)` immediately after argument parsing.
- occupied-port startup exits with code `98`.
- `benchmarks/python/resident_mlx_service.py` now propagates `main()` exit codes.

## Validation

Command:

```sh
python3 -m py_compile mlx_engine/resident_service.py benchmarks/python/resident_mlx_service.py benchmarks/python/resident_port_preflight_probe.py
```

Result: `PASS`

Command:

```sh
python3 benchmarks/python/resident_port_preflight_probe.py \
  --output-json artifacts/m224-resident-server-port-preflight/resident-port-preflight-m224.json \
  --tag m224-resident-port-preflight
```

Result:

- probe verdict: `PASS`
- module import probe stdout: `False`, meaning `mlx.core` was not imported by `import mlx_engine.resident_service`
- occupied-port launch return code: `98`
- occupied-port stderr: `port unavailable before MLX import`
- occupied-port launch did not reach model validation

## Performance

No inference hot path changed. Runtime performance evidence remains:

- M221 A3B first duplicate conversion ratio: `0.775`
- M221 A3B mature hit best service: `205.462 ms`
- M222 Qwen2.5 Coder 14B active memory: `8.360 GB`
- M222 Qwen2.5 Coder 14B mature hit best service: `182.281 ms`

Expected operational improvement:

- failed duplicate starts become cheap and deterministic
- duplicate starts do not allocate MLX/Metal runtime state
- duplicate starts do not launch async warmup threads
- duplicate starts do not trigger the observed warmup-shutdown crash path

## Decision

This is a crash-prevention milestone, not a throughput milestone. Continue raw performance work with split-prefill prepare-time reduction.
