# M226 Lower-Memory First-Hit Conversion Compatibility

## Result

M226 is complete for compatibility. The Qwen2.5 Coder 14B lower-memory candidate now converts the first duplicate request on turn 2 through request-derived split-prefill instead of waiting until turn 3 for the first usable cache hit.

The remaining performance issue is explicit: turn 2 still pays synchronous cache-build cost, so the strict M221 service-ratio latency budget did not pass for this candidate. That moves the next optimization target to proactive cache creation before the first duplicate request arrives.

## Implementation

Changed file:

- `mlx_engine/resident_service.py`

Change:

- `agent-workspace-first-hit` and `agent-workspace-low-memory` now force request-derived split-prefill conversion even when the model exposes trimmable KV caches.
- Generic `agent-workspace-request` behavior is unchanged and still defers request-cache storage for trimmable caches.
- Split-prefill conversions are tagged with `cache_split_prefill_reason: first_hit_profile_request_conversion`.

This preserves the prior safe path while making the lower-memory profile compatible with the first-hit conversion behavior already proven on the A3B path.

## Performance

Model:

- `/Volumes/StudioStackSSD4TB/Development/LLM/lmstudio/models/lmstudio-community/Qwen2.5-Coder-14B-Instruct-MLX-4bit`

| Metric | M222 Candidate | M226 Candidate |
| --- | ---: | ---: |
| turn 1 actual prefill tokens | `2081` | `2081` |
| turn 2 actual prefill tokens | `2081` | `11` |
| turn 2 conversion path | no split-prefill | request-derived split-prefill |
| turn 2 cache prepare ms | `0.125` | `3366.409` |
| turn 2 service ms | `3314.128` | `3626.465` |
| first mature hit service ms | `185.446` | `185.817` |
| mature-hit speedup vs baseline | n/a | `21.390x` |
| active memory, loaded candidate | `8.360 GB` | `8.309 GB` health / `8.763 GB` turn 1 |
| peak memory during sweep | n/a | `9.388 GB` |

M226 fixed the behavioral blocker from M222: the first duplicate request no longer performs full prompt prefill. The first duplicate latency did not improve because the cache is built synchronously inside `cache_prepare_ms`. This is expected from the current implementation and should be addressed by M229 proactive cache creation.

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
python3 -m py_compile mlx_engine/resident_service.py
python3 benchmarks/python/dax_first_hit_scheduling_sweep.py --base-url http://127.0.0.1:8774 --client-mode resident --variants agent-workspace-first-hit --turns 6 --shared-repeats 64 --max-tokens 4 --tag m226-qwen25-coder-14b-resident --output-dir artifacts/m226-lower-memory-first-hit-conversion --output-json artifacts/m226-lower-memory-first-hit-conversion/dax-first-hit-scheduling-sweep-m226-qwen25-coder-14b-resident.json --fail-on-fail
python3 benchmarks/python/chat_template_quality_probe.py --base-url http://127.0.0.1:8774 --output-json artifacts/m226-lower-memory-first-hit-conversion/chat-template-quality-adapted-m226-qwen25-coder-14b.json --tag m226-qwen25-coder-14b-chat-template-adapted --prompt-adapter qwen25-coder-lower-memory --fail-on-fail
python3 benchmarks/python/quality_threshold_gate.py --quality-artifact artifacts/m226-lower-memory-first-hit-conversion/chat-template-quality-adapted-m226-qwen25-coder-14b.json --output-json artifacts/m226-lower-memory-first-hit-conversion/quality-threshold-gate-m226-qwen25-coder-14b-adapted.json
```

Artifacts:

- `dax-repeated-context-m226-qwen25-coder-14b-resident-agent-workspace-first-hit.json`
- `dax-first-hit-conversion-gate-m226-qwen25-coder-14b-resident-agent-workspace-first-hit.json`
- `dax-first-hit-scheduling-sweep-m226-qwen25-coder-14b-resident.json`
- `chat-template-quality-adapted-m226-qwen25-coder-14b.json`
- `quality-threshold-gate-m226-qwen25-coder-14b-adapted.json`

## Decision

M226 is accepted as a compatibility milestone, not as a first-duplicate latency win. It removes the lower-memory candidate's full-prefill turn-2 behavior and keeps quality PASS, but the strict service-ratio gate remains a useful warning that proactive cache creation is required before promoting this as a user-visible latency improvement.
