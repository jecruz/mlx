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

## M88 Result

M88 exposed the product-path suite from Dax as a named benchmark mode.

Dax commit:

- `e8f5da12 Add MLX product bench mode`

Command:

```text
/bench run product <mlx-worktree> [output-dir] [tag]
```

Compatibility:

- `/bench run <mlx-worktree> [output-dir] [tag]` still runs the resident suite.
- `/bench run resident <mlx-worktree> [output-dir] [tag]` explicitly runs the
  resident suite.

Validation:

- Dax focused MLX test: `30` tests passed.
- Dax coding-agent typecheck passed.
- Dax pre-commit checks passed.

Decision:

- Product-path benchmark coverage is now reachable from the TUI as an operator
  mode instead of as raw suite-runner flags.

## M89 Result

M89 ran the new Dax product benchmark mode against the live Qwen A3B resident
server through the Dax panel command handler.

Command:

```text
/bench run product /Users/jeffreycruz/Development/LLM_INFERENCE/mlx/.worktrees/prompt-processing-bench artifacts/m89-dax-operator-product-run m89-qwen-a3b-dax-product
```

Result:

- suite verdict: `PASS`
- Dax product-path gate: `PASS`
- cache-hit turns: `2`
- best-hit speedup: `19.20x`
- baseline prefill: `2092` tokens
- best-hit prefill: `18` tokens
- best-hit service latency: `227.23 ms`

Decision:

- Product-path repeated-context performance is now proven through the
  operator-facing Dax command path.
- Steady-state repeated-context reuse is no longer the weakest link.

## M90 Result

M90 added a focused gate for first-hit latency and async build scheduling.

Added:

- `benchmarks/python/dax_first_hit_latency_gate.py`
- `artifacts/m90-first-hit-latency/dax-first-hit-latency-gate-m90-qwen-a3b.json`

Result:

- verdict: `PASS`
- scheduled pre-hit service: `1386.49 ms`
- scheduled pre-hit ratio vs baseline: `0.318`
- scheduled pre-hit prefill: `2092` tokens
- first-hit speedup vs baseline: `19.20x`
- first-hit prefill: `18` tokens

Decision:

- The first-hit/cache-build turn is now separately measurable and gateable.
- The current bottleneck is not mature reuse. It is the scheduled pre-hit turn
  that still performs full prefill before the next request can benefit.

Next target:

- Tune async build scheduling to reduce the scheduled pre-hit cost below the
  current `1386.49 ms` baseline or convert the scheduled pre-hit turn into a
  bounded pending-wait hit.
- Preserve the mature-hit target: `<= 32` actual prefill tokens, with current
  evidence at `18` tokens.
- Keep lower-memory product profiles as the next product track after first-hit
  latency is bounded.

## M91 Result

M91 swept existing Dax profile choices against the M90 first-hit gate.

Added:

- `benchmarks/python/dax_first_hit_scheduling_sweep.py`
- Dax profile/intent forwarding in
  `benchmarks/python/dax_repeated_context_bench.py`
- `artifacts/m91-first-hit-scheduling-sweep/dax-first-hit-scheduling-sweep-m91-qwen-a3b.json`

Result:

- sweep verdict: `PASS`
- first-hit target verdict: `FAIL`
- variants: `auto`, `agent-workspace`, `agent-workspace-async`
- best observed variant: `agent-workspace`
- best observed scheduled pre-hit service: `1375.97 ms`
- best observed scheduled pre-hit ratio vs baseline: `0.971`
- scheduled pre-hit prefill: `2092` tokens
- first mature hit: `231.92 ms`, `18` prefill tokens, `6.11x` speedup

Decision:

- Existing Dax profile selection does not materially reduce first-hit latency.
- The scheduled pre-hit/cache-build turn is still a full-prefill request.
- Next target is M92: add a first-hit conversion behavior or profile that makes
  the second repeated-context turn wait for or use the pending build instead of
  doing a full `2092` token prefill.

## M92 Result

M92 adds a named first-hit conversion profile and a gate for the second
repeated-context turn.

Added:

- runtime profile `agent-workspace-first-hit`
- `benchmarks/python/dax_first_hit_conversion_gate.py`
- `artifacts/m92-first-hit-conversion/dax-repeated-context-m92-request-probe.json`
- `artifacts/m92-first-hit-conversion/dax-first-hit-conversion-gate-m92-request-probe.json`

Result:

- first-hit conversion gate: `PASS`
- conversion turn: `2`
- conversion actual prefill: `18` tokens
- conversion service ratio vs baseline: `0.813`
- conversion path: `cache_split_prefill=True`
- mature hit speedup: `2.94x`
- mature hit actual prefill: `18` tokens

Decision:

- The product now has a clear profile name for first-hit conversion:
  `agent-workspace-first-hit`.
- The profile is backed by request-derived cache behavior, which converts the
  first duplicate request immediately but has weaker latency than mature async
  reuse.
- Next target is M93: make this first-hit behavior a product-path regression
  gate so Dax/product runs cannot silently fall back to full-prefill second
  turns.

## M93 Result

M93 adds a one-command Dax product-path regression gate for first-hit
conversion.

Added:

- `benchmarks/python/dax_product_first_hit_gate.py`
- `artifacts/m93-product-first-hit-gate/dax-product-first-hit-summary-m93-qwen-a3b-request-profile.json`

Result:

- product first-hit gate: `PASS`
- conversion turn: `2`
- conversion actual prefill: `18` tokens
- conversion service ratio vs baseline: `0.843`
- mature hit speedup: `2.996x`
- mature hit actual prefill: `18` tokens

Decision:

- Product-path first-hit conversion is now regression-gated.
- The gate catches the exact M91 failure mode: a second repeated-context turn
  falling back to full prefill instead of converting.
- Next target is M94: route Dax product mode to the first-hit profile when the
  product wants immediate second-turn latency rather than pure steady-state
  async reuse.

## M94 Result

M94 integrates first-hit product validation into the resident suite manifest and
evidence-package path.

Added:

- `run_resident_regression_suite.py --include-dax-first-hit`
- `run_resident_regression_suite.py --dax-first-hit-profile`
- manifest fields for first-hit benchmark, gate, summary, and JSONL artifacts
- suite summary output for `dax_first_hit`
- evidence-package summary for `dax_first_hit`

Result:

- suite verdict: `PASS`
- `dax_first_hit`: `PASS`
- conversion turn: `2`
- conversion actual prefill: `18` tokens
- conversion ratio vs baseline: `0.837`
- mature hit speedup: `3.052x`
- mature hit actual prefill: `18` tokens

Decision:

- Product validation can now include first-hit conversion from the resident
  suite, not only from standalone scripts.
- The first-hit gate remains opt-in so lower-level resident regression runs do
  not require Dax.
