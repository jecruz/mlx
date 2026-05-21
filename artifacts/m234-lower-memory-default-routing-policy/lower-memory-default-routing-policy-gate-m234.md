# M234 Lower-Memory Default-Routing Policy Gate

Verdict: `PASS`
Readiness: `lower-memory-default-routing-ready`

## Default When

- explicit low_memory=true
- memory_class_gb is 16, 24, or 32
- workload_intent is low-memory or coding-agent-low-memory

## Do Not Default When

- manual profile override is present
- interactive foreground work is non-agentic
- diagnostics workload is requested
- 64GB+ agentic work without low-memory signal should use agent-workspace-async
- immediate second-turn work without low-memory signal should use agent-workspace-first-hit

## Checks

| Check | Verdict | Detail |
| --- | --- | --- |
| `auto_selection_gate` | `PASS` | `verdict='PASS'` |
| `route.lower_memory_mac_32gb` | `PASS` | `observed='agent-workspace-low-memory', expected='agent-workspace-low-memory'` |
| `route.manual_override` | `PASS` | `observed='agent-workspace-first-hit', expected='agent-workspace-first-hit'` |
| `route.normal_coding_agent` | `PASS` | `observed='agent-workspace-async', expected='agent-workspace-async'` |
| `route.immediate_second_turn` | `PASS` | `observed='agent-workspace-first-hit', expected='agent-workspace-first-hit'` |
| `route.interactive_foreground` | `PASS` | `observed='interactive', expected='interactive'` |
| `route.diagnostics` | `PASS` | `observed='diagnostics', expected='diagnostics'` |
| `model_swap_acceptance` | `PASS` | `decision='ACCEPT', readiness='swap-acceptable'` |
| `quality_threshold` | `PASS` | `verdict='PASS', readiness='ci-quality-ready'` |
| `memory_guard` | `PASS` | `verdict='PASS'` |
| `first_duplicate_service_budget` | `PASS` | `first_duplicate_service_ms=193.0981669574976` |
| `first_duplicate_cache_hit` | `PASS` | `cache_hit=True` |

## Failures

- none
