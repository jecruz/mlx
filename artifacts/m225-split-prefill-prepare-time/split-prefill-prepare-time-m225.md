# M225 Split-Prefill Prepare-Time Reduction

## Result

M225 is complete. Request-derived split-prefill cache preparation dropped below the M221 baseline while quality stayed PASS and mature-hit speedup stayed above `5x`.

## Implementation

Changed file:

- `mlx_engine/resident_service.py`

Change:

- prefix-cache builds now use an effective default prefill step size of `min(max(prefix_tokens, 2048), 4096)` when no explicit `prefill_step_size` is selected
- the request-derived split-prefill path records `cache_build_prefill_step_size` in engine metrics

For the M225 repeated-context shape, the reusable prefix length was `2071` tokens, so the cache builder used `2071` instead of the prior implicit `2048` fallback. That avoids splitting the 2071-token prefix over the 2048-token boundary.

## Performance

| Metric | M221 Baseline | M225 Accepted |
| --- | ---: | ---: |
| split-prefill cache prepare ms | `903.934` | `866.720` |
| prepare-time improvement | n/a | `37.214 ms` / `4.12%` |
| first duplicate service ms | `1109.143` | `1080.968` |
| conversion ratio vs baseline | `0.775` | `0.716` |
| conversion actual prefill tokens | `11` | `11` |
| mature hit best service ms | `205.462` | `213.588` |
| mature hit speedup vs baseline | `6.836x` | `7.068x` |
| cache build prefill step size | implicit `2048` | `2071` |

The first M225 pass measured `905.560 ms`, so the accepted artifact is the second controlled pass against the same modified temporary server. The accepted pass is below the M221 target and keeps the quality/performance guardrails intact.

## Quality

Quality threshold stayed PASS:

- deterministic quality verdict: `PASS`
- quality threshold verdict: `PASS`
- readiness: `ci-quality-ready`
- failures: `0`

## Validation

Commands:

```sh
python3 -m py_compile mlx_engine/resident_service.py
python3 benchmarks/python/dax_first_hit_scheduling_sweep.py --base-url http://127.0.0.1:8774 --client-mode resident --variants agent-workspace-first-hit --turns 6 --shared-repeats 64 --max-tokens 4 --tag m225b-qwen-a3b-resident --output-dir artifacts/m225-split-prefill-prepare-time --output-json artifacts/m225-split-prefill-prepare-time/dax-first-hit-scheduling-sweep-m225b-qwen-a3b-resident.json --fail-on-fail
python3 benchmarks/python/quality_gate_runner.py --base-url http://127.0.0.1:8774 --gate deterministic --output-json artifacts/m225-split-prefill-prepare-time/deterministic-quality-m225-qwen-a3b.json --tag m225-qwen-a3b
python3 benchmarks/python/quality_threshold_gate.py --quality-artifact artifacts/m225-split-prefill-prepare-time/deterministic-quality-m225-qwen-a3b.json --output-json artifacts/m225-split-prefill-prepare-time/quality-threshold-gate-m225-qwen-a3b.json
```

Artifacts:

- `dax-repeated-context-m225b-qwen-a3b-resident-agent-workspace-first-hit.json`
- `dax-first-hit-conversion-gate-m225b-qwen-a3b-resident-agent-workspace-first-hit.json`
- `dax-first-hit-scheduling-sweep-m225b-qwen-a3b-resident.json`
- `deterministic-quality-m225-qwen-a3b.json`
- `quality-threshold-gate-m225-qwen-a3b.json`

## Decision

This is a modest but real split-prefill improvement. The next bigger gain is likely not further prefill-step tuning; it is making the cache exist before the first duplicate request needs to build it, or making lower-memory candidates compatible with request-derived first-hit conversion.