- Next target is M95: lower-memory product profile validation.

## M95 Result

M95 adds a lower-memory agent product profile and validates bounded first-hit
behavior under memory-saver constraints.

Added:

- runtime profile `agent-workspace-low-memory`
- `--conversion-path split-prefill|any` for first-hit conversion gates
- `--dax-first-hit-conversion-path` for resident suite first-hit runs

Profile:

- `engine_preset=request-derived`
- `prefix_cache_population_mode=request`
- `prefix_cache_max_entries=4`
- `prefix_cache_memory_limit_mb=64.0`
- `prefix_cache_min_entries=1`

Result:

- lower-memory first-hit gate: `PASS`
- compatibility profile used: `memory-saver`
- conversion turn: `2`
- conversion actual prefill: `18` tokens
- conversion ratio vs baseline: `0.588`
- mature hit speedup: `3.581x`
- mature hit actual prefill: `18` tokens

Decision:

- Lower-memory product behavior now has a named profile and a regression path.
- The profile should be offered separately from the default coding-agent mode
  because it trades cache capacity for safer memory behavior.
- Next target is M96: performance decision report and default-routing
  recommendation.

## M96 Result

M96 adds the artifact-backed performance decision report:

- `docs/mac-local-inference-platform/performance-decision-report-m91-m96.md`

Default routing recommendation:

- `agent-workspace-async` for long-running repeated-context coding-agent work.
- `agent-workspace-first-hit` for immediate second-turn responsiveness.
- `agent-workspace-low-memory` for smaller-memory Macs or bounded cache
  residency.
- `interactive` for ordinary foreground interaction.
- `diagnostics` for stable readiness/probe runs.

Next target after M96:

- Restart the resident server on the new code and rerun product gates with the
  new profile names directly.
- Wire these profile choices into the product UI/Dax product mode.

## M97 Result

M97 restarted the resident server on the updated worktree and validated
`agent-workspace-first-hit` directly.

Result:

- profile catalog includes `agent-workspace-first-hit`
- direct product first-hit gate: `PASS`
- resident suite first-hit path: `PASS`
- direct conversion turn: `2`
- direct conversion actual prefill: `18` tokens
- direct conversion ratio vs baseline: `0.783`
- direct mature hit speedup: `2.454x`
- suite conversion ratio vs baseline: `0.785`
- suite mature hit speedup: `2.382x`

Decision:

- `agent-workspace-first-hit` is now live-validated by name.
- Next target is M98: validate `agent-workspace-low-memory` directly by name.

## M98 Result

M98 validated `agent-workspace-low-memory` directly after server restart.

Result:

- direct product first-hit gate: `PASS`
- resident suite first-hit path: `PASS`
- direct conversion turn: `2`
- direct conversion actual prefill: `18` tokens
- direct conversion ratio vs baseline: `0.776`
- direct mature hit speedup: `2.585x`
- suite conversion ratio vs baseline: `0.797`
- suite mature hit speedup: `2.417x`

Decision:

- `agent-workspace-low-memory` is now live-validated by name.
- Next target is M99: wire product/Dax routing so operators can select async,
  first-hit, or low-memory profile modes intentionally.

## M99 Result

M99 wires the profile decisions into Dax product/operator commands.

Added in Dax commit `167cac48`:

- workload intents:
  - `first-hit` -> `agent-workspace-first-hit`
  - `coding-agent-first-hit` -> `agent-workspace-first-hit`
  - `low-memory` -> `agent-workspace-low-memory`
  - `coding-agent-low-memory` -> `agent-workspace-low-memory`
- benchmark modes:
  - `/bench run product-first-hit ...`
  - `/bench run product-low-memory ...`
- manifest summary support for `dax_first_hit_summary_report`

Validation:

- Dax MLX status test file: `31 passed`
- Dax typecheck: `tsgo --noEmit` passed
- Dax Biome check on changed files passed
- Dax diff whitespace check passed

Decision:

- Operators can now intentionally select steady-state async, first-hit, and
  lower-memory product paths from Dax instead of manually mapping raw MLX
  profiles.
- Next target is M100: produce an end-to-end operator wall-time report so
  service-time improvements are compared against actual command/operator
  elapsed time.

## M100 Result

M100 adds an operator wall-time report:

- script: `benchmarks/python/dax_operator_wall_time_report.py`
- artifact:
  `artifacts/m100-operator-wall-time/dax-operator-wall-time-m100-qwen-a3b.json`

Result:

- report verdict: `PASS`
- cases covered:
  - M97 first-hit direct
  - M97 first-hit suite
  - M98 low-memory direct
  - M98 low-memory suite
- mature service speedups: `2.382x` to `2.585x`
- mature wall-time speedups: `1.425x` to `2.190x`
- mean operator overhead: about `1512 ms` to `1922 ms`
- mean service share of wall time: about `0.346` to `0.389`

Decision:

- Resident engine service-time gains are confirmed.
- Product-visible wall-time gains are materially lower because the Dax command
  path still spends roughly `1.5s+` outside resident engine service time.
- Next target is M101: add a default profile decision gate that requires the
  async, first-hit, low-memory, and wall-time evidence before claiming the
  default product profile decision is ready.

## M101 Result

M101 adds a default profile decision gate:

- script: `benchmarks/python/dax_default_profile_decision_gate.py`
- artifact:
  `artifacts/m101-default-profile-decision-gate/default-profile-decision-gate-m101-qwen-a3b.json`

Evidence required by the gate:

- M80 async maturation gate
- M97 direct first-hit profile summary
- M98 direct low-memory profile summary
- M100 operator wall-time report
- M96 performance decision report
- M99 routing documentation

Result:

- gate verdict: `PASS`
- checks: `20`
- failures: `0`
- async mature speedup: `6.889x`
- first-hit mature speedup: `2.454x`
- low-memory mature speedup: `2.585x`
- minimum mature wall-time speedup across M100 cases: `1.425x`

Decision:

- Default coding-agent profile: `agent-workspace-async`
- Immediate second-turn profile: `agent-workspace-first-hit`
- Lower-memory Mac profile: `agent-workspace-low-memory`
- Next target is M102: expose these gate-backed profile choices clearly in the
  operator/product control surface.

## M102 Result

M102 exposes the gate-backed profile choices in Dax:

- Dax commit: `08c14b5d`
- `/profile default` -> `agent-workspace-async`
- `/profile coding-agent` -> `agent-workspace-async`
- `/profile async` -> `agent-workspace-async`
- `/profile first-hit` -> `agent-workspace-first-hit`
- `/profile low-memory` -> `agent-workspace-low-memory`
- `/profiles` and `/profile recommended` print readable shortcut mappings.

Validation:

