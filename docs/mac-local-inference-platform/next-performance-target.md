# Next Performance Target Decision

Decision date: 2026-05-18

Evidence base:

- M64 Qwen A3B resident suite
- M68 cache-create optimization probe
- M70 calibrated thresholds
- M73 live runtime profile comparison
- M76 runtime profile comparison gate
- M77 packaged profile evidence

## Decision

Next target: **async cache maturation and pending-wait tuning**.

Do not promote `request-derived` for Qwen A3B right now.

Keep `sync-safe` as the reliable baseline profile.

## Why

M73 live comparison showed:

| Preset | Result | Interpretation |
| --- | --- | --- |
| `sync-safe` | `PASS` | Reliable cache-create and cache-hit behavior. |
| `async-experimental` | `SKIP` | Avoided foreground cache-create rows, but no cache hit matured in the short run. |
| `request-derived` | `FAIL` | Safe fallback paid foreground work and cache-hit speedup was worse than full prefill. |

The strongest signal is not paged KV or tokenizer overhead yet. The measured
gap is that async mode avoids foreground cache-create, but the cache is not
ready soon enough for the next related request.

## Ranking

1. **Async cache maturation and pending-wait tuning**
   - Highest-confidence next step.
   - Directly addresses M73 `async-experimental SKIP`.
   - Goal is to turn async from "scheduled but not useful yet" into "scheduled
     and hit by the next repeated prompt."

2. **Foreground cache-create reduction in sync-safe**
   - Still useful because `sync-safe` had `prepare_share=0.437`.
   - M76 gate now tracks this.
   - Lower priority than async maturation because sync-safe already works and
     request-derived did not improve this Qwen stack.

3. **JIT/warmup reduction**
   - Important for product startup and first-use experience.
   - Not the immediate bottleneck in the resident repeated-prompt path because
     the current work is measuring warm resident behavior.

4. **Tokenizer/chat-template overhead**
   - Worth measuring later.
   - Current evidence points more strongly at cache population timing and
     prompt-cache reuse behavior.

5. **Paged KV / lower-level cache storage**
   - Potentially important for large contexts and memory pressure.
   - Should wait until async maturation is measured because the current cache
     path already shows large wins when cache hits occur.

6. **Native service packaging**
   - Product-relevant, but not the next performance bottleneck.
   - Keep runbook and Dax integration moving in parallel, but do not let
     packaging hide engine performance work.

## M79 Proposal

Name: **Async Maturation Sweep**

Goal:

- Find the smallest async/pending-wait settings that turn `async-experimental`
  from `SKIP` into useful cache hits for repeated Qwen A3B prompts without
  hurting foreground latency too much.

Experiment matrix:

- `prefix_cache_async_idle_grace_ms`: `0`, `25`, `50`, `100`, `250`
- `prefix_cache_pending_wait_ms`: `0`, `250`, `500`, `1000`, `1500`
- repeated prompt shape: same bounded M73 shape first
- then longer prompt shape if the bounded shape succeeds

Required metrics:

- cache scheduled count
- async builds started/completed/skipped/failed
- pending wait hit/miss/timeout counts
- cache-hit service time
- cache-hit speedup versus full prefill
- foreground service cost added by pending wait

Acceptance criteria:

- At least one async profile produces cache hits in the repeated-prompt run.
- Cache-hit speedup is at least `2x` versus full prefill.
- Pending wait overhead does not exceed the cache-hit benefit.
- `runtime_profile_comparison_gate.py` passes for the selected async profile.

## Product Implication

Default profile should remain `sync-safe` until async maturation passes.

Future product profile mapping:

- `Interactive`: async with low or zero pending wait only after M79 passes.
- `Agent Workspace`: async with tuned pending wait if repeated coding-agent
  prompts reliably hit.
- `Diagnostics`: `sync-safe`.
- `Memory Saver`: existing memory-saver profile.
- `Request Derived`: keep experimental and model-dependent; do not expose as a
  recommended profile for Qwen A3B.
