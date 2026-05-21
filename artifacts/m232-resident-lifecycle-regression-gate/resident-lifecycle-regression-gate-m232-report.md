# M232 Resident Lifecycle Regression Gate

M232 is complete. Resident lifecycle safety now has a repeatable regression gate
that validates shutdown, reload/unload source contracts, startup port preflight,
and FastAPI lifespan shutdown wiring without loading a large MLX model.

## Artifacts

- `resident-lifecycle-regression-gate-m232.json`
- `resident-lifecycle-regression-gate-m232.md`
- `resident-port-preflight-m232.json`

## Gate Coverage

The gate combines:

- `resident_shutdown_safety_probe.py`
- `resident_port_preflight_probe.py`
- static source-contract checks in `mlx_engine/resident_service.py`

The startup preflight probe requires local socket bind permissions and was run
outside the sandbox.

## Results

- lifecycle gate verdict: `PASS`
- readiness: `resident-lifecycle-regression-ready`
- checks: `11`
- failures: `0`
- shutdown probe verdict: `PASS`
- startup preflight verdict: `PASS`

## Lifecycle Contracts Verified

- `ResidentEngine.shutdown()` signals `shutdown_requested`.
- warmup thread is joined and not alive after shutdown.
- async prefix-cache build thread is joined and not alive after shutdown.
- occupied-port startup exits before MLX import/model validation.
- `EngineManager.reload()` / `EngineManager.unload()` request old-engine
  shutdown.
- reload/unload join old-engine background work.
- FastAPI lifespan shutdown calls `EngineManager.shutdown()`.

## Performance

M232 does not change the inference hot path. The gate measures lifecycle
overhead only:

- shutdown probe elapsed: about `0.058 ms`
- model load avoided
- no generation or prompt-processing benchmark changed

The latest lower-memory performance evidence remains the M231/M230 carried
forward result:

- first duplicate service: `193.098 ms`
- M226-to-current improvement: `3433.367 ms` / `94.68%`
- mature-hit speedup: `23.445x`
- max peak memory: `11.048 GB`

## Conclusion

M232 turns the previously one-off lifecycle validations into a repeatable gate.
Future lifecycle changes now have a cheap check that catches regressions in
startup preflight, shutdown joining, reload/unload replacement safety, and
server lifespan cleanup.