- Dax MLX status test file: `31 passed`
- Dax typecheck: `tsgo --noEmit` passed
- Dax Biome check on changed files passed
- Dax diff whitespace check passed
- Dax pre-commit full check passed during commit.

Decision:

- Product operators no longer need to memorize raw profile names for the main
  gate-backed modes.
- The next performance lane should move from profile selection to reducing
  operator wall-time overhead and broadening prompt-processing sweeps.

## M103 Result

M103 converts the M100 wall-time finding into a measurable reduction target:

- script: `benchmarks/python/dax_operator_overhead_reduction_report.py`
- artifact:
  `artifacts/m103-operator-overhead-reduction/operator-overhead-reduction-m103-qwen-a3b.json`

Result:

- report verdict: `PASS`
- cases covered: `4`
- mean operator overhead: `1635.49 ms`
- maximum operator overhead: above the `1000 ms` warning threshold
- target operator overhead: `500 ms`
- projected mature-turn wall-time reduction: about `47.4%`

Decision:

- Avoiding per-request Dax CLI process startup is now the primary product
  overhead target.
- Product gates should continue reporting both `wall_ms` and
  `service_request_ms`.
- Next target is M104: broaden prompt-processing evidence so the next engine
  work distinguishes raw prompt bottlenecks from operator overhead.

## M104 Result

M104 extracts prompt-processing behavior from existing product-path JSONL
traces:

- script: `benchmarks/python/dax_prompt_processing_extension_report.py`
- artifact:
  `artifacts/m104-prompt-processing-extension/prompt-processing-extension-m104-qwen-a3b.json`

Result:

- report verdict: `PASS`
- rows analyzed: `16`
- long-prefill rows: `4`
- short-prefill rows: `12`
- long-prefill mean service time: `1510.54 ms`
- long-prefill prompt-progress share of service: `0.970`
- short-prefill mean service time: `840.77 ms`
- short-prefill prompt-progress share of service: `0.670`

Decision:

- Prompt processing remains a dominant service-time component even after cache
  and split-prefill reduction.
- The next sweep should vary prompt length, reuse ratio, Dax transport, and
  profile together.
- Next target is M105: define and gate the fast Dax invocation path that should
  reduce operator overhead without hiding prompt-processing bottlenecks.

## M105 Result

M105 defines the fast Dax invocation path:

- script: `benchmarks/python/dax_fast_invocation_path_report.py`
- artifact:
  `artifacts/m105-fast-dax-invocation/fast-dax-invocation-m105-qwen-a3b.json`

Result:

- report verdict: `PASS`
- recommended path: `resident-dax-client`
- current mean operator overhead: `1635.49 ms`
- acceptance target: `<=500 ms`
- transport order:
  - in-process Dax panel/client call
  - resident Dax local RPC/IPC client
  - direct HTTP client to MLX resident service
  - fallback `npx`/`tsx` CLI process

Decision:

- The next product implementation should keep Dax hot and reuse its MLX client
  state for repeated turns.
- The fast path must preserve `wall_ms`, `service_request_ms`, and
  `overhead_ms`.
- Next target is M106: define the profile auto-selection policy on top of the
  gate-backed profiles and operator controls.

## M106 Result

M106 defines and validates the profile auto-selection policy:

- script: `benchmarks/python/dax_profile_auto_selection_policy.py`
- artifact:
  `artifacts/m106-profile-auto-selection/profile-auto-selection-m106-qwen-a3b.json`

Result:

- policy verdict: `PASS`
- scenarios: `6`
- failures: `0`
- normal coding-agent -> `agent-workspace-async`
- immediate second turn -> `agent-workspace-first-hit`
- lower-memory Mac -> `agent-workspace-low-memory`
- interactive foreground -> `interactive`
- diagnostics -> `diagnostics`
- manual override preserved

Decision:

- Auto-selection should be policy-driven with manual override support.
- Low-memory selection should happen before generic repeated-workspace async
  selection.
- Next target is M107: make the lower-memory Mac runtime strategy concrete.

## M107 Result

M107 makes the lower-memory Mac strategy concrete:

- script: `benchmarks/python/mlx_lower_memory_mac_strategy.py`
- artifact:
  `artifacts/m107-lower-memory-mac-strategy/lower-memory-mac-strategy-m107-qwen-a3b.json`

Result:

- strategy verdict: `PASS`
- validated low-memory profile: `agent-workspace-low-memory`
- 16-24GB Macs: planned lower-memory/offload lane, prefer smaller MoE active
  parameter models or 4-bit MLX models
- 32GB Macs: use `agent-workspace-low-memory` by default
- 64GB+ Macs: use `agent-workspace-async` unless first-hit or memory pressure
  signals override

Decision:

- The AirLLM/layer-offload idea belongs behind a lower-memory feature flag,
  not in the default 64GB+ path.
- Lower-memory gates must report peak memory and cache memory limits, not only
  latency.
- Next target is M108: package the completed profile, overhead, prompt, and
  low-memory evidence into a product readiness bundle.

## M108 Result

M108 packages the lane into a product readiness bundle:

- script: `benchmarks/python/mlx_product_readiness_bundle.py`
- artifact:
  `artifacts/m108-product-readiness-bundle/product-readiness-bundle-m108-qwen-a3b.json`

Result:

- bundle verdict: `PASS`
- readiness: `ready-for-next-implementation-lane`
- evidence artifacts: `9`
- failures: `0`

Included evidence:

- M97 first-hit direct evidence
- M98 low-memory direct evidence
- M100 wall-time report
- M101 default profile decision gate
- M103 overhead target
- M104 prompt-processing extension
- M105 fast invocation path
- M106 auto-selection policy
- M107 lower-memory strategy

Next implementation lane:

- Implement `resident-dax-client`.
- Add `overhead_ms` gate to product benchmark rows.
- Run extended prompt sweep across `512/1024/2048/4096` prompt tokens.
- Add lower-memory peak-memory and cache-limit gates.
- Use auto-selection policy in the product control surface.

## M109 Result

M109 implements the resident Dax client benchmark path:

- updated script: `benchmarks/python/dax_repeated_context_bench.py`
- readiness script: `benchmarks/python/dax_resident_client_readiness_report.py`
- artifact:
  `artifacts/m109-resident-dax-client/resident-dax-client-m109-qwen-a3b.json`

Result:

- readiness verdict: `PASS`
- checks: `5`
- failures: `0`
- new mode: `--client-mode resident`
- fallback mode: `--client-mode cli`
- direct endpoint: `/v1/completions`
- benchmark rows now include `overhead_ms`

Decision:

- The harness can now bypass per-request Dax CLI startup for product-path
  timing.
- Live timing validation requires the resident MLX server to be running on
  `127.0.0.1:8773`.
- Next target is M110: add an overhead gate around the new `overhead_ms` row
  field.

## M110 Result

M110 adds the operator overhead gate:

