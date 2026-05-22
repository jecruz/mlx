# M247 First-Hit Regression Recovery

Status: PASS

## Acceptance

Investigate and restore post-upstream `agent-workspace-first-hit` first duplicate service below the `250 ms` promotion budget while preserving best-hit latency and quality gates.

## Fresh Reproduction

Model:
`/Volumes/StudioStackSSD4TB/Development/LLM/lmstudio/models/lmstudio-community/Qwen2.5-Coder-14B-Instruct-MLX-4bit`

Server:
`http://127.0.0.1:8789`

Runtime profile:
`agent-workspace-first-hit`

Fresh benchmark commands:

```bash
python3 benchmarks/python/dax_repeated_context_bench.py \
  --base-url http://127.0.0.1:8789 \
  --client-mode resident \
  --dax-profile agent-workspace-first-hit \
  --output-jsonl artifacts/m247-first-hit-regression-recovery/dax-first-hit-m247-qwen25-coder-14b.jsonl \
  --output-json artifacts/m247-first-hit-regression-recovery/dax-first-hit-m247-qwen25-coder-14b.json \
  --turns 6 \
  --shared-repeats 64 \
  --max-tokens 4 \
  --max-hit-prefill-tokens 16 \
  --min-speedup 5 \
  --fail-on-fail

python3 benchmarks/python/dax_first_hit_conversion_gate.py \
  artifacts/m247-first-hit-regression-recovery/dax-first-hit-m247-qwen25-coder-14b.json \
  --output-json artifacts/m247-first-hit-regression-recovery/dax-first-hit-conversion-gate-m247-qwen25-coder-14b.json \
  --max-conversion-prefill-tokens 16 \
  --max-conversion-ratio 0.85 \
  --conversion-path any \
  --min-mature-hit-speedup 5 \
  --max-mature-hit-prefill-tokens 16 \
  --fail-on-fail
```

## Results

- benchmark verdict: `PASS`
- conversion gate verdict: `PASS`
- baseline service: `4617.073 ms`
- first duplicate service: `185.660 ms`
- first duplicate prompt progress last: `174.469 ms`
- best hit service: `179.281 ms`
- best hit prompt progress last: `168.114 ms`
- best-hit speedup: `25.753x`
- hit count: `5`

## Comparison To M246

- M246 first duplicate service: `265.968 ms`
- M247 first duplicate service: `185.660 ms`
- delta: `-80.308 ms` / `-30.195%`
- M246 best hit service: `183.477 ms`
- M247 best hit service: `179.281 ms`
- delta: `-4.196 ms` / `-2.287%`
- M246 first duplicate prompt progress last: `254.571 ms`
- M247 first duplicate prompt progress last: `174.469 ms`
- delta: `-80.102 ms`

## Conclusion

The post-upstream first-duplicate regression observed in M246 is not reproducible on a fresh run. The recovered run is back under the `250 ms` budget, keeps the mature-hit speedup well above threshold, and passes the first-hit conversion gate.
