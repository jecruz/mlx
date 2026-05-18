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

## M79 Result

M79 is complete for the stable Qwen A3B matrix.

Tracked artifacts:

- `benchmarks/python/async_maturation_sweep.py`
- `artifacts/m79-async-maturation/async-maturation-qwen-a3b-m79-stable.json`
- `artifacts/m79-async-maturation/async-maturation-qwen-a3b-m79-stable.jsonl`

Result summary:

- verdict: `PASS`
- stable combinations: `20`
- first-hit cache conversions: `8`
- mature-cache hits: `17`
- best steady-state mature reuse: `grace=0`, `wait=0`
  - baseline: `1713.12 ms`
  - mature hit: `248.66 ms`
  - speedup: `6.89x`
  - actual prefill: `9` tokens
- best first-hit conversion: `grace=0`, `wait=1000`
  - pending wait: `801.01 ms`
  - actual prefill: `10` tokens
  - first-hit speedup: `0.98x`, effectively break-even

Decision:

- `sync-safe` remains the default.
- `async-experimental` is useful for completed-cache reuse in repeated
  coding-agent context.
- Pending wait should not be enabled globally for interactive chat yet.
- The `Agent Workspace` profile should use tuned async only when repeated
  context reuse is expected.

Next target:

- Convert the M79 result into a named `agent-workspace-async` profile and a
  profile gate that verifies mature-cache reuse without requiring ad hoc sweep
  interpretation.

## M80 Result

M80 completed the M79 follow-through.

Added:

- `agent-workspace-async` runtime profile
- `benchmarks/python/async_maturation_gate.py`
- `artifacts/m80-agent-workspace-async/async-maturation-gate-qwen-a3b-m80.json`

Profile settings:

- `engine_preset=async-experimental`
- `prefix_cache_async_idle_grace_ms=0`
- `prefix_cache_pending_wait_ms=0`

Gate result:

- verdict: `PASS`
- mature hits: `17`
- mature speedup: `6.89x`
- mature prefill: `9` tokens
- mature service: `248.66 ms`
- first-hit conversions present: `8`

Decision:

- Use `agent-workspace-async` for repeated coding-agent context where mature
  cache reuse is expected.
- Keep `agent-workspace` for explicit pending-wait experiments.
- Keep `sync-safe` as the default until product profile selection is wired.

Next target:

- Wire workload-intent profile selection into the product/UI layer so coding
  agent sessions can choose `agent-workspace-async` without raw cache flags.

## M81 Result

M81 adds workload intent selection.

Added:

- `runtime_profile_for_intent` in `mlx_engine/ui_client.py`
- `EngineUiClient.apply_workload_intent`
- Dax `mlx-engine --intent <intent>`

Intent mapping:

- `coding-agent` -> `agent-workspace-async`
- `agent-workspace` -> `agent-workspace-async`
- `interactive` -> `interactive`
- `memory-saver` -> `memory-saver`
- `diagnostics` -> `diagnostics`

Validated:

- MLX UI client probe:
  `artifacts/m81-workload-intent/ui-client-adapter-m81.json`
- Dax focused test: `29` tests passed
- Dax typecheck passed
- Live Dax dry-run with `--intent coding-agent` returned the profile catalog
  including `agent-workspace-async` and left the active profile unchanged
  because `--dry-run` was used.

Next target:

- Use the intent signal automatically for coding-agent sessions instead of
  requiring an explicit `--intent coding-agent` flag.

## M82 Result

M82 makes the Dax coding-agent path automatic.

Behavior:

- `dax mlx-engine --prompt ...` auto-applies `coding-agent` intent.
- `dax mlx-engine --interactive` auto-applies `coding-agent` intent.
- `dax mlx-engine --once` and other status-only inspection remain read-only.
- Explicit `--profile` and `--intent` override the automatic default.

Validated:

- Dax focused test passed.
- Dax typecheck passed.

Next target:

- Measure the end-to-end coding-agent prompt path with automatic
  `agent-workspace-async` selection and compare it against the prior manual
  profile flow.