- script: `benchmarks/python/dax_operator_overhead_gate.py`
- artifact:
  `artifacts/m110-overhead-gate/operator-overhead-gate-m110-current-baseline.json`

Result:

- gate verdict: `PASS`
- input: M100 wall-time report
- rows: `16`
- mean overhead: `1635.49 ms`
- current baseline threshold: `<=2000 ms`

Decision:

- `overhead_ms` is now gateable for JSONL rows and wall-time reports.
- The M103 fast-path target remains `<=500 ms`; the current CLI baseline does
  not satisfy that target and should not be treated as optimized.
- Next target is M111: define and package the extended prompt sweep matrix.

## M111 Result

M111 defines the extended prompt sweep matrix:

- script: `benchmarks/python/extended_prompt_sweep_matrix.py`
- artifact:
  `artifacts/m111-extended-prompt-sweep/extended-prompt-sweep-matrix-m111-qwen-a3b.json`

Result:

- matrix verdict: `PASS`
- cases: `72`
- prompt tokens: `512`, `1024`, `2048`, `4096`
- reuse modes: `none`, `first-hit`, `mature-hit`
- transports: `cli`, `resident`
- profiles: `agent-workspace-async`, `agent-workspace-first-hit`,
  `agent-workspace-low-memory`

Decision:

- Live sweeps must include `overhead_ms`, prompt progress, and peak memory.
- The resident transport must be tested beside the CLI path.
- Next target is M112: add lower-memory peak-memory/cache-limit gates.

## M112 Result

M112 adds lower-memory runtime gates:

- script: `benchmarks/python/lower_memory_runtime_gate.py`
- artifact:
  `artifacts/m112-lower-memory-gate/lower-memory-runtime-gate-m112-qwen-a3b.json`

Result:

- gate verdict: `PASS`
- rows: `4`
- observed profile: `agent-workspace-low-memory`
- max peak memory: `22.682 GB`
- cache memory limit: `64 MB`
- conversion prefill: `18` tokens

Decision:

- Lower-memory mode now has memory and cache-limit acceptance checks.
- The next lower-memory live run should execute this gate on target 16-24GB
  and 32GB hardware.
- Next target is M113: integrate the auto-selection policy into product
  readiness checks.

## M113 Result

M113 adds auto-selection integration gating:

- script: `benchmarks/python/profile_auto_selection_integration_gate.py`
- artifact:
  `artifacts/m113-auto-selection-integration/auto-selection-integration-gate-m113-qwen-a3b.json`

Result:

- gate verdict: `PASS`
- checks: `5`
- failures: `0`
- required scenarios covered:
  - normal coding-agent
  - immediate second turn
  - lower-memory Mac
  - interactive foreground
  - diagnostics
  - manual override

Decision:

- Auto-selection is now part of readiness gating.
- Product implementation must preserve manual override.
- Next target is M114: combine M109-M113 into a readiness regression suite.

## M114 Result

M114 adds the product runtime readiness regression suite:

- script: `benchmarks/python/product_runtime_readiness_suite.py`
- artifact:
  `artifacts/m114-readiness-regression-suite/product-runtime-readiness-suite-m114-qwen-a3b.json`

Result:

- suite verdict: `PASS`
- readiness: `ready-for-live-resident-client-validation`
- evidence artifacts: `5`
- failures: `0`

Covered milestones:

- M109 resident Dax client benchmark path
- M110 operator overhead gate
- M111 extended prompt sweep matrix
- M112 lower-memory runtime gate
- M113 auto-selection integration gate

Next live validation:

- Start the resident MLX server.
- Run `dax_repeated_context_bench.py --client-mode resident`.
- Gate the resulting JSONL with
  `dax_operator_overhead_gate.py --max-mean-overhead-ms 500 --fail-on-fail`.

## M115-M120 Live Result

The resident MLX server is now live-validated against the Qwen3.6-35B-A3B MLX
model path:

- model:
  `/Volumes/StudioStackSSD4TB/Development/LLM/lmstudio/models/unsloth/Qwen3.6-35B-A3B-UD-MLX-4bit`
- M115 resident repeated-context benchmark:
  - artifact:
    `artifacts/m115-live-resident-client/dax-resident-client-m115-qwen-a3b.json`
  - verdict: `PASS`
  - hit count: `2`
  - best hit speedup: `6.899x`
- M116 resident overhead gate:
  - artifact:
    `artifacts/m116-fast-path-overhead/fast-path-overhead-gate-m116-qwen-a3b.json`
  - verdict: `PASS`
  - mean overhead: `4.598 ms`
  - max overhead: `4.980 ms`
- M117 live prompt transport sweep:
  - artifact:
    `artifacts/m117-live-extended-prompt-sweep/live-prompt-transport-sweep-m117-qwen-a3b.json`
  - verdict: `PASS`
  - rows: `8`
  - prompt targets: `512`, `1024`, `2048`, `4096`
  - transports: `resident`, `cli`
- M118 live lower-memory gate:
  - artifact:
    `artifacts/m118-live-lower-memory/lower-memory-live-gate-m118-qwen-a3b.json`
  - verdict: `PASS`
  - max peak memory: `24.054 GB`
  - cache memory limit: `64 MB`
  - conversion prefill: `11` tokens
- M119 runtime auto-selection:
  - artifact:
    `artifacts/m119-auto-selection-runtime/dax-auto-selected-m119-qwen-a3b.json`
  - verdict: `PASS`
  - auto-selected profile: `agent-workspace-first-hit`
  - best hit speedup: `7.336x`
- M120 live product readiness bundle:
  - artifact:
    `artifacts/m120-live-product-readiness/live-product-readiness-bundle-m120-qwen-a3b.json`
  - verdict: `PASS`
  - readiness: `live-validated`
  - evidence artifacts: `7`

Decision:

- The immediate product target is no longer proving whether the resident path
  works; it does.
- Next performance target should move to server-side automation and profiling:
  one-command live regression, request-derived profile selection, and
  Instruments-backed prompt-processing/JIT breakdowns.

## M121 Result

M121 adds the one-command live product regression suite:

- script: `benchmarks/python/run_live_product_regression_suite.py`
- artifact:
  `artifacts/m121-live-product-regression-suite/live-product-regression-suite-m121-qwen-a3b.json`

Result:

- suite verdict: `PASS`
- readiness: `live-regression-passing`
- evidence artifacts: `7`
- failures: `0`
- resident repeated-context speedup: `7.166x`
- fast-path overhead mean: `4.234 ms`
- prompt transport sweep rows: `8`
- lower-memory max peak memory: `24.056 GB`
- auto-selected first-hit speedup: `5.265x`

Decision:

- M115-M119 can now be rerun as a focused live regression command.
- The next target is M122: move profile selection into server-side request
  metadata handling so product clients do not need to choose benchmark flags.

