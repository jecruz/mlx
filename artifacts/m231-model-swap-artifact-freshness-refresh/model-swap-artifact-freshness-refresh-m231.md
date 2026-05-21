# M231 Model-Swap Artifact Freshness Refresh

M231 is complete. The lower-memory Qwen2.5 Coder 14B candidate now has fresh
M231 quality-threshold and model-swap acceptance artifacts, so Prowl's artifact
root reader can move from `STALE` to `PASS`.

## Artifacts

- `quality-threshold-gate-m231-qwen25-coder-14b-adapted.json`
- `model-swap-acceptance-m231-qwen25-coder-14b.json`
- `model-swap-acceptance-m231-qwen25-coder-14b.md`

## Acceptance Evidence

The M231 quality artifact was regenerated from the M229 adapted chat-template
quality artifact so the latest quality milestone matches the latest model-swap
milestone:

- quality verdict: `PASS`
- quality readiness: `ci-quality-ready`
- quality checks: `6`
- quality failures: `0`

The M231 model-swap artifact was generated from the M230 promotion gate plus the
fresh M231 quality threshold:

- swap decision: `ACCEPT`
- swap readiness: `swap-acceptable`
- swap checks: `10`
- swap blockers: `0`

## Prowl Validation

A temporary Prowl XCTest asserted the configured default MLX artifact root reads
the new artifacts as:

- root status: `PASS`
- quality status: `PASS`
- quality source:
  `artifacts/m231-model-swap-artifact-freshness-refresh/quality-threshold-gate-m231-qwen25-coder-14b-adapted.json`
- swap status: `PASS`
- swap decision: `ACCEPT`
- swap readiness: `swap-acceptable`
- swap source:
  `artifacts/m231-model-swap-artifact-freshness-refresh/model-swap-acceptance-m231-qwen25-coder-14b.json`
- issues: empty

The temporary test passed and was then removed so the Prowl repository stayed
clean.

## Performance Carry-Forward

M231 does not change the inference hot path. It preserves the M230 promotion
metrics:

| Metric | Value |
| --- | ---: |
| first duplicate service | `193.098 ms` |
| first duplicate prefill | `11` tokens |
| first duplicate cache hit | `true` |
| conversion ratio vs baseline | `0.043` |
| mature-hit speedup vs baseline | `23.445x` |
| max active memory | `11.028 GB` |
| max peak memory | `11.048 GB` |
| proactive prefix caches created | `5` |

Compared with M226, the lower-memory first duplicate service request remains
reduced from `3626.465 ms` to `193.098 ms`, a `3433.367 ms` / `94.68%`
improvement.

## Conclusion

M231 closes the artifact freshness gap that kept Prowl's artifact-root status
stale after the lower-memory candidate became promotable. The product-facing
artifact reader now has same-milestone quality and swap evidence for the chosen
candidate.
