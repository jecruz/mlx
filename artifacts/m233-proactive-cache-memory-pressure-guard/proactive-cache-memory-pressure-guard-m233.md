# M233 Proactive Cache Memory-Pressure Guard

Verdict: `PASS`
Readiness: `proactive-cache-memory-guard-ready`

## Profiles

| Profile | Max entries | Memory limit MB | Min entries |
| --- | ---: | ---: | ---: |
| `agent-workspace-first-hit` | `8` | `128.0` | `5` |
| `agent-workspace-low-memory` | `4` | `64.0` | `1` |

## Checks

| Check | Verdict | Actual | Threshold |
| --- | --- | ---: | ---: |
| `first_hit.prefix_cache_memory_limit_mb` | `PASS` | `128.0` | `<= 128.0` |
| `first_hit.prefix_cache_memory_limit_mb_nonzero` | `PASS` | `128.0` | `>= 1.0` |
| `first_hit.prefix_cache_max_entries` | `PASS` | `8` | `<= 8.0` |
| `first_hit.prefix_cache_min_entries` | `PASS` | `5` | `>= 5.0` |
| `low_memory.prefix_cache_memory_limit_mb` | `PASS` | `64.0` | `<= 64.0` |
| `low_memory.prefix_cache_max_entries` | `PASS` | `4` | `<= 4.0` |
| `low_memory.prefix_cache_min_entries` | `PASS` | `1` | `>= 1.0` |
| `m229.first_request.proactive_prefix_cache_created` | `PASS` | `5` | `>= 5.0` |
| `m229.first_request.proactive_prefix_cache_trim_failures` | `PASS` | `0` | `<= 0` |
| `m229.first_request.cache_memory_mb` | `PASS` | `20.817750930786133` | `<= 64.0` |
| `m230.first_duplicate_service_ms` | `PASS` | `193.0981669574976` | `<= 250.0` |
| `m230.first_duplicate_cache_hit` | `PASS` | `True` | `== True` |
| `m230.first_duplicate_prefill_tokens` | `PASS` | `11.0` | `<= 16.0` |
| `m230.mature_hit_speedup_vs_baseline` | `PASS` | `23.445196664976958` | `>= 5.0` |

## Failures

- none