## M122 Result

M122 adds server-side request profile metadata handling:

- selector module: `mlx_engine/request_profiles.py`
- service integration: `mlx_engine/resident_service.py`
- UI intent map update: `mlx_engine/ui_client.py`
- gate: `benchmarks/python/request_profile_metadata_gate.py`
- artifact:
  `artifacts/m122-request-profile-metadata/request-profile-metadata-gate-m122-qwen-a3b.json`

Result:

- gate verdict: `PASS`
- scenarios: `6`
- schema checks: `4`
- failures: `0`

Accepted request metadata:

- `workload_intent`
- `runtime_profile`
- `memory_class_gb`
- `immediate_second_turn`
- `low_memory`
- `diagnostics_workload`
- `interactive_workload`
- `agentic_workload`
- `repeated_workspace`

Decision:

- Product clients should send workload metadata directly on completion/chat
  requests.
- Manual `runtime_profile` remains the highest-priority override.
- The next target is M123: restart the live server on the updated code and run
  a live request-metadata regression to verify the decision appears in
  `engine_metrics`.

## M123 Result

M123 live-validates request metadata profile selection:

- script: `benchmarks/python/live_request_profile_metadata_probe.py`
- artifact:
  `artifacts/m123-live-request-profile-metadata/live-request-profile-metadata-m123-qwen-a3b.json`
- service: restarted on `127.0.0.1:8773` from the updated worktree

Result:

- verdict: `PASS`
- rows: `3`
- failures: `0`
- `/v1/completions` with first-hit intent:
  `agent-workspace-first-hit`
- `/v1/chat/completions` with coding-agent plus `memory_class_gb=32`:
  `agent-workspace-low-memory`
- `/v1/completions` with manual `runtime_profile=interactive`:
  `interactive`
- all rows reported `request_runtime_profile_source=request_metadata`
- all rows reported `request_runtime_profile_applied=true`

Decision:

- Server-side request metadata routing is live-validated.
- The next target is M124: add request-metadata coverage to the one-command
  live product regression suite so M121-style regression catches profile
  routing regressions automatically.

## M124 Result

M124 integrates live request-metadata routing into the one-command product
regression suite:

- script: `benchmarks/python/run_live_product_regression_suite.py`
- artifact:
  `artifacts/m124-live-product-regression-suite/live-product-regression-suite-m124-qwen-a3b.json`

Result:

- suite verdict: `PASS`
- readiness: `live-regression-passing`
- evidence artifacts: `8`
- failures: `0`
- resident repeated-context speedup: `7.251x`
- fast-path overhead mean: `4.691 ms`
- lower-memory speedup: `9.685x`
- lower-memory max peak memory: `24.054 GB`
- auto-selected first-hit speedup: `5.191x`
- request metadata probe rows: `3`

Decision:

- The live product regression suite now covers request profile metadata.
- The next target is M125: add a concise product/client contract document for
  request metadata fields and expected profile routing so Dax, Prowl, or a UI
  can integrate without reading benchmark code.

## M125 Result

M125 adds the product/client request metadata contract:

- document:
  `docs/mac-local-inference-platform/request-metadata-client-contract.md`
- linked from:
  - `docs/mac-local-inference-platform/engine-readiness.md`
  - `docs/mac-local-inference-platform/resident-operator-runbook.md`

Contract coverage:

- accepted request metadata fields
- selection precedence
- workload-intent routing table
- completion, chat, and manual override examples
- validation commands for M122, M123, and M124
- current limitation for future true concurrent generation

Decision:

- Dax, Prowl, and UI clients can integrate request metadata without reading
  benchmark code.
- The next target is M126: add a small client-side helper or sample that emits
  this metadata from a product mode enum.

## M126 Result

M126 adds product-mode request metadata helpers:

- helper: `mlx_engine/ui_client.py`
- probe: `benchmarks/python/product_mode_metadata_probe.py`
- artifact:
  `artifacts/m126-product-mode-metadata/product-mode-metadata-m126-qwen-a3b.json`
- contract update:
  `docs/mac-local-inference-platform/request-metadata-client-contract.md`

Result:

- verdict: `PASS`
- cases: `7`
- failures: `0`

Product modes:

- `chat`
- `coding-agent`
- `coding-agent-first-hit`
- `coding-agent-low-memory`
- `diagnostics`

Decision:

- Product clients can call `apply_product_mode(...)` instead of hardcoding
  request metadata.
- The next target is M127: wire the helper into a concrete client path, likely
  Dax first, so operator commands can emit request metadata instead of changing
  server profile state.

## M127 Result

M127 wires request metadata into the Dax MLX command path.

Dax commit:

- `28b5493f Add MLX request metadata to Dax prompts`

Implemented behavior:

- prompt and interactive generation send request metadata in the completion
  payload
- default prompt and interactive sessions map to `workload_intent=coding-agent`
- `--intent first-hit`, `--intent low-memory`, `--intent interactive`, and
  `--intent diagnostics` map to explicit request metadata fields
- `--profile` becomes a per-request `runtime_profile` override for generation
- status-only profile/intent operations and interactive `/profile` remain
  global operator controls

Validation:

- Dax focused MLX test: `32` passed
- Dax coding-agent build: passed
- Dax pre-commit checks: passed

Decision:

- Product generation should prefer request metadata over global profile
  mutation.
- The next target is M128: live-smoke the Dax request metadata path against the
  running resident server.

## M128 Result

M128 live-validates Dax request metadata against the Qwen A3B resident server.

Artifact:

- `artifacts/m128-dax-request-metadata-smoke/dax-request-metadata-smoke-m128-qwen-a3b.json`

Verified response metrics:

- `request_runtime_profile=agent-workspace-async`
- `request_runtime_profile_source=request_metadata`
- `request_runtime_profile_applied=true`
- `workload_intent=coding-agent`
- `agentic_workload=true`
- `repeated_workspace=true`

Decision:

- The operator-facing Dax command path reaches the same server-side request
  metadata router validated by M123-M126.
- The next target is M129: make the Dax operator contract explicit in docs so
  future UI/Prowl clients do not confuse request metadata with global engine
  configuration.

## M129 Result

M129 documents the Dax/operator contract for request metadata.

Updated docs:

- `docs/mac-local-inference-platform/request-metadata-client-contract.md`
- `docs/mac-local-inference-platform/resident-operator-runbook.md`
- `docs/mac-local-inference-platform/engine-readiness.md`

Contract:

- prompt and interactive product generation send per-request metadata
- status-only profile/intent commands can still mutate `/engine/config`
- interactive `/profile` remains a deliberate global override

Decision:

- Dax, Prowl, and future UI work should expose product modes while keeping raw
  runtime profile mutation as an operator-only control.
