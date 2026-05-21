# M221 First-Hit Conversion Budget

## Result

M221 is complete. The first-hit sweep now treats request-conversion profiles as first-class target candidates and tightens the default guardrails:

- first duplicate-turn conversion ratio: `<= 0.80` of cold baseline, tightened from `<= 1.10`
- mature reusable-turn speedup: `>= 5.0x`, tightened from `>= 2.0x`
- first-hit target selection now works for `request-conversion` gate shapes, not only scheduled-pre-hit variants

## Live Evidence

Model:

`/Volumes/StudioStackSSD4TB/Development/LLM/lmstudio/models/unsloth/Qwen3.6-35B-A3B-UD-MLX-4bit`

Resident server:

`http://127.0.0.1:8773`, GPU available, runtime profile switched by benchmark.

Artifacts:

- `dax-first-hit-scheduling-sweep-m221-qwen-a3b-resident.json`
- `dax-first-hit-conversion-gate-m221-qwen-a3b-resident-agent-workspace-first-hit.json`
- `dax-repeated-context-m221-qwen-a3b-resident-agent-workspace-first-hit.json`
- `quality-threshold-gate-m221-qwen-a3b.json`
- `deterministic-quality-m221-qwen-a3b.json`

## Performance

| Metric | M218 Baseline | M221 Current |
| --- | ---: | ---: |
| cold baseline service ms | `1092.314` | `1431.913` |
| first duplicate conversion service ms | `1121.612` | `1109.143` |
| conversion ratio vs cold baseline | `1.027` | `0.775` |
| conversion actual prefill tokens | `11` | `11` |
| mature hit service ms | `208.385` | `209.457` |
| mature hit speedup vs cold baseline | `5.242x` | `6.836x` |
| mature hit actual prefill tokens | `11` | `11` |

The important change is budget discipline: M218 allowed the first duplicate request to be slightly slower than the cold baseline. M221 requires it to be materially faster while preserving mature cache-hit behavior.

## Quality

Quality threshold stayed PASS:

- deterministic quality verdict: `PASS`
- failures: `0`
- missing required markers: `0`
- visible thinking count: `0`
- max repetition score: `0.0`

## Implementation Notes

- `dax_first_hit_scheduling_sweep.py` now ranks request-conversion variants using `first_hit_service_request_ms`.
- The default `--max-conversion-ratio` is now `0.80`.
- The default `--min-first-hit-speedup` is now `5.0`.
- The observed first duplicate request still pays about `903.934 ms` in split-prefill cache preparation. That remains the next target if we want another large first-hit gain.
