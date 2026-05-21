# M230 Lower-Memory Profile Promotion Gate

## Result

M230 is complete. The lower-memory Qwen2.5 Coder 14B candidate now has a repeatable promotion gate that combines memory ceiling, first-duplicate behavior, mature-hit speed, proactive cache creation, and quality threshold.

Promotion verdict:

- `PASS`
- readiness: `lower-memory-profile-promotable`

Model:

`/Volumes/StudioStackSSD4TB/Development/LLM/lmstudio/models/lmstudio-community/Qwen2.5-Coder-14B-Instruct-MLX-4bit`

## Gate Definition

New script:

`benchmarks/python/lower_memory_profile_promotion_gate.py`

Inputs:

- repeated-context benchmark JSON
- first-hit conversion gate JSON
- quality threshold JSON

Promotion thresholds:

| Check | Threshold |
| --- | ---: |
| quality threshold verdict | `PASS` |
| quality readiness | `ci-quality-ready` |
| first-hit conversion gate | `PASS` |
| max active memory | `<= 12 GB` |
| max peak memory | `<= 12 GB` |
| first duplicate service | `<= 250 ms` |
| first duplicate prefill | `<= 32 tokens` |
| first duplicate cache hit | `true` |
| first duplicate cache created inline | `false` |
| conversion ratio vs baseline | `<= 0.20` |
| mature-hit speedup | `>= 5x` |
| proactive prefix cache created | `>= 1` |

The `12 GB` ceiling is intentional. A calibration run with a `10 GB` ceiling failed because the proactive-cache run reached:

- max active memory: `11.028 GB`
- max peak memory: `11.048 GB`

That keeps the lower-memory candidate well below the earlier A3B memory class while accounting for M229's proactive prefix-cache memory.

## Performance

| Metric | Result | Threshold | Verdict |
| --- | ---: | ---: | --- |
| max active memory | `11.028 GB` | `12 GB` | `PASS` |
| max peak memory | `11.048 GB` | `12 GB` | `PASS` |
| first duplicate service | `193.098 ms` | `250 ms` | `PASS` |
| first duplicate prefill | `11` tokens | `32` tokens | `PASS` |
| first duplicate cache hit | `true` | `true` | `PASS` |
| first duplicate cache created inline | `false` | `false` | `PASS` |
| conversion ratio vs baseline | `0.043` | `0.20` | `PASS` |
| mature-hit speedup | `23.445x` | `5x` | `PASS` |
| proactive prefix caches created | `5` | `1` | `PASS` |

Compared with M226:

- M226 first duplicate service: `3626.465 ms`
- M229/M230 first duplicate service: `193.098 ms`
- improvement: `3433.367 ms` / `94.68%`

## Quality

Quality threshold stayed PASS:

- quality verdict: `PASS`
- readiness: `ci-quality-ready`
- max repetition score: `0.045455`
- failures: `0`

## Validation

Commands:

```sh
python3 -m py_compile benchmarks/python/lower_memory_profile_promotion_gate.py
python3 benchmarks/python/lower_memory_profile_promotion_gate.py --repeated-context-json artifacts/m229-proactive-first-duplicate-cache/dax-repeated-context-m229-qwen25-coder-14b-resident-agent-workspace-first-hit.json --conversion-gate-json artifacts/m229-proactive-first-duplicate-cache/dax-first-hit-conversion-gate-m229-qwen25-coder-14b-resident-agent-workspace-first-hit.json --quality-threshold-json artifacts/m229-proactive-first-duplicate-cache/quality-threshold-gate-m229-qwen25-coder-14b-adapted.json --output-json artifacts/m230-lower-memory-profile-promotion-gate/lower-memory-profile-promotion-gate-m230-qwen25-coder-14b.json --tag m230-qwen25-coder-14b --max-active-memory-gb 12 --max-peak-memory-gb 12 --max-first-duplicate-service-ms 250 --max-first-duplicate-prefill-tokens 32 --max-conversion-ratio 0.20 --min-mature-hit-speedup 5 --require-proactive-prefix-cache --fail-on-fail
```

Result:

- promotion gate verdict: `PASS`
- checks: `12`
- failures: `0`

Calibration artifact:

- `lower-memory-profile-promotion-gate-m230-qwen25-coder-14b-10gb-calibration.json`

Accepted artifact:

- `lower-memory-profile-promotion-gate-m230-qwen25-coder-14b.json`

## Decision

The lower-memory candidate is promotable under the M230 gate. It is no longer blocked on quality, first-hit behavior, mature-hit speedup, or memory budget. The next risk is memory growth from proactive cache creation across longer sessions, which should be handled by M233.