- The next target is M130: improve Dax operator UX so the active product mode
  and metadata path are visible instead of implicit.

## M130 Result

M130 makes Dax request routing visible in the interactive operator panel.

Dax commit:

- `3afb64d1 Show MLX request route in Dax prompt panel`

Displayed route examples:

- `request route: engine default`
- `request route: workload_intent=coding-agent flags=agentic,repeated`
- `request route: workload_intent=first-hit flags=agentic,repeated,first-hit`
- `request route: runtime_profile=interactive`

Validation:

- Dax focused MLX test: `34` passed
- Dax coding-agent build: passed
- Dax pre-commit checks: passed

Decision:

- Operators should be able to distinguish request metadata routing from global
  engine profile state at a glance.
- The next target is M131: put the real Dax request-metadata path into the
  one-command live regression suite.

## M131 Result

M131 adds Dax request-metadata smoke coverage to the live product regression
suite.

Added:

- `benchmarks/python/dax_request_metadata_smoke.py`
- `run_live_product_regression_suite.py` artifact key:
  `dax_request_metadata_smoke`
- `covered_milestones` now includes `M131`

Live artifact:

- `artifacts/m131-dax-request-metadata-suite/dax-request-metadata-smoke-m131-qwen-a3b.json`

Result:

- verdict: `PASS`
- checks: `5`
- failures: `0`
- profile source: `request_metadata`

Decision:

- The live product regression suite now covers the actual Dax CLI request path,
  not only direct HTTP probes.
- The next target is M132: refresh the initial-to-current performance
  comparison with the latest request-metadata and Dax evidence.

## M132 Result

M132 refreshes the performance comparison artifact.

Added:

- `benchmarks/python/milestone_performance_comparison_report.py`

Artifacts:

- `artifacts/m132-performance-comparison/performance-comparison-m132-qwen-a3b.json`
- `artifacts/m132-performance-comparison/performance-comparison-m132-qwen-a3b.md`

Result:

- verdict: `PASS`
- current prompt transport rows: `4`
- M121 repeated-context speedup: `7.17x`
- M124 repeated-context speedup: `7.25x`
- Dax request metadata smoke: `PASS`

Decision:

- The large change from the initial bench remains resident warmup and avoiding
  repeated prefill.
- The next target is M133: turn the current evidence chain into an operator
  readiness checkpoint.

## M133 Result

M133 defines the current operator readiness checkpoint.

Evidence chain:

- Dax integration commit: `28b5493f`
- Dax route-visibility commit: `3afb64d1`
- live Dax request metadata artifact:
  `artifacts/m131-dax-request-metadata-suite/dax-request-metadata-smoke-m131-qwen-a3b.json`
- performance comparison:
  `artifacts/m132-performance-comparison/performance-comparison-m132-qwen-a3b.md`
- runbook:
  `docs/mac-local-inference-platform/resident-operator-runbook.md`
- client contract:
  `docs/mac-local-inference-platform/request-metadata-client-contract.md`

Decision:

- The Dax operator path is ready for continued performance work.
- The next target is M134: select the next performance slice based on the
  refreshed comparison.

## M134 Result

M134 selects the next performance target: request-scoped prompt-processing
automation for repeated workspace turns.

Target:

- keep request metadata as the product control plane
- profile cache admission and async prefix-build scheduling under Dax/product
  workloads
- reduce first reusable-turn latency while preserving memory bounds

Why this target:

- warmed resident prefill already removes most initial short-prompt noise
- current Qwen A3B prompt transport is not the product bottleneck by itself
- M121/M124 repeated-context evidence shows the product path benefits most when
  repeated prefill is avoided
- Dax now sends and displays request metadata, so product routing decisions can
  drive the next optimization safely

Deferred:

- speculative decoding
- tensor parallelism
- image/VLM expansion
- broad UI work

## M135-M142 Result

The next performance lane moved from planning to measured request-scoped
product-routing gates.

Completed:

- M135 request-scoped cache admission probe
- M136 async prefix-build scheduling profile
- M137 first reusable-turn latency gate
- M138 memory-pressure bounded cache policy gate
- M139 request-scoped routing isolation start
- M140 expanded live product regression suite
- M141 Dax product mode shortcuts
- M142 performance checkpoint

Key artifacts:

- `artifacts/m135-request-scoped-cache-admission/request-scoped-cache-admission-m135-qwen-a3b.json`
- `artifacts/m136-m139-request-scoped-gates/request-scoped-performance-gates-m136-m139-qwen-a3b.json`
- `artifacts/m140-live-product-regression-suite/live-product-regression-suite-m140-qwen-a3b.json`
- `artifacts/m142-performance-checkpoint/performance-checkpoint-m142-qwen-a3b.md`

Key commits:

- MLX: request-scoped service/gates/docs in the M135-M142 batch
- Dax: `efb3cc78 Add MLX product mode shortcuts to Dax`

M140 live suite:

- verdict: `PASS`
- artifacts: `11`
- failures: `0`
- covered milestones: `M115`, `M116`, `M117`, `M118`, `M119`, `M121`,
  `M123`, `M124`, `M131`, `M135`, `M136`, `M137`, `M138`, `M139`, `M140`

Decision:

- Continue the request-scoped prompt-processing lane.
- The next target should be streaming request-profile scope parity, then first
  reusable-turn latency reduction and cache-admission threshold tuning.

Important limitation:

- Non-stream generation now uses `request_runtime_profile_scope(...)`.
- Streaming routes still use the compatibility path and should be converted in
  the next milestone batch before claiming complete concurrency-safe request
  profile isolation.

## M143-M150 Result

The request-scoped prompt-processing lane now has streaming parity, cache-turn
gates, product-mode smoke coverage, and an expanded live suite checkpoint.

Completed:

- M143 streaming request-profile scope parity
- M144 streaming metadata regression gate
- M145 first reusable-turn latency reduction probe
- M146 cache-admission threshold tuning
- M147 Dax product-mode smoke commands
- M148 live suite product-mode coverage
- M149 request-scoped concurrency safety probe
- M150 performance checkpoint

Key artifacts:

- `artifacts/m144-streaming-metadata-scope/streaming-request-metadata-scope-m144-qwen-a3b.json`
- `artifacts/m145-m146-cache-turn-gates/cache-threshold-and-turn-gates-m145-m146-qwen-a3b.json`
- `artifacts/m146-cache-threshold-tuning/request-scoped-cache-admission-m146-qwen-a3b.json`
- `artifacts/m148-live-product-mode-suite/live-product-regression-suite-m148-qwen-a3b.json`
- `artifacts/m149-request-scoped-concurrency/request-scoped-concurrency-m149-qwen-a3b.json`
- `artifacts/m150-performance-checkpoint/performance-checkpoint-m150-qwen-a3b.md`

M148 live suite:

