# M231 Lower-Memory Model Swap Acceptance

Verdict: `PASS`
Swap decision: `ACCEPT`
Readiness: `swap-acceptable`

## Candidate

- Model: `/Volumes/StudioStackSSD4TB/Development/LLM/lmstudio/models/lmstudio-community/Qwen2.5-Coder-14B-Instruct-MLX-4bit`
- Promotion gate: `artifacts/m230-lower-memory-profile-promotion-gate/lower-memory-profile-promotion-gate-m230-qwen25-coder-14b.json`
- Quality threshold: `artifacts/m231-model-swap-artifact-freshness-refresh/quality-threshold-gate-m231-qwen25-coder-14b-adapted.json`

## Metrics

| Metric | Value |
| --- | ---: |
| `conversion_ratio_vs_baseline` | `0.04265265991536023` |
| `first_duplicate_cache_created` | `False` |
| `first_duplicate_cache_hit` | `True` |
| `first_duplicate_prefill_tokens` | `11.0` |
| `first_duplicate_service_ms` | `193.0981669574976` |
| `mature_hit_speedup_vs_baseline` | `23.445196664976958` |
| `max_active_memory_gb` | `11.027572744` |
| `max_peak_memory_gb` | `11.048436144` |
| `proactive_prefix_cache_created` | `5.0` |

## Checks

| Check | Verdict | Detail |
| --- | --- | --- |
| `promotion_gate.verdict` | `PASS` | `verdict='PASS'` |
| `promotion_gate.readiness` | `PASS` | `readiness='lower-memory-profile-promotable'` |
| `promotion_gate.failure_count` | `PASS` | `failures=0` |
| `quality_threshold.verdict` | `PASS` | `verdict='PASS'` |
| `quality_threshold.readiness` | `PASS` | `readiness='ci-quality-ready'` |
| `quality_threshold.failure_count` | `PASS` | `failures=0` |
| `candidate.first_duplicate_cache_hit` | `PASS` | `cache_hit=True` |
| `candidate.first_duplicate_service_ms` | `PASS` | `actual=193.0981669574976, threshold=250.0` |
| `candidate.max_peak_memory_gb` | `PASS` | `actual=11.048436144, threshold=12.0` |
| `candidate.mature_hit_speedup` | `PASS` | `actual=23.445196664976958, threshold=5.0` |

## Blockers

- none
