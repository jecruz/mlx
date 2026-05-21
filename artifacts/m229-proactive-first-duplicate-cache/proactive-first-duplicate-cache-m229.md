# M229 Proactive First-Duplicate Cache Creation

## Result

M229 is complete. The lower-memory Qwen2.5 Coder 14B candidate now creates reusable prefix cache state from the first request, so the first duplicate request hits cache immediately instead of building split-prefill cache synchronously.

## Implementation

Changed files:

- `mlx_engine/resident_service.py`

Changes:

- added proactive trimmed-prefix cache creation for request-derived first-hit profiles
- enabled the proactive path only for:
  - `agent-workspace-first-hit`
  - `agent-workspace-low-memory`
- stores several likely repeated-workspace prefix lengths from the first full prompt
- added longest-prefix fallback lookup in the prefix KV cache so a shorter proactive prefix can still be reused when the next prompt's exact match length differs
- records proactive cache metrics in full engine metrics and recent request metrics

The first M229 request proactively stored these prefix lengths:

- `2073`
- `2070`
- `2065`
- `2049`
- `2017`

The second request then hit the `2070` cached prefix with only `11` prefill tokens.

## Performance

Model:

`/Volumes/StudioStackSSD4TB/Development/LLM/lmstudio/models/lmstudio-community/Qwen2.5-Coder-14B-Instruct-MLX-4bit`

| Metric | M226 | M229 |
| --- | ---: | ---: |
| first duplicate service ms | `3626.465` | `193.098` |
| first duplicate improvement | n/a | `3433.367 ms` / `94.68%` |
| first duplicate prefill tokens | `11` | `11` |
| first duplicate cache prepare ms | `3366.409` | `0.253` |
| first duplicate cache state | split-prefill created during turn 2 | proactive cache hit on turn 2 |
| conversion ratio vs baseline | `0.912` | `0.043` |
| mature-hit service ms | `185.817` | `193.098` |
| mature-hit speedup vs baseline | `21.390x` | `23.445x` |
| strict conversion gate | `FAIL` | `PASS` |

M229 turns the M226 compatibility win into a real first-duplicate latency win. The synchronous cache-build cost moved out of turn 2 and was replaced by a prepared prefix hit.

## Quality

Quality threshold stayed PASS with the adapted Qwen2.5 Coder prompt adapter:

- chat-template quality verdict: `PASS`
- quality threshold verdict: `PASS`
- readiness: `ci-quality-ready`
- failures: `0`
- max repetition score: `0.045455`

## Validation

Commands:

```sh
python3 -m py_compile mlx_engine/resident_service.py mlx_engine/prefix_cache.py benchmarks/python/resident_shutdown_safety_probe.py
python3 benchmarks/python/dax_first_hit_scheduling_sweep.py --base-url http://127.0.0.1:8777 --client-mode resident --variants agent-workspace-first-hit --turns 6 --shared-repeats 64 --max-tokens 4 --tag m229-qwen25-coder-14b-resident --output-dir artifacts/m229-proactive-first-duplicate-cache --output-json artifacts/m229-proactive-first-duplicate-cache/dax-first-hit-scheduling-sweep-m229-qwen25-coder-14b-resident.json --fail-on-fail
python3 benchmarks/python/chat_template_quality_probe.py --base-url http://127.0.0.1:8777 --output-json artifacts/m229-proactive-first-duplicate-cache/chat-template-quality-adapted-m229-qwen25-coder-14b.json --tag m229-qwen25-coder-14b-chat-template-adapted --prompt-adapter qwen25-coder-lower-memory --fail-on-fail
python3 benchmarks/python/quality_threshold_gate.py --quality-artifact artifacts/m229-proactive-first-duplicate-cache/chat-template-quality-adapted-m229-qwen25-coder-14b.json --output-json artifacts/m229-proactive-first-duplicate-cache/quality-threshold-gate-m229-qwen25-coder-14b-adapted.json
python3 benchmarks/python/resident_shutdown_safety_probe.py
```

Results:

- compile: `PASS`
- first-hit scheduling sweep: `PASS`
- first-hit conversion gate: `PASS`
- adapted quality: `PASS`
- quality threshold: `PASS`
- shutdown safety probe: `PASS`

Artifacts:

- `dax-repeated-context-m229-qwen25-coder-14b-resident-agent-workspace-first-hit.json`
- `dax-first-hit-conversion-gate-m229-qwen25-coder-14b-resident-agent-workspace-first-hit.json`
- `dax-first-hit-scheduling-sweep-m229-qwen25-coder-14b-resident.json`
- `chat-template-quality-adapted-m229-qwen25-coder-14b.json`
- `quality-threshold-gate-m229-qwen25-coder-14b-adapted.json`

## Decision

M229 is a real latency milestone. The first duplicate no longer pays synchronous split-prefill build cost, and the lower-memory candidate keeps quality PASS. The next promotion question should move from "can it first-hit?" to "does it meet a combined memory, speed, and quality gate?"