- verdict: `PASS`
- readiness: `live-regression-passing`
- artifacts: `15`
- failures: `0`
- covered milestones include `M143`, `M144`, `M145`, `M146`, `M148`, and
  `M149`

Decision:

- Continue into concurrency hardening and first reusable-turn latency
  reduction.
- Treat request-scoped routing as improved but not finished. A first M149 run
  observed profile bleed before the passing rerun, so the next milestone should
  strengthen the lock/scope discipline and run repeated stress coverage before
  claiming complete request-profile isolation.

## M151-M158 Result

The next lane converted the M149 profile-bleed concern into lock hardening,
stress coverage, parity checks, and a current performance report.

Completed:

- M151 concurrency stress hardening
- M152 request-profile scope lock audit
- M153 streaming and non-stream route parity
- M154 product-profile policy stabilization
- M155 live suite lock regression
- M156 performance report
- M157 operator visibility contract
- M158 checkpoint and next milestone list

Performance report:

- `artifacts/m156-performance-report/performance-report-m156-qwen-a3b.md`

Checkpoint:

- `artifacts/m158-performance-checkpoint/performance-checkpoint-m158-qwen-a3b.md`

Current performance:

- M155 live suite: `PASS`, 15 artifacts, 0 failures
- M151 stress: 12 iterations, 36 rows, 0 failures
- repeated best-hit speedup: `6.949899063306281`
- repeated best-hit service ms: `214.1152499243617`
- repeated best-hit prefill tokens: `11`
- resident prompt transport wall ms: `474.661166081205`
- CLI prompt transport wall ms: `6038.545124931261`

Next target:

- Pause performance-only work and add quality gates first. Speed improvements
  are not release-ready unless response quality is preserved.
- The next milestone lane is M159-M166 quality-gated performance:
  `M159` quality golden-set harness, `M160` deterministic quality regression
  runner, `M161` cache-enabled vs cache-disabled quality comparison, `M162`
  streaming vs non-stream quality parity, `M163` loop/repetition detector,
  `M164` long-context RoPE/IMRoPE quality probe, `M165` cross-engine Qwen3.6
  quality comparison, and `M166` quality-gated performance checkpoint.

Quality plan:

- `docs/mac-local-inference-platform/inference-quality-gates.md`
- `artifacts/m159-quality-gate-plan/quality-gate-plan-m159-qwen-a3b.md`

## M159-M166 Quality Gate Execution

The quality gate harness is now implemented and has live evidence.

Result:

- `M159` golden prompt set: `PASS`
- `M160` deterministic quality regression: `PASS`
- `M161` cache-enabled vs cache-disabled quality comparison: `PASS`
- `M162` streaming vs non-stream quality parity: `PASS`
- `M163` loop/repetition detector: `PASS`
- `M164` long-context RoPE/IMRoPE quality probe: `PASS`
- `M165` cross-engine Qwen3.6 rubric comparison: `PASS`
- `M166` quality-gated performance checkpoint: `PASS`

Resolved quality finding:

- The original Qwen3.6 MLX path retrieved long-context sentinel facts inside
  visible reasoning but did not produce a clean final answer. Explicit
  `/no_think` prompts now receive a Qwen assistant prefill
  `<think>\n\n</think>\n\n`, which suppresses visible reasoning and lets the
  long-context quality gate return a clean final answer:
  `ORCHID-17, LANTERN-42, HARBOR-93`.

Artifacts:

- `artifacts/m159-quality-golden-set/quality-golden-set-m159-qwen-a3b.json`
- `artifacts/m160-deterministic-quality/deterministic-quality-m160-qwen-a3b.json`
- `artifacts/m161-cache-quality/cache-quality-m161-qwen-a3b.json`
- `artifacts/m162-streaming-quality/streaming-quality-m162-qwen-a3b.json`
- `artifacts/m163-loop-quality/loop-quality-m163-qwen-a3b.json`
- `artifacts/m164-long-context-quality/long-context-quality-m164-qwen-a3b.json`
- `artifacts/m165-cross-engine-quality/cross-engine-quality-m165-qwen-a3b.json`
- `artifacts/m166-quality-checkpoint/quality-checkpoint-m166-qwen-a3b.md`

Decision:

- Quality gates are now blocking criteria for future speed work.
- Continue performance optimization only while keeping M159-M166 in the
  regression suite.

## M167 Result

M167 integrates the quality gates into the live product regression suite.

Artifact:

- `artifacts/m167-live-quality-regression-suite/live-product-regression-suite-m167-qwen-a3b.json`

Result:

- verdict: `PASS`
- readiness: `live-regression-passing`
- artifacts: `23`
- failures: `0`
- covered milestones include `M159` through `M167`

Decision:

- The default acceptance bar is now quality-gated performance.
- Continue with Dax/TUI quality status visibility, broader coding-agent golden
  prompts, and model-to-model quality comparison.

## M168 Result

M168 packages suite quality health for operator surfaces.

Artifact:

- `artifacts/m168-quality-status/quality-status-m168-qwen-a3b.json`

Result:

- verdict: `PASS`
- quality gates: `8`
- failures: `0`
- operator summary reports quality `PASS` and performance `PASS`

## M169 Result

M169 expands the deterministic golden set with coding-agent-shaped quality
checks.

Artifacts:

- `artifacts/m169-expanded-golden-set/quality-golden-set-m169-qwen-a3b.json`
- `artifacts/m169-expanded-golden-set/deterministic-quality-m169-qwen-a3b.json`

Result:

- verdict: `PASS`
- deterministic rows: `8`
- failures: `0`
- added coverage: code review, edit-plan, and summary prompts

## M170 Result

M170 adds model-to-model quality comparison before using smaller models as a
performance shortcut.

Compared models:

- `/Volumes/StudioStackSSD4TB/Development/LLM/lmstudio/models/unsloth/Qwen3.6-35B-A3B-UD-MLX-4bit`
- `/Volumes/StudioStackSSD4TB/Development/LLM/lmstudio/models/unsloth/Qwen3.6-27B-UD-MLX-4bit`

Artifacts:

- `artifacts/m170-model-quality-comparison/model-quality-comparison-m170-qwen.json`
- `artifacts/m170-model-quality-comparison/model-quality-comparison-m170-qwen.md`

Result:

- verdict: `PASS`
- candidate reload: `PASS`
- candidate GPU health: `Device(gpu, 0)`
- quality gates compared: deterministic, cache, loop, long-context
- failures: `0`
- observed latency: the 27B dense candidate was slower than the current A3B
  model in these probes

Decision:

- The 27B UD MLX 4-bit model is quality-compatible enough for follow-up testing,
  but this evidence does not support using it as the speed replacement.
- Keep the comparison gate as the acceptance bar for any model swap.

## M171 Result

