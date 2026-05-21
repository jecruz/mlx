# M232 Resident Lifecycle Regression Gate

Verdict: `PASS`
Readiness: `resident-lifecycle-regression-ready`

## Probe Results

- Shutdown probe: `PASS`
- Startup preflight probe: `PASS`

## Checks

| Check | Verdict | Detail |
| --- | --- | --- |
| `shutdown_probe.exit_code` | `PASS` | `returncode=0` |
| `shutdown_probe.verdict` | `PASS` | `verdict='PASS'` |
| `shutdown_probe.joined_warmup` | `PASS` | `joined=True, alive_after=False` |
| `shutdown_probe.joined_async_cache_builds` | `PASS` | `joined=1, alive_after=0` |
| `startup_preflight.exit_code` | `PASS` | `returncode=0` |
| `startup_preflight.verdict` | `PASS` | `verdict='PASS'` |
| `source_contract.resident_engine_shutdown_sets_event` | `PASS` | `ResidentEngine.shutdown must signal shutdown_requested before joining background work` |
| `source_contract.reload_requests_old_engine_shutdown` | `PASS` | `EngineManager.reload/unload must request old-engine shutdown before replacement/removal` |
| `source_contract.reload_or_unload_joins_old_engine` | `PASS` | `EngineManager.reload/unload must join old-engine background work` |
| `source_contract.lifespan_shutdown_calls_manager` | `PASS` | `FastAPI lifespan shutdown must call EngineManager.shutdown` |
| `source_contract.port_preflight_before_mlx_import` | `PASS` | `occupied-port startup must fail before importing MLX/model validation` |

## Failures

- none
