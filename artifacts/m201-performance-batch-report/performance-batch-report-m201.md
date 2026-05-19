# M201 Performance Batch Report

Verdict: `PASS`
Readiness: `performance-batch-reported`

## Performance

- baseline service request: `1411.08045889996 ms`
- mature reusable-turn service request: `204.03116615489125 ms`
- speedup vs baseline: `6.91600447859388x`
- max active memory: `21.02259841 GB`
- target mature hit: `175.0 ms`
- required reduction: `29.031 ms`

## Next Milestones

- `M202`: Cache lookup fast-path implementation - mature reusable-turn latency improves while quality threshold stays PASS
- `M203`: Tokenized prompt reuse probe - identical repeated workspace prompts reduce prompt overhead without route bleed
- `M204`: Async cache completion wait sweep - conversion-turn latency improves without queue wait regression
- `M205`: Response metrics trim experiment - hot response overhead drops and operator debug mode preserves full metrics
- `M206`: Live performance suite rerun - M180-equivalent suite stays PASS with quality threshold PASS
- `M207`: Prowl/UI readiness endpoint smoke - Prowl or UI-side probe consumes /engine/operator-readiness
- `M208`: Candidate model registry refresh - registry includes any new smaller/lower-memory candidates
- `M209`: Performance report refresh - new report shows latency delta versus M194 baseline

## Failures

- none