M171 creates the operator/TUI bundle that combines live runtime status, quality
gate status, and model-comparison status.

Artifacts:

- `artifacts/m171-operator-quality-bundle/operator-quality-bundle-m171-qwen-a3b.json`
- `artifacts/m171-operator-quality-bundle/operator-quality-bundle-m171-qwen-a3b.md`

Result:

- verdict: `PASS`
- readiness: `operator-quality-ready`
- status card: engine `PASS`, gpu `PASS`, warmup `PASS`, quality `PASS`,
  model comparison `PASS`
- warning: the 27B quality-compatible candidate is slower than the active A3B
  model

Decision:

- Dax/TUI should read this bundle shape for quality status before exposing model
  swap or speed-claim surfaces.

## M172 Result

M172 broadens the deterministic quality gate into coding-agent workflow coverage.

Added cases:

- workspace symbol lookup
- patch planning
- focused test selection
- failure triage

Artifacts:

- `artifacts/m172-coding-agent-golden-set/quality-golden-set-m172-qwen-a3b.json`
- `artifacts/m172-coding-agent-golden-set/deterministic-quality-m172-qwen-a3b.json`
- `artifacts/m172-coding-agent-golden-set/loop-quality-m172-qwen-a3b.json`
- `artifacts/m172-coding-agent-golden-set/quality-checkpoint-m172-qwen-a3b.json`
- `artifacts/m172-coding-agent-golden-set/quality-checkpoint-m172-qwen-a3b.md`

Result:

- verdict: `PASS`
- deterministic rows: `12`
- loop rows: `13`
- failures: `0`

Decision:

- Continue prompt-processing and generation speed work only while preserving
  coding-agent task correctness, not just generic answer quality.

## M173 Result

M173 adds a CI-style threshold report for quality and operator readiness.

Artifact:

- `artifacts/m173-quality-threshold-gate/quality-threshold-gate-m173-qwen-a3b.json`

Result:

- verdict: `PASS`
- readiness: `ci-quality-ready`
- checks: `18`
- failures: `0`
- deterministic quality verdict: `PASS`
- loop quality verdict: `PASS`
- operator bundle verdict: `PASS`

Decision:

- Any future model swap, profile change, cache change, or speed claim should
  include this threshold gate or an equivalent stricter gate.

## M175 Result

M175 reruns the full live product regression suite after integrating expanded
coding-agent quality and CI threshold output.

Artifact:

- `artifacts/m175-live-expanded-quality-suite/live-product-regression-suite-m175-qwen-a3b.json`

Result:

- verdict: `PASS`
- readiness: `live-regression-passing`
- artifacts: `24`
- failures: `0`
- lower-memory gate: `PASS`
- quality checkpoint: `PASS`
- quality threshold gate: `PASS`

Implementation note:

- The lower-memory runtime gate now checks current active memory through live
  `/health` when available. This avoids false failures from historical MLX peak
  memory after model reload experiments.

## M176 Result

M176 adds model/profile swap acceptance automation.

Artifact:

- `artifacts/m176-model-swap-acceptance/model-swap-acceptance-m176-qwen27b.json`

Result:

- gate verdict: `PASS`
- swap decision: `REJECT`
- blocker: candidate speed
- candidate slowdown ratio: `9.968977`
- quality gates: `PASS`
- CI threshold gate: `PASS`

Decision:

- Do not replace the active A3B model with the tested 27B dense model. The swap
  gate correctly blocks it even though quality checks pass.

## M177 Result

M177 adds per-request active memory fields to engine metrics.

Artifact:

- `artifacts/m177-request-memory-metrics/request-memory-metrics-static-probe-m177-qwen-a3b.json`

Result:

- static contract: `PASS`
- request metric injection points: `3`
- failures: `0`

Fields:

- `active_memory_gb`
- `cache_memory_gb`
- `mlx_peak_memory_gb`

Decision:

- Once the live resident server is restarted onto this commit, lower-memory
  checks should prefer per-request `active_memory_gb` and only use `/health` as
  compatibility fallback.

## M178 Result

M178 restarts the live resident server onto M177 and validates memory metrics at
runtime.

Artifact:

- `artifacts/m178-request-memory-live/request-memory-metrics-live-probe-m178-qwen-a3b.json`

Result:

- verdict: `PASS`
- non-stream response includes all required memory fields
- stream final metrics include all required memory fields
- active memory: `20.78077057 GB`
- MLX peak memory: `21.419940142 GB`

Decision:

- M177 is now runtime-proven. Future lower-memory suite runs should no longer
  need `/health` fallback when they are run against a server started from this
  commit or later.

## M179 Result

M179 creates a one-command model swap artifact workflow.

Artifact:

- `artifacts/m179-model-swap-workflow/model-swap-workflow-m179-qwen27b.json`

Result:

- workflow verdict: `PASS`
- swap decision: `REJECT`
- model comparison: `PASS`
- quality threshold: `PASS`
- blocker: candidate speed
- candidate slowdown ratio: `9.968977`

Decision:

- Keep the active A3B model. The 27B dense model is quality-compatible but not a
  performance upgrade.

## M180 Result

M180 reruns the full live product regression suite after request-local memory
metrics were added and proven live.

Artifacts:

- `artifacts/m180-live-request-memory-suite/live-product-regression-suite-m180-qwen-a3b.json`
- `artifacts/m180-live-request-memory-suite/lower-memory-live-gate-m180-qwen-a3b.json`
- `artifacts/m180-live-request-memory-suite/quality-threshold-gate-m180-qwen-a3b.json`

Result:

- suite verdict: `PASS`
- artifacts: `24`
- failures: `0`
- lower-memory gate: `PASS`
- quality checkpoint: `PASS`
- quality threshold gate: `PASS`
- lower-memory memory source: `request_metrics`
- health fallback active memory: unused
- max active memory: `21.02259841 GB`
- max peak memory: `22.31961337 GB`

Decision:

- Continue using the active A3B model and request-scoped runtime profiles. The
  lower-memory gate is now driven by request-local active memory instead of stale
  process peak memory or process-level `/health` when request metrics are
  available.

## M181 Result

M181 adds and runs a live resident model swap lifecycle probe.

Artifact:

- `artifacts/m181-live-model-swap/live-model-swap-m181-qwen-a3b.json`

Result:

- verdict: `PASS`
- readiness: `live-model-swap-safe`
- failures: `0`
- candidate reload: `12524.02 ms`
- restore reload: `8440.3 ms`
- candidate post-reload completion: `PASS`
- restore post-reload completion: `PASS`
- device stayed on `Device(gpu, 0)`
- request-local memory metrics were present after both reloads

Decision:

- Same-model reload/restore is live-safe enough to use as the baseline lifecycle
  gate. Candidate model swaps still need the M176/M179 acceptance decision before
  promotion.
