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

## M83 Result

M83 measured automatic coding-agent intent against the explicit/manual flows.

Added:

- `benchmarks/python/dax_workload_intent_prompt_bench.py`
- `artifacts/m83-dax-workload-intent/dax-workload-intent-qwen-a3b-m83.json`
- `artifacts/m83-dax-workload-intent/dax-workload-intent-qwen-a3b-m83.jsonl`

Compared:

- automatic: `dax mlx-engine --prompt ...`
- explicit intent: `dax mlx-engine --intent coding-agent --prompt ...`
- manual profile: `dax mlx-engine --profile agent-workspace-async --prompt ...`

Result:

- verdict: `PASS`
- all paths applied `agent-workspace-async`
- auto/manual-profile wall-time ratio: `0.998`
- auto/explicit-intent wall-time ratio: `1.000`

Decision:

- Keep automatic coding-agent intent enabled.
- It is operationally simpler and equivalent to the manual profile flow in the
  measured end-to-end path.

Next target:

- Measure repeated coding-agent prompts with shared context to verify the
  automatic path realizes M79 mature-cache reuse under realistic multi-turn
  usage.

## M84 Result

M84 measured repeated automatic Dax coding-agent prompts with shared context.

Added:

- `benchmarks/python/dax_repeated_context_bench.py`
- `artifacts/m84-dax-repeated-context/dax-repeated-context-qwen-a3b-m84.json`
- `artifacts/m84-dax-repeated-context/dax-repeated-context-qwen-a3b-m84.jsonl`

Result:

- verdict: `PASS`
- cache-hit turns: `2`
- baseline service: `1670.83 ms`
- best hit service: `234.69 ms`
- speedup: `7.12x`
- baseline prefill: `2092` tokens
- best-hit prefill: `18` tokens

Decision:

- The automatic Dax coding-agent path realizes mature cache reuse in repeated
  shared-context usage.

## M85 Result

M85 added a regression gate around the repeated-context Dax benchmark.

Added:

- `benchmarks/python/dax_repeated_context_gate.py`
- `artifacts/m85-dax-repeated-context-gate/dax-repeated-context-gate-qwen-a3b-m85.json`

Gate thresholds:

- source benchmark verdict must be `PASS`
- cache-hit turns must be at least `1`
- best-hit speedup must be at least `2.0x`
- baseline prefill must be at least `512` tokens
- best-hit prefill must be at most `32` tokens
- best-hit service latency must be at most `400.0 ms`

Result:

- verdict: `PASS`
- cache-hit turns: `2`
- best-hit speedup: `7.12x`
- baseline prefill: `2092` tokens
- best-hit prefill: `18` tokens
- best-hit service latency: `234.69 ms`

Decision:

- The automatic Dax coding-agent product path now has an explicit regression
  gate for repeated shared-context cache reuse.

## M86 Result

M86 folded the M84 benchmark and M85 gate into the resident/operator suite.

Added:

- `run_resident_regression_suite.py --include-dax-repeated-context`
- `dax_repeated_context_report` in suite manifests
- `dax_repeated_context_gate_report` in suite manifests
- `dax_repeated_context_gate PASS|FAIL` in suite manifest summaries

Artifacts:

- `artifacts/m86-dax-suite-product-path/dax-repeated-context-m86-qwen-a3b-dax-product.jsonl`
- `artifacts/m86-dax-suite-product-path/dax-repeated-context-m86-qwen-a3b-dax-product.json`
- `artifacts/m86-dax-suite-product-path/dax-repeated-context-gate-m86-qwen-a3b-dax-product.json`
- `artifacts/m86-dax-suite-product-path/resident-regression-suite-m86-qwen-a3b-dax-product.json`

Result:

- suite verdict: `PASS`
- Dax product-path gate: `PASS`
- cache-hit turns: `2`
- best-hit speedup: `22.06x`
- baseline prefill: `2092` tokens
- best-hit prefill: `18` tokens
- best-hit service latency: `241.70 ms`

Decision:

- Future Dax, TUI, and UI changes can run the product-path repeated-context
  regression from the resident suite command instead of hand-assembling the
  benchmark and gate.
- The step remains opt-in so lower-level resident suites do not depend on the
  external Dax checkout unless product-path coverage is requested.

## M87 Result

M87 packaged the M86 product-path suite evidence through the existing resident
suite evidence flow.

Added:

- `gate` summary in `resident-suite-evidence-index.json`
- `dax_repeated_context` summary in `resident-suite-evidence-index.json`

Artifact:

- `artifacts/m87-dax-product-evidence-package/resident-suite-evidence-index.json`

Result:

- suite verdict: `PASS`
- Dax product-path gate: `PASS`
- copied artifacts: `4`
- missing optional artifacts: `4`
- cache-hit turns: `2`
- best-hit speedup: `22.06x`
- baseline prefill: `2092` tokens
- best-hit prefill: `18` tokens
- best-hit service latency: `241.70 ms`

Decision:

- Product-path evidence packages now contain a compact machine-readable summary
  for Redmine, Dax, CI, and future app surfaces.
- Raw benchmark, JSONL rows, gate report, and suite manifest are still copied
  for deeper debugging.

Next target:

- Decide and implement whether Dax `/bench run` should expose the opt-in
  product-path suite flag directly, likely as a named mode rather than a raw
  pile of suite-runner flags.
