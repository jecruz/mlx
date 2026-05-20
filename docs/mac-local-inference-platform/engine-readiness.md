# MLX Engine Readiness

This checklist captures the current operator-facing readiness surface for the
resident MLX engine work through M80.

## Runtime Target

- Model:
  `/Volumes/StudioStackSSD4TB/Development/LLM/lmstudio/models/unsloth/Qwen3.6-35B-A3B-UD-MLX-4bit`
- Server:
  `bin/mlx-engine serve --model <model> --port 8773 --warmup-mode async --require-gpu`
- Expected device:
  `Device(gpu, 0)` with Metal available
- Tested `mlx-lm`:
  `0.30.7`

## Controls

Use `/engine/profiles` to discover product-facing runtime profiles:

- `interactive`
- `agent-workspace`
- `agent-workspace-async`
- `agent-workspace-request`
- `memory-saver`
- `diagnostics`

Use `/engine/config` to apply a named profile or tune lower-level behavior
without reloading the model:

- `runtime_profile`
- `engine_preset`
- `prefix_cache_population_mode`
- `prefix_cache_async_idle_timeout_ms`
- `prefix_cache_async_idle_grace_ms`
- `prefix_cache_pending_wait_ms`
- `prefix_cache_memory_limit_mb`
- `prefix_cache_min_entries`
- `max_concurrent_requests`
- `max_queued_requests`
- `queue_timeout_ms`

Use `/engine/ui` for UI and product integrations. It returns a single snapshot
with:

- model/load state
- current `runtime_profile`
- profile catalog
- readiness flags
- generation controls
- cache strategy and counters
- scheduler state
- memory summary
- request metrics

Python integrations can use `mlx_engine.ui_client.EngineUiClient` to consume the
same contract and normalize it into `EngineUiSummary`.

Python integrations can select workload intent instead of raw profile names:

- `EngineUiClient.apply_workload_intent("coding-agent")`
- `runtime_profile_for_intent("coding-agent") == "agent-workspace-async"`

Dax integrations can use:

- `dax mlx-engine --intent coding-agent`
- `dax mlx-engine --prompt ...` and `dax mlx-engine --interactive` apply the
  `coding-agent` intent automatically unless `--profile` or `--intent` is
  supplied.

Recommended product profiles:

- Low-latency interactive:
  `runtime_profile=interactive`
- Repeated-agent-context with pending-wait experiments:
  `runtime_profile=agent-workspace`
- Repeated-agent-context with M79-proven mature async reuse:
  `runtime_profile=agent-workspace-async`
- Request-derived cache experiments:
  `runtime_profile=agent-workspace-request`
- Memory constrained:
  `runtime_profile=memory-saver`
- Operational diagnostics:
  `runtime_profile=diagnostics`

## Readiness Probes

Run these against a live server:

```bash
python3 benchmarks/python/async_prefix_build_amortization_probe.py \
  --base-url http://127.0.0.1:8773

python3 benchmarks/python/async_prefix_pending_wait_probe.py \
  --base-url http://127.0.0.1:8773

python3 benchmarks/python/cache_continuation_capabilities_probe.py \
  --base-url http://127.0.0.1:8773

python3 benchmarks/python/engine_readiness_probe.py \
  --base-url http://127.0.0.1:8773

python3 benchmarks/python/runtime_profile_probe.py \
  --base-url http://127.0.0.1:8773

python3 benchmarks/python/ui_status_contract_probe.py \
  --base-url http://127.0.0.1:8773

python3 benchmarks/python/ui_client_adapter_probe.py \
  --base-url http://127.0.0.1:8773

cd /Users/jeffreycruz/Development/AI_AGENTS/dax-stereo/packages/coding-agent
npx tsx src/cli.ts mlx-engine --base-url http://127.0.0.1:8773 --once
npx tsx src/cli.ts mlx-engine --base-url http://127.0.0.1:8773 \
  --prompt "Reply with exactly three words about MLX speed." \
  --max-tokens 8
npx tsx src/cli.ts mlx-engine --base-url http://127.0.0.1:8773 \
  --prompt "Stream exactly four words about MLX." \
  --max-tokens 8 \
  --stream
npx tsx src/cli.ts mlx-engine --base-url http://127.0.0.1:8773 \
  --interactive \
  --max-tokens 128
```

## Go Criteria

- `/health.ok` is `true`
- `/health.device.metal_available` is `true`
- `/health.device.default_device` contains `gpu`
- `prefix_cache_policy` includes:
  - `existing_build_reuses`
  - `pending_build_deduplications`
  - `pending_wait_ms`
  - `pending_wait_hits`
- `prompt_cache_continuation` includes:
  - `native_replay_free_prefix_store_supported`
  - `safe_request_prefix_store_strategy`
  - `required_lower_level_work`
- `/engine/config` dry-run returns planned state for pending-wait controls
- `/engine/profiles` returns all named runtime profiles
- `/engine/config` can apply `runtime_profile=agent-workspace`
- `/engine/ui` returns the stable UI integration contract
- `EngineUiClient.summary()` returns a normalized UI summary
- `dax mlx-engine --once` displays live model, GPU, generation, cache, scheduler,
  metrics, and runtime-profile state from the resident engine
- `dax mlx-engine --prompt ...` returns a non-streaming generation response and
  usage counters through the resident engine HTTP API
- `dax mlx-engine --prompt ... --stream` prints streamed chunks from the
  OpenAI-compatible SSE API and reports usage counters when the final event
  arrives
- `dax mlx-engine --interactive` opens a focused Dax TUI prompt panel that
  streams responses into a short terminal transcript
- completed interactive generations append elapsed timing and completion
  tokens-per-second feedback when completion-token usage is available
- `/export` and `/snapshot` include structured `generation_metrics` records for
  elapsed milliseconds, completion throughput, and returned usage counters
- `/export` and `/snapshot` include `generation_metrics_summary` aggregates for
  count, elapsed milliseconds, and completion throughput
- inside the interactive panel, `/metrics`, `/metrics all`, `/metrics clear`,
  and `/metrics export [path]` review, reset, or export generation timing
  evidence without prompt text
- inside the interactive panel, `/profiles`, `/profile <name>`, and `/profile
  next` list and apply runtime profiles without leaving the TUI
- inside the interactive panel, the configured stop key aborts in-flight
  generation without exiting the TUI
- inside the interactive panel, live engine status refresh shows active/queued
  requests, cache mode, failed requests, and total request count
- inside the interactive panel, `/export [path]` writes an evidence JSON file
  with the latest engine snapshot, profile catalog, mode, max token cap, and
  plain-text transcript
- inside the interactive panel, `/reload [model-path]` and `/unload` control
  resident model lifecycle through the MLX engine HTTP API and refresh the
  panel from `/engine/ui`
- inside the interactive panel, `/cache prune [target_entries]` performs manual
  prefix-cache recovery through `/engine/cache/prune` and refreshes the panel
  from `/engine/ui`
- inside the interactive panel, `/config [--dry-run] key=value ...` applies
  guarded runtime config through `/engine/config` and refreshes the panel from
  `/engine/ui`
- inside the interactive panel, `/help` shows available controls and `/status`
  appends a compact engine summary to the transcript
- inside the interactive panel, `/find <text>` searches prior transcript lines
  and appends compact recent matches or a no-match result
- inside the interactive panel, `/view recent`, `/view all`, and `/clear`
  control long transcript rendering and cleanup without deleting prompt history
- inside the interactive panel, `/history` lists recent natural-language
  prompts and `/again [n]` reruns the latest or numbered prompt
- inside the interactive panel, `/snapshot [path]` writes a diagnostic JSON
  bundle with compact status, raw engine snapshot, profiles, prompt history,
  and transcript
- snapshot export also writes an attach-ready Markdown sidecar with compact
  status, recent prompts, and recent transcript excerpt
- `/snapshot --redact [path]` replaces prompt history and transcript content
  with redaction markers while preserving engine status and configuration
  context
- `/snapshot --safe [path]` implies prompt/transcript redaction and also scrubs
  local filesystem-style model paths from status, raw snapshot payloads,
  profiles, and Markdown sidecars
- `/snapshot --no-raw [path]` omits the raw engine snapshot payload while
  preserving compact status, profiles, metadata, and prompt/transcript fields;
  combine with `--safe` for compact external handoff artifacts
- `/snapshot ticket|internal|full [path]` provides named privacy presets:
  `ticket` maps to `--safe --no-raw`, `internal` maps to `--redact`, and
  `full` preserves the complete raw snapshot behavior

## Latest Resident Benchmark Evidence

M54 captured a live resident benchmark against
`Qwen3.6-35B-A3B-UD-MLX-4bit` on `Device(gpu, 0)`.

Key result:

- Full prefill path: 247 actual prefill tokens, 87728.97 ms service time.
- Prefix cache create path: 7.5 mean actual prefill tokens, 434.44 ms mean
  service time.
- Prefix cache hit path: 8 actual prefill tokens, 219.72 ms service time.

Readiness interpretation:

- The current resident engine can turn repeated long-context prompt processing
  from tens of seconds into hundreds of milliseconds when prefix reuse hits.
- Cache creation remains a visible cost and should be treated as the next
  prompt-processing optimization target.
- Dax operator metrics now have a concrete resident benchmark baseline to
  compare against future engine-profile and cache-policy changes.
- `benchmarks/python/compare_resident_benchmarks.py` now reports derived
  per-artifact service speedup, prefill-token reduction, and cache-prepare
  share versus full prefill, so later runs can be compared without manual JSONL
  parsing.
- `benchmarks/python/resident_regression_gate.py` now gates cache-hit service
  speedup and actual-prefill-token reduction versus full prefill, and
  `benchmarks/python/run_resident_regression_suite.py` exposes both thresholds
  as suite flags.
- The same gate now separately checks cache-create mean service time and
  cache-prepare share, so first-reuse overhead can regress independently of
  cache-hit behavior.
- `benchmarks/python/resident_regression_gate.py --output-json` emits a compact
  machine-readable report, and `benchmarks/python/run_resident_regression_suite.py`
  writes `resident-regression-gate-<tag>.json` next to the benchmark artifacts.
- `benchmarks/python/run_resident_regression_suite.py` also writes
  `resident-regression-suite-<tag>.json`, a suite manifest that records
  artifact paths, executed steps, and the embedded gate report when available.
- Failed suite subprocesses now write a `verdict=FAIL` suite manifest before
  exiting, preserving the failing command, return code, artifact existence
  state, and embedded gate report when available.
- `benchmarks/python/summarize_resident_suite_manifest.py` prints a stable
  line-based summary for `resident-regression-suite-<tag>.json` manifests,
  including suite verdict, artifact existence, gate failures, and failing
  subprocess details.
- `benchmarks/python/summarize_resident_suite_manifest.py --fail-on-fail` exits
  non-zero when the suite manifest verdict is not `PASS`, making the summary
  tool usable as a CI assertion step.
- `benchmarks/python/run_resident_regression_suite.py --print-manifest-summary`
  prints the same suite manifest summary inline on success and after child
  subprocess failure, while preserving existing output unless the flag is set.
- M64 real suite evidence passed against the live Qwen3.6-35B-A3B resident
  engine on `Device(gpu, 0)`: suite verdict `PASS`, gate verdict `PASS`, `11`
  checks, `0` failures, `cache_hit` mean service `236.74 ms`, and `cache_hit`
  service speedup `17.98x` versus full prefill.
- `benchmarks/python/package_resident_suite_evidence.py` packages a suite
  manifest and all existing referenced artifacts into one handoff directory
  with a `resident-suite-evidence-index.json` index.
- Dax commit `3f967990` adds `/bench summary <resident-regression-suite.json>`
  so the operator panel can read resident suite manifests and show suite
  verdicts, gate failures, and referenced artifact paths.
- Dax commit `36252308` adds `/bench run <mlx-worktree> [output-dir] [tag]`
  so the operator panel can launch the bounded resident regression suite and
  summarize the generated manifest.
- `benchmarks/python/cache_create_optimization_probe.py` isolates the
  cache-create overhead signal. On the M64 Qwen A3B suite it measured
  `prepare_share=0.439`, `cache_hit_speedup=17.981`, and estimated foreground
  cache-create service after deferred preparation at `235.55 ms`.
- `benchmarks/python/runtime_profile_comparison_suite.py` can now run the same
  resident benchmark across multiple engine presets and attach the
  cache-create optimization report for each preset.
- `benchmarks/python/calibrate_resident_thresholds.py` generates stricter
  regression thresholds from measured gate reports. The M64 Qwen A3B
  calibration sets cache-hit service at `295.93 ms`, cache-create service at
  `525.28 ms`, cache-create prepare share at `0.549`, and cache-hit speedup at
  `13.49x`.
- `docs/mac-local-inference-platform/resident-operator-runbook.md` is the
  current reproduction path for the M64-M70 operator workflow.
- M72 adds `request-derived` plus `agent-workspace-request`, using
  `prefix_cache_population_mode=request` to derive reusable prefixes from the
  foreground request cache when safe. Live comparison is the next required
  evidence step.
- M73 live comparison on Qwen A3B produced:
  `sync-safe PASS`, `async-experimental SKIP`, and `request-derived FAIL`.
  `request-derived` should not be promoted for this model stack; `sync-safe`
  remains the reliable baseline while async needs maturation/pending-wait work.
- M74 adds `--threshold-calibration-json` to the resident regression suite, so
  calibrated thresholds can be applied directly to future gate runs.
- Dax commit `91bcc93a` adds `/bench profiles <runtime-profile-comparison.json>`
  so the operator panel can inspect M73 profile comparison evidence directly.
- `benchmarks/python/runtime_profile_comparison_gate.py` gates profile
  comparison reports. On M73 it passed `sync-safe` and failed
  `request-derived` on cache-hit speedup, matching the live evidence.
- `benchmarks/python/package_runtime_profile_evidence.py` packages M73/M76
  comparison evidence into `artifacts/m77-runtime-profile-evidence` with an
  index and zero missing artifacts.
- M78 selects async cache maturation and pending-wait tuning as the next
  performance target. `sync-safe` remains the reliable baseline, and
  `request-derived` is not recommended for Qwen A3B.
- M79 adds `benchmarks/python/async_maturation_sweep.py` and proves async
  maturation on Qwen A3B repeated long prompts:
  - stable report:
    `artifacts/m79-async-maturation/async-maturation-qwen-a3b-m79-stable.json`
  - result: `PASS`, `20` combinations, `8` first-hit conversions, `17`
    mature-cache hits
  - best steady-state reuse: `grace=0`, `wait=0`, `6.89x` speedup, actual
    prefill reduced to `9` tokens
  - best first-hit conversion: `grace=0`, `wait=1000`, pending wait
    `801.01 ms`, roughly break-even first-hit latency
  - decision: keep `sync-safe` as default, but use tuned async for repeated
    agent-workspace context reuse.
- M80 adds `agent-workspace-async` and
  `benchmarks/python/async_maturation_gate.py`:
  - gate report:
    `artifacts/m80-agent-workspace-async/async-maturation-gate-qwen-a3b-m80.json`
  - profile settings: `async-experimental`, `prefix_cache_async_idle_grace_ms=0`,
    `prefix_cache_pending_wait_ms=0`
  - gate result: `PASS`, with `17` mature hits, `6.89x` mature speedup,
    `9` mature prefill tokens, and `248.66 ms` mature service time
- M81 adds workload-intent selection:
  - `coding-agent` maps to `agent-workspace-async`
  - Python integrations use `EngineUiClient.apply_workload_intent`
  - Dax uses `dax mlx-engine --intent coding-agent`
- M82 makes Dax generation sessions apply `coding-agent` intent automatically
  for `--prompt` and `--interactive`, while status-only inspection remains
  read-only.
- M83 measures the automatic Dax prompt path against explicit intent and manual
  profile selection:
  - artifact:
    `artifacts/m83-dax-workload-intent/dax-workload-intent-qwen-a3b-m83.json`
  - result: `PASS`
  - auto/manual-profile wall-time ratio: `0.998`
  - auto/explicit-intent wall-time ratio: `1.000`
- M84 measures repeated automatic Dax coding-agent prompts with shared context:
  - artifact:
    `artifacts/m84-dax-repeated-context/dax-repeated-context-qwen-a3b-m84.json`
  - result: `PASS`
  - service speedup: `7.12x`
  - actual prefill reduced from `2092` tokens to `18` tokens on the best hit
- M85 adds an explicit regression gate for the M84 product path:
  - artifact:
    `artifacts/m85-dax-repeated-context-gate/dax-repeated-context-gate-qwen-a3b-m85.json`
  - result: `PASS`
  - requires at least `1` cache-hit turn, at least `2.0x` best-hit speedup,
    baseline prefill of at least `512` tokens, hit prefill at most `32`
    tokens, and hit service latency at most `400.0 ms`
- M86 wires the Dax product-path benchmark and gate into the resident suite:
  - suite flag: `--include-dax-repeated-context`
  - suite artifact:
    `artifacts/m86-dax-suite-product-path/resident-regression-suite-m86-qwen-a3b-dax-product.json`
  - Dax gate artifact:
    `artifacts/m86-dax-suite-product-path/dax-repeated-context-gate-m86-qwen-a3b-dax-product.json`
  - result: suite `PASS`, Dax gate `PASS`, `2` cache-hit turns,
    `22.06x` best-hit speedup, and best-hit prefill `18` tokens
- M87 packages the Dax product-path suite evidence:
  - package index:
    `artifacts/m87-dax-product-evidence-package/resident-suite-evidence-index.json`
  - result: suite `PASS`, Dax gate `PASS`, copied `4` artifacts, and exposes
    cache-hit count, best-hit speedup, prefill reduction, and best-hit service
    latency in the package index
- M88 exposes product-path coverage through Dax:
  - Dax commit: `e8f5da12 Add MLX product bench mode`
  - TUI command: `/bench run product <mlx-worktree> [output-dir] [tag]`
  - existing resident-suite command remains compatible
  - Dax summaries now show product gate verdict and product-path cache metrics
- M89 validates the Dax product mode against the live Qwen A3B resident server:
  - suite artifact:
    `artifacts/m89-dax-operator-product-run/resident-regression-suite-m89-qwen-a3b-dax-product.json`
  - package index:
    `artifacts/m89-dax-operator-product-evidence-package/resident-suite-evidence-index.json`
  - result: suite `PASS`, Dax gate `PASS`, `2` cache-hit turns,
    `19.20x` best-hit speedup, best-hit prefill `18` tokens, and best-hit
    service latency `227.23 ms`
- M90 adds a first-hit latency gate:
  - artifact:
    `artifacts/m90-first-hit-latency/dax-first-hit-latency-gate-m90-qwen-a3b.json`
  - result: `PASS`, scheduled pre-hit service `1386.49 ms`, scheduled pre-hit
    prefill `2092` tokens, first-hit speedup `19.20x`, and first-hit prefill
    `18` tokens
- M91 sweeps existing Dax profile choices against that first-hit gate:
  - artifact:
    `artifacts/m91-first-hit-scheduling-sweep/dax-first-hit-scheduling-sweep-m91-qwen-a3b.json`
  - result: sweep `PASS`, target `FAIL`; best observed profile
    `agent-workspace`, scheduled pre-hit service `1375.97 ms`, scheduled
    pre-hit ratio `0.971`, scheduled pre-hit prefill `2092` tokens, and first
    mature hit `231.92 ms` with `18` prefill tokens
  - implication: existing profile selection does not convert the expensive
    scheduled pre-hit turn; the next readiness target is a runtime behavior or
    profile change that alters scheduler/cache interaction.
- M92 adds first-hit conversion as a named product profile:
  - profile: `agent-workspace-first-hit`
  - behavior: `engine_preset=request-derived`,
    `prefix_cache_population_mode=request`
  - gate artifact:
    `artifacts/m92-first-hit-conversion/dax-first-hit-conversion-gate-m92-request-probe.json`
  - result: `PASS`, conversion turn `2`, conversion prefill `18` tokens,
    conversion service ratio `0.813`, `cache_split_prefill=True`, mature hit
    speedup `2.94x`, mature hit prefill `18` tokens
  - note: the live artifact used equivalent `agent-workspace-request` behavior
    because the resident server had not been restarted with the new profile
    catalog yet.
- M93 adds a product-path first-hit regression gate:
  - script: `benchmarks/python/dax_product_first_hit_gate.py`
  - summary artifact:
    `artifacts/m93-product-first-hit-gate/dax-product-first-hit-summary-m93-qwen-a3b-request-profile.json`
  - result: `PASS`, conversion turn `2`, conversion prefill `18` tokens,
    conversion ratio `0.843`, mature hit speedup `2.996x`, mature hit prefill
    `18` tokens
  - implication: Dax/product validation can now fail specifically when the
    second repeated-context turn regresses to full prefill.
- M94 integrates first-hit product validation into the resident suite:
  - suite option: `--include-dax-first-hit`
  - profile option: `--dax-first-hit-profile`
  - suite artifact:
    `artifacts/m94-suite-first-hit-product/resident-regression-suite-m94-qwen-a3b-first-hit-product.json`
  - evidence package:
    `artifacts/m94-suite-first-hit-product-evidence-package/resident-suite-evidence-index.json`
  - result: suite `PASS`, `dax_first_hit` `PASS`, conversion turn `2`,
    conversion prefill `18` tokens, conversion ratio `0.837`, mature hit
    speedup `3.052x`, mature hit prefill `18` tokens
- M95 adds lower-memory agent product mode:
  - profile: `agent-workspace-low-memory`
  - behavior: `engine_preset=request-derived`,
    `prefix_cache_population_mode=request`, `prefix_cache_max_entries=4`,
    `prefix_cache_memory_limit_mb=64.0`, `prefix_cache_min_entries=1`
  - artifact:
    `artifacts/m95-lower-memory-product-profile/dax-product-first-hit-summary-m95-qwen-a3b-memory-saver.json`
  - result: lower-memory first-hit gate `PASS`, conversion turn `2`,
    conversion prefill `18` tokens, conversion ratio `0.588`, mature hit
    speedup `3.581x`, mature hit prefill `18` tokens
- M96 records the routing decision:
  - report:
    `docs/mac-local-inference-platform/performance-decision-report-m91-m96.md`
  - default long-session coding-agent profile: `agent-workspace-async`
  - immediate second-turn profile: `agent-workspace-first-hit`
  - lower-memory profile: `agent-workspace-low-memory`
- M97 validates the restarted-server first-hit profile path:
  - direct artifact:
    `artifacts/m97-direct-first-hit-profile/dax-product-first-hit-summary-m97-qwen-a3b-first-hit-direct.json`
  - suite artifact:
    `artifacts/m97-suite-first-hit-direct/resident-regression-suite-m97-qwen-a3b-first-hit-suite-direct.json`
  - result: `agent-workspace-first-hit` direct gate `PASS`, suite path `PASS`,
    conversion turn `2`, conversion prefill `18` tokens, direct conversion
    ratio `0.783`, suite conversion ratio `0.785`
- M98 validates the restarted-server lower-memory profile path:
  - direct artifact:
    `artifacts/m98-direct-low-memory-profile/dax-product-first-hit-summary-m98-qwen-a3b-low-memory-direct.json`
  - suite artifact:
    `artifacts/m98-suite-low-memory-direct/resident-regression-suite-m98-qwen-a3b-low-memory-suite-direct.json`
  - result: `agent-workspace-low-memory` direct gate `PASS`, suite path
    `PASS`, conversion turn `2`, conversion prefill `18` tokens, direct
    conversion ratio `0.776`, suite conversion ratio `0.797`
- M99 wires the validated profiles into Dax product routing:
  - Dax commit: `167cac48`
  - `--intent first-hit` and `--intent coding-agent-first-hit` route to
    `agent-workspace-first-hit`
  - `--intent low-memory` and `--intent coding-agent-low-memory` route to
    `agent-workspace-low-memory`
  - `/bench run product-first-hit ...` runs the resident suite first-hit path
    with `agent-workspace-first-hit`
  - `/bench run product-low-memory ...` runs the resident suite first-hit path
    with `agent-workspace-low-memory`
  - Dax validation passed: focused MLX status tests, typecheck, Biome check,
    and diff whitespace check
- M100 adds end-to-end operator wall-time evidence:
  - script: `benchmarks/python/dax_operator_wall_time_report.py`
  - artifact:
    `artifacts/m100-operator-wall-time/dax-operator-wall-time-m100-qwen-a3b.json`
  - result: report `PASS` across M97/M98 direct and suite cases
  - mature service speedups: `2.382x` to `2.585x`
  - mature wall-time speedups: `1.425x` to `2.190x`
  - mean Dax/operator overhead: roughly `1.5s` to `1.9s`
- M101 gates the default profile decision:
  - script: `benchmarks/python/dax_default_profile_decision_gate.py`
  - artifact:
    `artifacts/m101-default-profile-decision-gate/default-profile-decision-gate-m101-qwen-a3b.json`
  - result: `PASS`, `20` checks, `0` failures
  - default coding-agent profile: `agent-workspace-async`
  - explicit immediate second-turn profile: `agent-workspace-first-hit`
  - explicit lower-memory profile: `agent-workspace-low-memory`
- M102 exposes those decisions through Dax TUI shortcuts:
  - Dax commit: `08c14b5d`
  - `/profile default`, `/profile coding-agent`, and `/profile async` route to
    `agent-workspace-async`
  - `/profile first-hit` routes to `agent-workspace-first-hit`
  - `/profile low-memory` routes to `agent-workspace-low-memory`
  - `/profiles` and `/profile recommended` show the shortcut mapping
- M103 defines the operator-overhead reduction target:
  - script: `benchmarks/python/dax_operator_overhead_reduction_report.py`
  - artifact:
    `artifacts/m103-operator-overhead-reduction/operator-overhead-reduction-m103-qwen-a3b.json`
  - result: `PASS`, mean operator overhead `1635.49 ms`
  - target: reduce product invocation overhead toward `500 ms`
  - priority: avoid per-request Dax CLI startup for repeated product turns
- M104 extends prompt-processing evidence:
  - script: `benchmarks/python/dax_prompt_processing_extension_report.py`
  - artifact:
    `artifacts/m104-prompt-processing-extension/prompt-processing-extension-m104-qwen-a3b.json`
  - result: `PASS`, `16` rows analyzed
  - long-prefill prompt progress consumes `0.970` of service time on average
  - short-prefill prompt progress still consumes `0.670` of service time on
    average
- M105 defines the fast Dax invocation path:
  - script: `benchmarks/python/dax_fast_invocation_path_report.py`
  - artifact:
    `artifacts/m105-fast-dax-invocation/fast-dax-invocation-m105-qwen-a3b.json`
  - result: `PASS`
  - recommended path: `resident-dax-client`
  - acceptance target: mean operator overhead `<=500 ms`
- M106 defines profile auto-selection:
  - script: `benchmarks/python/dax_profile_auto_selection_policy.py`
  - artifact:
    `artifacts/m106-profile-auto-selection/profile-auto-selection-m106-qwen-a3b.json`
  - result: `PASS`, `6` scenarios, `0` failures
  - normal coding-agent -> `agent-workspace-async`
  - immediate second turn -> `agent-workspace-first-hit`
  - lower-memory Mac -> `agent-workspace-low-memory`
- M107 defines lower-memory Mac runtime strategy:
  - script: `benchmarks/python/mlx_lower_memory_mac_strategy.py`
  - artifact:
    `artifacts/m107-lower-memory-mac-strategy/lower-memory-mac-strategy-m107-qwen-a3b.json`
  - result: `PASS`
  - 32GB Macs default to `agent-workspace-low-memory`
  - 64GB+ Macs default to `agent-workspace-async` unless profile policy
    overrides
- M108 packages the product readiness bundle:
  - script: `benchmarks/python/mlx_product_readiness_bundle.py`
  - artifact:
    `artifacts/m108-product-readiness-bundle/product-readiness-bundle-m108-qwen-a3b.json`
  - result: `PASS`, readiness `ready-for-next-implementation-lane`
  - bundle contains `9` passing evidence artifacts and `0` failures
- M109 adds the resident Dax client benchmark path:
  - `benchmarks/python/dax_repeated_context_bench.py --client-mode resident`
  - direct endpoint: `/v1/completions`
  - fallback: `--client-mode cli`
  - product benchmark rows now include `overhead_ms`
  - readiness artifact:
    `artifacts/m109-resident-dax-client/resident-dax-client-m109-qwen-a3b.json`
- M110 adds operator overhead gating:
  - script: `benchmarks/python/dax_operator_overhead_gate.py`
  - artifact:
    `artifacts/m110-overhead-gate/operator-overhead-gate-m110-current-baseline.json`
  - current CLI baseline mean overhead: `1635.49 ms`
  - fast-path live target remains `<=500 ms`
- M111 defines extended prompt sweep matrix:
  - script: `benchmarks/python/extended_prompt_sweep_matrix.py`
  - artifact:
    `artifacts/m111-extended-prompt-sweep/extended-prompt-sweep-matrix-m111-qwen-a3b.json`
  - result: `PASS`, `72` cases across prompt length, reuse, transport, and
    profile axes
- M112 adds lower-memory runtime gates:
  - script: `benchmarks/python/lower_memory_runtime_gate.py`
  - artifact:
    `artifacts/m112-lower-memory-gate/lower-memory-runtime-gate-m112-qwen-a3b.json`
  - result: `PASS`, max peak memory `22.682 GB`, cache limit `64 MB`,
    conversion prefill `18` tokens
- M113 adds profile auto-selection integration gating:
  - script: `benchmarks/python/profile_auto_selection_integration_gate.py`
  - artifact:
    `artifacts/m113-auto-selection-integration/auto-selection-integration-gate-m113-qwen-a3b.json`
  - result: `PASS`, `5` checks, `0` failures
- M114 adds product runtime readiness suite:
  - script: `benchmarks/python/product_runtime_readiness_suite.py`
  - artifact:
    `artifacts/m114-readiness-regression-suite/product-runtime-readiness-suite-m114-qwen-a3b.json`
  - result: `PASS`, readiness `ready-for-live-resident-client-validation`,
    `5` evidence artifacts, `0` failures

## Current Qwen Result

- In-flight async prefix builds are deduplicated.
- Duplicate foreground requests can wait for a pending prefix build and convert
  into a cache hit when `prefix_cache_pending_wait_ms` is enabled.
- Qwen3.5/Next cache continuation remains blocked for generic replay-free
  prefix storage because `ArraysCache` carries recurrent state without offset or
  trim semantics.
- Safe strategy for this model family:
  `split_prefill_or_async_build`
- Required lower-level work:
  `model_specific_recurrent_state_continuation_for_arrays_cache`

## Product Implication

For a fast Mac local-inference product, expose these controls as named profiles
instead of raw internals:

- `Interactive`: prioritize immediate foreground latency.
- `Agent Workspace Async`: use M79-proven steady-state async cache reuse for
  repeated coding-agent context.
- `Agent Workspace First Hit`: use request-derived split-prefill conversion
  when the second repeated-context turn must become responsive immediately.
- `Agent Workspace Low Memory`: cap cache entries and memory while still
  accepting bounded first-hit conversion for smaller-memory Macs.
- `Memory Saver`: keep as a generic conservative profile, not the preferred
  coding-agent lower-memory product route.
- `Diagnostics`: run the readiness probes and show cache continuation blockers.

Operator shortcuts:

- `/profile default` for normal coding-agent sessions.
- `/profile first-hit` when immediate second-turn responsiveness matters more
  than steady-state async behavior.
- `/profile low-memory` for smaller-memory Macs or constrained cache residency.

## Tensor Parallelism Note

MLX has tensor-parallel and distributed primitives, but the current resident
engine does not use them.

- Framework support exists through `mlx.core.distributed`, distributed
  collectives, `shard_linear`, `shard_inplace`, `AllToShardedLinear`, and
  `ShardedToAllLinear`.
- MLX model format alone does not make inference tensor-parallel.
- The current `mlx_engine/` resident service should be treated as a
  single-process resident engine until an explicit distributed model-sharding
  milestone is added.
- Tensor parallelism is more relevant for multi-Mac or very large model work;
  the current single-Mac path should prioritize prompt processing, cache reuse,
  scheduling, warmup/JIT behavior, Dax/operator overhead, and quantized kernels
  first.

## Live Product Readiness: M115-M120

The M115-M120 lane validates the resident server against a live Qwen3.6-35B-A3B
MLX model and packages the result as a product-readiness bundle.

Evidence:

- M115 resident repeated-context benchmark:
  `artifacts/m115-live-resident-client/dax-resident-client-m115-qwen-a3b.json`
  - verdict: `PASS`
  - best hit speedup: `6.899x`
- M116 fast-path overhead gate:
  `artifacts/m116-fast-path-overhead/fast-path-overhead-gate-m116-qwen-a3b.json`
  - verdict: `PASS`
  - mean overhead: `4.598 ms`
- M117 live prompt transport sweep:
  `artifacts/m117-live-extended-prompt-sweep/live-prompt-transport-sweep-m117-qwen-a3b.json`
  - verdict: `PASS`
  - rows: `8`
- M118 lower-memory gate:
  `artifacts/m118-live-lower-memory/lower-memory-live-gate-m118-qwen-a3b.json`
  - verdict: `PASS`
  - max peak memory: `24.054 GB`
- M119 runtime auto-selection:
  `artifacts/m119-auto-selection-runtime/dax-auto-selected-m119-qwen-a3b.json`
  - verdict: `PASS`
  - auto-selected profile: `agent-workspace-first-hit`
- M120 live readiness bundle:
  `artifacts/m120-live-product-readiness/live-product-readiness-bundle-m120-qwen-a3b.json`
  - verdict: `PASS`
  - readiness: `live-validated`

Readiness position:

- Resident Dax client transport is validated.
- Hot-path operator overhead is under the `<=500 ms` target by a wide margin.
- Lower-memory runtime behavior is gated with peak memory and cache-limit
  checks.
- Profile auto-selection is implemented in the benchmark path and validated
  against the live server.

Remaining constraints:

- Qwen recurrent-state generic cache continuation still needs model-specific
  continuation work.
- Tensor parallelism is outside the current single-process resident-engine
  lane.
- The next engine milestone should convert this into a one-command live
  regression suite and add server-side profile selection from request metadata.

## M121 One-Command Live Regression

M121 converts the M115-M119 validation sequence into a focused live regression
command:

- script: `benchmarks/python/run_live_product_regression_suite.py`
- artifact:
  `artifacts/m121-live-product-regression-suite/live-product-regression-suite-m121-qwen-a3b.json`

Validated result:

- suite verdict: `PASS`
- readiness: `live-regression-passing`
- evidence artifacts: `7`
- resident repeated-context speedup: `7.166x`
- fast-path overhead mean: `4.234 ms`
- lower-memory max peak memory: `24.056 GB`
- auto-selected first-hit speedup: `5.265x`

Operational implication:

- Product readiness can now be checked by running the M121 suite against a live
  resident server.
- The next readiness gap is server-side profile selection from request metadata,
  because product clients should send workload intent, not benchmark-specific
  profile flags.

## M122 Request Metadata Profile Selection

M122 adds request-level workload intent handling to the resident engine.

Implementation:

- `mlx_engine/request_profiles.py` owns the lightweight selector and does not
  import MLX.
- `GenerateRequest`, `CompletionRequest`, and `ChatCompletionRequest` inherit
  request profile hints.
- `/generate`, `/v1/completions`, and `/v1/chat/completions` apply the selected
  runtime profile before request metadata and prefill policy selection.
- Streaming and non-streaming paths both use the same selector.
- `engine_metrics` carries `request_runtime_profile`,
  `request_runtime_profile_source`, `request_runtime_profile_reason`, and the
  submitted workload hint fields.

Validation:

- gate:
  `artifacts/m122-request-profile-metadata/request-profile-metadata-gate-m122-qwen-a3b.json`
- verdict: `PASS`
- scenarios: `6`
- schema checks: `4`

Operational note:

- Existing live servers need a restart before this request metadata behavior is
  available.
- M123 should restart the live resident server and run a request-metadata
  regression against the updated process.

## M123 Live Request Metadata Regression

M123 restarts the resident service from the updated worktree and validates
request metadata profile routing against live OpenAI-compatible endpoints.

Evidence:

- artifact:
  `artifacts/m123-live-request-profile-metadata/live-request-profile-metadata-m123-qwen-a3b.json`
- verdict: `PASS`
- rows: `3`
- failures: `0`

Live cases:

- `/v1/completions` with `workload_intent=first-hit` selected
  `agent-workspace-first-hit`.
- `/v1/chat/completions` with `workload_intent=coding-agent` and
  `memory_class_gb=32` selected `agent-workspace-low-memory`.
- `/v1/completions` with `runtime_profile=interactive` and conflicting
  low-memory hints selected `interactive`, proving manual override precedence.

Readiness position:

- Product clients can now send workload metadata on the request itself.
- The routing decision is visible in `engine_metrics`.
- The next regression gap is including this live request metadata probe in the
  one-command product regression suite.

## M124 Product Regression Suite Coverage

M124 integrates the live request metadata probe into the one-command product
regression suite.

Evidence:

- artifact:
  `artifacts/m124-live-product-regression-suite/live-product-regression-suite-m124-qwen-a3b.json`
- verdict: `PASS`
- readiness: `live-regression-passing`
- evidence artifacts: `8`
- failures: `0`

Covered live gates:

- resident repeated-context first-hit path
- fast-path operator overhead
- prompt transport sweep
- lower-memory runtime behavior
- auto-selection runtime gate
- auto-selected live repeated-context path
- request metadata profile routing

Readiness position:

- Request metadata profile routing is now part of the live regression suite.
- A product client contract can be written against the validated behavior:
  send workload metadata on OpenAI-compatible requests, inspect
  `engine_metrics.request_runtime_profile`, and reserve manual
  `runtime_profile` for explicit operator override.

## M125 Product Client Contract

The product/client contract for request metadata lives at:

- `docs/mac-local-inference-platform/request-metadata-client-contract.md`

It defines:

- accepted request metadata fields
- selection precedence
- workload-intent to runtime-profile routing
- completion and chat examples
- validation commands
- current limitation around global profile mutation under future true
  concurrency

## M126 Product-Mode Helper

Product-mode request metadata helpers now live in `mlx_engine/ui_client.py`.

Validated helper:

- `metadata_for_product_mode(...)`
- `apply_product_mode(...)`

Validation:

- artifact:
  `artifacts/m126-product-mode-metadata/product-mode-metadata-m126-qwen-a3b.json`
- verdict: `PASS`
- cases: `7`
- failures: `0`

Product modes:

- `chat`
- `coding-agent`
- `coding-agent-first-hit`
- `coding-agent-low-memory`
- `diagnostics`

Readiness position:

- Product clients no longer need to hand-assemble request metadata fields.
- The next integration step is to wire this into a concrete client path.

## M127 Dax Request Metadata Integration

Dax now sends MLX workload routing as per-request metadata for prompt and
interactive generation instead of mutating the resident engine profile before
each product request.

Dax commit:

- `28b5493f Add MLX request metadata to Dax prompts`

Changed Dax behavior:

- `dax mlx-engine --prompt ...` derives request metadata from `--intent`,
  `--profile`, or the default coding-agent product path.
- `dax mlx-engine --interactive` keeps the same per-request metadata for panel
  generations.
- status-only `--profile` and `--intent` operations still use `/engine/config`
  as explicit operator controls.
- in-panel `/profile` remains a deliberate global runtime-profile override.

Validation:

- Dax focused test:
  `npm run test -- mlx-engine-status.test.ts`
- result: `32` tests passed
- Dax coding-agent build:
  `npm run build`
- Dax pre-commit checks passed during commit.

Readiness position:

- Dax no longer needs to globally change the server profile just to run the
  normal coding-agent prompt path.

## M128 Live Dax Request Metadata Smoke

M128 validates the committed Dax path against the live Qwen A3B resident MLX
server.

Live command shape:

```bash
node /Users/jeffreycruz/Development/AI_AGENTS/dax-stereo/packages/coding-agent/dist/cli.js mlx-engine \
  --base-url http://127.0.0.1:8773 \
  --prompt "M128 Dax request metadata artifact. Reply with one short sentence." \
  --max-tokens 8 \
  --json
```

Artifact:

- `artifacts/m128-dax-request-metadata-smoke/dax-request-metadata-smoke-m128-qwen-a3b.json`

Observed live metrics:

- `engine_metrics.request_runtime_profile`: `agent-workspace-async`
- `engine_metrics.request_runtime_profile_source`: `request_metadata`
- `engine_metrics.request_runtime_profile_applied`: `true`
- `engine_metrics.workload_intent`: `coding-agent`
- `engine_metrics.agentic_workload`: `true`
- `engine_metrics.repeated_workspace`: `true`

Readiness position:

- The Dax product/operator path is now live-proven to reach MLX's request
  metadata router.

## M129 Dax Operator Metadata Contract

The Dax-facing request metadata behavior is documented in:

- `docs/mac-local-inference-platform/request-metadata-client-contract.md`
- `docs/mac-local-inference-platform/resident-operator-runbook.md`

Operator distinction:

- `--prompt` and `--interactive` use per-request metadata.
- status-only `--profile` and `--intent` mutate `/engine/config`.
- interactive `/profile` is a deliberate global override for operators.

Readiness position:

- Future Dax, Prowl, or UI client work has a clear contract for when to use
  request metadata versus global engine controls.

## M130 Dax Request Route Visibility

Dax now surfaces request metadata routing in the interactive prompt panel header.

Dax commit:

- `3afb64d1 Show MLX request route in Dax prompt panel`

Displayed examples:

- `request route: engine default`
- `request route: workload_intent=coding-agent flags=agentic,repeated`
- `request route: workload_intent=first-hit flags=agentic,repeated,first-hit`
- `request route: runtime_profile=interactive`

Validation:

- Dax focused test:
  `npm run test -- mlx-engine-status.test.ts`
- result: `34` tests passed
- Dax coding-agent build:
  `npm run build`
- Dax pre-commit checks passed during commit.

Readiness position:

- Operators can now see whether a Dax prompt session is using request metadata
  instead of silently relying on implicit routing.

## M131 Dax Metadata Regression Suite Coverage

The one-command live product regression suite now includes the real Dax CLI
request-metadata smoke path.

Added verifier:

- `benchmarks/python/dax_request_metadata_smoke.py`

Suite integration:

- `benchmarks/python/run_live_product_regression_suite.py`
- artifact key: `dax_request_metadata_smoke`
- covered milestone: `M131`

Live validation:

- artifact:
  `artifacts/m131-dax-request-metadata-suite/dax-request-metadata-smoke-m131-qwen-a3b.json`
- verdict: `PASS`
- checks: `5`
- failures: `0`
- runtime profile source: `request_metadata`

Readiness position:

- M121-style live regression can now fail if the Dax product path stops sending
  request metadata correctly.

## M132 Performance Comparison Refresh

M132 packages an updated initial-to-current comparison.

Added report generator:

- `benchmarks/python/milestone_performance_comparison_report.py`

Artifacts:

- `artifacts/m132-performance-comparison/performance-comparison-m132-qwen-a3b.json`
- `artifacts/m132-performance-comparison/performance-comparison-m132-qwen-a3b.md`

Comparison coverage:

- initial cold `gpt-oss-20b-MXFP4-Q8` prompt sweep
- warmed resident `gpt-oss-20b-MXFP4-Q8` baseline
- current Qwen A3B prompt transport sweep
- M121 and M124 repeated-context product-path results
- M131 Dax request-metadata smoke

Readiness position:

- The current evidence still points to repeated-context reuse and server-side
  routing as the meaningful product levers, not another isolated short-prompt
  micro-benchmark.

## M133 Operator Readiness Checkpoint

Operator readiness is now summarized by the following evidence chain:

- Dax request metadata integration: `28b5493f`
- Dax request route visibility: `3afb64d1`
- live Dax request metadata artifact:
  `artifacts/m131-dax-request-metadata-suite/dax-request-metadata-smoke-m131-qwen-a3b.json`
- performance comparison:
  `artifacts/m132-performance-comparison/performance-comparison-m132-qwen-a3b.md`
- operator docs:
  `docs/mac-local-inference-platform/resident-operator-runbook.md`
- client contract:
  `docs/mac-local-inference-platform/request-metadata-client-contract.md`

Checkpoint result:

- Dax can run product prompts without global profile mutation.
- The live server confirms metadata-derived profile selection.
- The operator surface shows the active request route.
- The regression suite has a Dax-specific metadata smoke step.

## M134 Next Performance Target

The next optimization target is server-side prompt-processing automation for
repeated workspace turns.

Priority:

1. keep request metadata as the product control plane
2. profile request-scoped cache admission and async prefix-build scheduling
3. reduce first reusable-turn latency without increasing memory pressure
4. preserve Dax/operator visibility and live regression coverage

Non-targets for the next slice:

- UI polish beyond request-route visibility
- raw model-format changes
- speculative decoding
- multi-machine distribution

Rationale:

- warmed prompt processing is already much better than the initial cold sweep
- current Qwen A3B long-prompt transport is in the warmed resident performance
  class
- product wins are dominated by avoiding repeated prefill and making the right
  request-scoped routing decision automatically

## M135 Request-Scoped Cache Admission Probe

M135 measures request-metadata-routed cache admission across product modes.

Added:

- `benchmarks/python/request_scoped_cache_admission_probe.py`

Live artifact:

- `artifacts/m135-request-scoped-cache-admission/request-scoped-cache-admission-m135-qwen-a3b.json`

Result:

- verdict: `PASS`
- rows: `5`
- failures: `0`

Covered cases:

- `coding_agent`
- `first_hit`
- `low_memory`
- `interactive`
- `diagnostics`

## M136 Async Prefix-Build Scheduling Profile

M136 gates the M135 admission rows for observed async and request-derived cache
population behavior.

Artifact:

- `artifacts/m136-m139-request-scoped-gates/m136_async_prefix_build_scheduling-m136-m139-qwen-a3b.json`

Result:

- verdict: `PASS`
- async and request-derived modes were both observed.

## M137 First Reusable-Turn Latency Gate

M137 gates first reusable-turn behavior using the repeated-context product
path.

Artifact:

- `artifacts/m136-m139-request-scoped-gates/m137_first_reusable_turn_latency-m136-m139-qwen-a3b.json`

Result:

- verdict: `PASS`
- M124 repeated-context speedup remains above threshold.
- best-hit prefill remains bounded at `11` tokens.

## M138 Memory-Pressure Bounded Cache Policy

M138 validates that lower-memory product routing still keeps repeated-context
reuse.

Artifact:

- `artifacts/m136-m139-request-scoped-gates/m138_memory_bounded_cache_policy-m136-m139-qwen-a3b.json`

Result:

- verdict: `PASS`
- lower-memory metadata selects `agent-workspace-low-memory`
- lower-memory repeated-context speedup remains above threshold.

## M139 Request-Scoped Routing Isolation

M139 starts isolating request metadata routing from persistent global profile
state.

Code change:

- `mlx_engine/resident_service.py`
- non-stream generation now applies request profile defaults inside
  `request_runtime_profile_scope(...)`
- the runtime configuration snapshot is restored after the request
- response metrics include `request_runtime_profile_scoped=true` for scoped
  non-stream calls

Gate artifact:

- `artifacts/m136-m139-request-scoped-gates/m139_request_scoped_routing_isolation-m136-m139-qwen-a3b.json`

Result:

- verdict: `PASS`
- all request-metadata cases routed through `request_metadata`

Remaining follow-up:

- streaming routes still use the compatibility path and should be moved to the
  scoped context in the next lane.

## M140 Live Product Regression Expansion

M140 expands the one-command live product regression suite with:

- request-scoped cache admission
- async/request-derived scheduling gate
- first reusable-turn latency gate
- lower-memory cache policy gate
- request-scoped routing isolation gate

Suite artifact:

- `artifacts/m140-live-product-regression-suite/live-product-regression-suite-m140-qwen-a3b.json`

Result:

- verdict: `PASS`
- readiness: `live-regression-passing`
- artifacts: `11`
- failures: `0`
- covered milestones include `M135` through `M140`

## M141 Dax Product Mode Controls

Dax now exposes product-mode shortcuts for MLX routing.

Dax commit:

- `efb3cc78 Add MLX product mode shortcuts to Dax`

Added CLI option:

- `--product-mode <mode>`

Supported modes:

- `chat`
- `coding-agent`
- `coding-agent-first-hit`
- `coding-agent-low-memory`
- `diagnostics`

Validation:

- Dax focused MLX test: `34` passed
- Dax coding-agent build: passed
- Dax pre-commit checks: passed

## M142 Performance Checkpoint

M142 packages the M135-M141 decision point.

Artifacts:

- `artifacts/m142-performance-checkpoint/performance-checkpoint-m142-qwen-a3b.json`
- `artifacts/m142-performance-checkpoint/performance-checkpoint-m142-qwen-a3b.md`

Result:

- verdict: `PASS`
- live suite verdict: `PASS`
- request-scoped gates: `PASS`

Decision:

- Continue request-scoped prompt-processing automation.
- Next lane should prioritize streaming request-profile scope parity, first
  reusable-turn latency reduction, cache-admission threshold tuning, and Dax
  product-mode docs/smokes.

## M143 Streaming Request-Profile Scope Parity

M143 moves streaming request-profile handling onto the same scoped path as
non-stream generation.

Code change:

- `mlx_engine/resident_service.py`
- `stream_generate_jsonl`
- `stream_openai_completion`
- `stream_openai_chat_completion`

Result:

- streaming routes now apply request metadata inside
  `request_runtime_profile_scope(...)`
- streaming responses report scoped request-profile metrics instead of relying
  on the compatibility path

## M144 Streaming Metadata Regression Gate

M144 validates streaming request-profile scope parity.

Artifact:

- `artifacts/m144-streaming-metadata-scope/streaming-request-metadata-scope-m144-qwen-a3b.json`

Result:

- verdict: `PASS`
- rows: `2`
- failures: `0`
- readiness: `streaming-request-scope-parity`

## M145 First Reusable-Turn Latency Reduction Probe

M145 packages the first reusable-turn latency gate from the repeated-context
and cache-admission artifacts.

Artifacts:

- `artifacts/m145-m146-cache-turn-gates/cache-threshold-and-turn-gates-m145-m146-qwen-a3b.json`
- `artifacts/m145-m146-cache-turn-gates/m145_first_reusable_turn_reduction-m145-m146-qwen-a3b.json`

Result:

- verdict: `PASS`
- failures: `0`

## M146 Cache-Admission Threshold Tuning

M146 validates cache admission and threshold behavior for request-scoped
prompt-processing gates.

Artifacts:

- `artifacts/m146-cache-threshold-tuning/request-scoped-cache-admission-m146-qwen-a3b.json`
- `artifacts/m145-m146-cache-turn-gates/m146_cache_admission_thresholds-m145-m146-qwen-a3b.json`

Result:

- verdict: `PASS`
- rows: `5`
- failures: `0`
- readiness: `cache-admission-measured`

## M147 Dax Product-Mode Smoke Commands

M147 documents the operator-facing Dax product-mode commands.

Example command shape:

```bash
node packages/coding-agent/dist/cli.js mlx-engine \
  --base-url http://127.0.0.1:8773 \
  --product-mode coding-agent-first-hit \
  --prompt "Summarize the active workspace route." \
  --json
```

Covered product modes:

- `chat`
- `coding-agent`
- `coding-agent-first-hit`
- `coding-agent-low-memory`
- `diagnostics`

## M148 Live Suite Product-Mode Coverage

M148 expands the one-command live product regression suite with:

- streaming request metadata scope
- cache threshold and first reusable-turn gates
- Dax product-mode smoke
- request-scoped concurrency probe

Suite artifact:

- `artifacts/m148-live-product-mode-suite/live-product-regression-suite-m148-qwen-a3b.json`

Result:

- verdict: `PASS`
- readiness: `live-regression-passing`
- artifacts: `15`
- failures: `0`
- covered milestones include `M143`, `M144`, `M145`, `M146`, `M148`, and
  `M149`

## M149 Request-Scoped Concurrency Safety Probe

M149 validates mixed concurrent request metadata does not persistently mutate
the active runtime profile.

Artifact:

- `artifacts/m149-request-scoped-concurrency/request-scoped-concurrency-m149-qwen-a3b.json`

Result:

- verdict: `PASS`
- rows: `3`
- failures: `0`
- before runtime profile: `interactive`
- after runtime profile: `interactive`
- readiness: `request-profile-no-bleed`

Follow-up:

- a first M149 attempt previously observed profile bleed before the passing
  rerun, so the next lane should harden lock/scope discipline with a repeated
  stress gate.

## M150 Performance Checkpoint

M150 packages the M143-M149 decision point.

Artifacts:

- `artifacts/m150-performance-checkpoint/performance-checkpoint-m150-qwen-a3b.json`
- `artifacts/m150-performance-checkpoint/performance-checkpoint-m150-qwen-a3b.md`

Result:

- verdict: `PASS`
- readiness: `m143-m150-passing-with-concurrency-follow-up`
- live suite verdict: `PASS`
- request-scoped concurrency verdict: `PASS`

Decision:

- Continue into concurrency hardening and first reusable-turn latency
  reduction.
- Do not claim complete request-scoped runtime isolation until the transient
  M149 profile-bleed observation is converted into a stronger repeated stress
  gate.

## M151-M158 Lock Hardening And Performance Checkpoint

M151-M158 hardens request-scoped runtime-profile handling and packages the next
performance report.

Code changes:

- `mlx_engine/resident_service.py` now has `runtime_config_lock`.
- runtime profile config changes, snapshots, restores, and request-scoped
  profile overrides are serialized through that lock.

Artifacts:

- `artifacts/m151-concurrency-stress/request-scoped-concurrency-stress-m151-qwen-a3b.json`
- `artifacts/m152-runtime-profile-scope-audit/runtime-profile-scope-audit-m152-qwen-a3b.json`
- `artifacts/m153-route-parity/route-parity-m153-qwen-a3b.json`
- `artifacts/m154-product-profile-policy/product-profile-policy-m154-qwen-a3b.json`
- `artifacts/m155-live-suite-lock-regression/live-product-regression-suite-m155-qwen-a3b.json`
- `artifacts/m156-performance-report/performance-report-m156-qwen-a3b.md`
- `artifacts/m157-operator-visibility/operator-visibility-m157-qwen-a3b.json`
- `artifacts/m158-performance-checkpoint/performance-checkpoint-m158-qwen-a3b.md`

Result:

- M151 stress: `PASS`, 12 iterations, 36 rows, 0 failures
- M152 static scope audit: `PASS`
- M153 route parity: `PASS`
- M154 product-profile policy: `PASS`
- M155 live suite: `PASS`, 15 artifacts, 0 failures
- M156 performance report: `PASS`
- M157 operator visibility contract: `PASS`
- M158 checkpoint: `PASS`

Performance summary:

- repeated best-hit speedup: `6.949899063306281`
- repeated best-hit service ms: `214.1152499243617`
- repeated best-hit prefill tokens: `11`
- resident prompt transport wall ms: `474.661166081205`
- CLI prompt transport wall ms: `6038.545124931261`

## Quality Gate Policy

Speed does not count as release-ready progress if response quality regresses.

Before further performance milestones are treated as production-ready, add and
run quality gates for:

- deterministic golden prompts
- cache-enabled versus cache-disabled answer comparison
- streaming versus non-stream answer parity
- loop and repetition detection
- long-context RoPE/IMRoPE recall
- cross-engine Qwen3.6 comparison against known-good `puma.cpp` and
  `panthro.cpp` behavior

Quality plan:

- `docs/mac-local-inference-platform/inference-quality-gates.md`
- `artifacts/m159-quality-gate-plan/quality-gate-plan-m159-qwen-a3b.md`

## M159-M166 Quality Gate Result

The quality-gated lane is implemented and passing end-to-end.

Passing:

- `M159` golden prompt set
- `M160` deterministic quality regression
- `M161` cache-enabled vs cache-disabled quality comparison
- `M162` streaming vs non-stream quality parity
- `M163` loop/repetition detector
- `M164` long-context RoPE/IMRoPE quality probe
- `M165` cross-engine Qwen3.6 rubric comparison
- `M166` quality-gated performance checkpoint

Resolved blocker:

- Explicit `/no_think` prompts now receive a Qwen assistant prefill
  `<think>\n\n</think>\n\n`. This prevents visible thinking output for the
  quality-gated prompts and lets the long-context sentinel prompt return the
  clean answer `ORCHID-17, LANTERN-42, HARBOR-93`.

Primary artifact:

- `artifacts/m166-quality-checkpoint/quality-checkpoint-m166-qwen-a3b.md`

## M167 Live Suite Quality Integration

M167 integrates the quality gates into the live product regression suite.

Suite artifact:

- `artifacts/m167-live-quality-regression-suite/live-product-regression-suite-m167-qwen-a3b.json`

Result:

- verdict: `PASS`
- readiness: `live-regression-passing`
- artifacts: `23`
- failures: `0`
- covered milestones now include `M159` through `M167`

Quality artifacts in the suite:

- `artifacts/m167-live-quality-regression-suite/quality-golden-set-m167-qwen-a3b.json`
- `artifacts/m167-live-quality-regression-suite/deterministic-quality-m167-qwen-a3b.json`
- `artifacts/m167-live-quality-regression-suite/cache-quality-m167-qwen-a3b.json`
- `artifacts/m167-live-quality-regression-suite/streaming-quality-m167-qwen-a3b.json`
- `artifacts/m167-live-quality-regression-suite/loop-quality-m167-qwen-a3b.json`
- `artifacts/m167-live-quality-regression-suite/long-context-quality-m167-qwen-a3b.json`
- `artifacts/m167-live-quality-regression-suite/cross-engine-quality-m167-qwen-a3b.json`
- `artifacts/m167-live-quality-regression-suite/quality-checkpoint-m167-qwen-a3b.md`

Acceptance rule:

- Future live-suite passes now require both performance/request-scope gates and
  response-quality gates to pass.

## M168 Operator Quality Status

M168 adds a compact quality status summary for Dax/TUI consumption.

Artifact:

- `artifacts/m168-quality-status/quality-status-m168-qwen-a3b.json`

Result:

- verdict: `PASS`
- quality gates: `8`
- failures: `0`
- operator summary: quality `PASS`, performance `PASS`

## M169 Expanded Coding-Agent Golden Set

M169 broadens the deterministic golden set with coding-agent-shaped prompts.

Added cases:

- `code_review`
- `edit_plan`
- `summary`

Artifacts:

- `artifacts/m169-expanded-golden-set/quality-golden-set-m169-qwen-a3b.json`
- `artifacts/m169-expanded-golden-set/deterministic-quality-m169-qwen-a3b.json`

Result:

- verdict: `PASS`
- deterministic rows: `8`
- failures: `0`
- visible thinking: `false` for every row

## M170 Model-To-Model Quality Comparison

M170 compares quality gates across the current A3B model and the smaller Qwen
27B UD MLX 4-bit candidate.

Models:

- current: `/Volumes/StudioStackSSD4TB/Development/LLM/lmstudio/models/unsloth/Qwen3.6-35B-A3B-UD-MLX-4bit`
- candidate: `/Volumes/StudioStackSSD4TB/Development/LLM/lmstudio/models/unsloth/Qwen3.6-27B-UD-MLX-4bit`

Artifact:

- `artifacts/m170-model-quality-comparison/model-quality-comparison-m170-qwen.md`

Result:

- verdict: `PASS`
- compared gates: deterministic, cache, loop, and long-context
- current model failures: `0`
- candidate model failures: `0`
- server restored to the current A3B model after comparison
- observed candidate latency was slower in this gate set, so quality passed but
  speed did not improve

Decision:

- Smaller or alternate models can be considered for speed work only after they
  pass the same quality comparison gate.
- The tested 27B dense candidate is not a current speed replacement for the
  35B-A3B MoE model based on this evidence.

## M171 Operator Quality Bundle

M171 packages live engine status, suite quality status, and model-comparison
quality into one operator/TUI-facing bundle.

Artifacts:

- `artifacts/m171-operator-quality-bundle/operator-quality-bundle-m171-qwen-a3b.json`
- `artifacts/m171-operator-quality-bundle/operator-quality-bundle-m171-qwen-a3b.md`

Result:

- verdict: `PASS`
- readiness: `operator-quality-ready`
- engine: `PASS`
- gpu: `PASS`
- warmup: `PASS`
- quality: `PASS`
- model comparison: `PASS`
- failures: `0`

Operator warning:

- The quality-compatible 27B candidate is slower than the active 35B-A3B model,
  so it should not be presented as the speed replacement.

## M172 Coding-Agent Workspace Golden Set

M172 expands the quality gate corpus with coding-agent workflow prompts.

Added cases:

- `workspace_symbol_lookup`
- `patch_plan`
- `test_selection`
- `failure_triage`

Artifacts:

- `artifacts/m172-coding-agent-golden-set/quality-golden-set-m172-qwen-a3b.json`
- `artifacts/m172-coding-agent-golden-set/deterministic-quality-m172-qwen-a3b.json`
- `artifacts/m172-coding-agent-golden-set/loop-quality-m172-qwen-a3b.json`
- `artifacts/m172-coding-agent-golden-set/quality-checkpoint-m172-qwen-a3b.md`

Result:

- verdict: `PASS`
- deterministic rows: `12`
- loop rows: `13`
- failures: `0`

Decision:

- Coding-agent quality now covers workspace lookup, edit planning, focused test
  selection, and failure triage before future speed claims can be accepted.

## M173 CI Quality Threshold Gate

M173 adds a CI-style threshold gate for quality artifacts and operator quality
bundles.

Artifact:

- `artifacts/m173-quality-threshold-gate/quality-threshold-gate-m173-qwen-a3b.json`

Result:

- verdict: `PASS`
- readiness: `ci-quality-ready`
- checks: `18`
- failures: `0`
- visible-thinking threshold: `0`
- missing-required threshold: `0`
- max repetition threshold: `0.2`

Decision:

- Future model/profile/speed changes should publish this threshold gate output
  so automation can block regressions before operator surfaces claim a speed win.

## M175 Expanded Live Product Regression Suite

M175 runs the full live product regression suite with the expanded M172
coding-agent quality gates and the M173 CI threshold gate integrated.

Artifact:

- `artifacts/m175-live-expanded-quality-suite/live-product-regression-suite-m175-qwen-a3b.json`

Result:

- verdict: `PASS`
- readiness: `live-regression-passing`
- artifacts: `24`
- failures: `0`
- deterministic quality rows: `12`
- loop quality rows: `13`
- quality threshold readiness: `ci-quality-ready`

Fix included:

- The lower-memory gate now prefers current active MLX memory from `/health`
  when a live base URL is provided. Historical MLX peak memory is still recorded
  as diagnostic data, but it no longer fails a lower-memory run after prior
  model reloads raised process-level peak memory.

## M176 Model Swap Acceptance Gate

M176 adds an acceptance gate for model/profile swaps.

Artifacts:

- `artifacts/m176-model-swap-acceptance/model-swap-acceptance-m176-qwen27b.json`
- `artifacts/m176-model-swap-acceptance/model-swap-acceptance-m176-qwen27b.md`

Result:

- gate verdict: `PASS`
- swap decision: `REJECT`
- current model: `qwen35b-a3b-ud-4bit`
- candidate model: `qwen27b-ud-4bit`
- model comparison: `PASS`
- quality threshold: `PASS`
- candidate quality: `PASS`
- candidate speed: `FAIL`
- candidate slowdown ratio: `9.968977`

Decision:

- Quality passing is necessary but not sufficient for a model swap. The 27B
  candidate remains blocked because it is materially slower than the active A3B
  model on the quality-gate comparison.

## M177 Per-Request Active Memory Metrics

M177 adds current MLX memory fields to per-request engine metrics.

Artifact:

- `artifacts/m177-request-memory-metrics/request-memory-metrics-static-probe-m177-qwen-a3b.json`

Added request metric fields:

- `active_memory_gb`
- `active_memory_bytes`
- `cache_memory_gb`
- `cache_memory_bytes`
- `mlx_peak_memory_gb`
- `peak_memory_bytes`

Result:

- static contract: `PASS`
- request metric injection points: `3`
- failures: `0`

Decision:

- Future lower-memory and operator gates can use per-request active memory
  directly after the resident server is restarted onto this commit. The `/health`
  fallback remains useful for older live server processes.

## M178 Live Per-Request Memory Metrics

M178 restarts the resident server onto M177 and proves the new memory fields are
present in live OpenAI-compatible responses.

Artifact:

- `artifacts/m178-request-memory-live/request-memory-metrics-live-probe-m178-qwen-a3b.json`

Result:

- verdict: `PASS`
- readiness: `request-memory-metrics-live`
- non-stream fields: `PASS`
- stream fields: `PASS`
- active memory observed: `20.78077057 GB`
- cache memory observed: `0.007968398 GB`
- MLX peak observed: `21.419940142 GB`

Decision:

- The running resident server now emits per-request memory metrics, so
  lower-memory gates can use request-local `active_memory_gb` instead of relying
  on process-level `/health` fallback.

## M179 Model Swap Workflow

M179 adds a one-command artifact workflow for model swap decisions.

Artifacts:

- `artifacts/m179-model-swap-workflow/model-swap-workflow-m179-qwen27b.json`
- `artifacts/m179-model-swap-workflow/model-swap-acceptance-m179-qwen27b.md`

Result:

- workflow verdict: `PASS`
- model comparison: `PASS`
- quality threshold: `PASS`
- swap decision: `REJECT`
- readiness: `swap-blocked`
- blocker: `candidate_speed`
- candidate slowdown ratio: `9.968977`

Decision:

- Model swap evaluation is now reproducible as a single artifact workflow. The
  tested 27B dense model remains rejected because it is slower despite passing
  quality gates.

## M180 Live Suite With Request-Local Memory

M180 reruns the full live product regression suite after per-request memory
metrics were proven live.

Artifacts:

- `artifacts/m180-live-request-memory-suite/live-product-regression-suite-m180-qwen-a3b.json`
- `artifacts/m180-live-request-memory-suite/lower-memory-live-gate-m180-qwen-a3b.json`
- `artifacts/m180-live-request-memory-suite/quality-threshold-gate-m180-qwen-a3b.json`

Result:

- suite verdict: `PASS`
- readiness: `live-regression-passing`
- artifacts: `24`
- failures: `0`
- lower-memory gate: `PASS`
- quality checkpoint: `PASS`
- quality threshold gate: `PASS`
- lower-memory memory source: `request_metrics`
- lower-memory max active memory: `21.02259841 GB`
- lower-memory health fallback: unused
- lower-memory max peak memory: `22.31961337 GB`

Decision:

- Lower-memory suite gating now uses request-local `active_memory_gb` when the
  live server emits it. `/health` remains a compatibility fallback, but it did
  not drive the M180 lower-memory verdict.

## M181 Live Model Swap Lifecycle Probe

M181 adds a live reload/restore probe for the resident model lifecycle.

Artifact:

- `artifacts/m181-live-model-swap/live-model-swap-m181-qwen-a3b.json`

Result:

- verdict: `PASS`
- readiness: `live-model-swap-safe`
- failures: `0`
- candidate reload elapsed: `12524.02 ms`
- restore reload elapsed: `8440.3 ms`
- candidate device: `Device(gpu, 0)`
- restore device: `Device(gpu, 0)`
- candidate active memory: `20.78082 GB`
- restore active memory: `20.780771 GB`

Decision:

- The resident engine can reload a model path, serve a completion with
  request-local memory metrics, then reload back to the original model path and
  serve again. M181 used a same-model candidate to prove lifecycle safety without
  changing the active model decision from M179/M180.

## M182 Operator Readiness Bundle

M182 packages current runtime, quality, lower-memory, and model-swap evidence
into one operator-facing artifact.

Artifacts:

- `artifacts/m182-operator-readiness/operator-readiness-bundle-m182-qwen-a3b.json`
- `artifacts/m182-operator-readiness/operator-readiness-bundle-m182-qwen-a3b.md`

Result:

- verdict: `PASS`
- readiness: `operator-readiness-ready`
- failures: `0`
- warnings: `1`
- runtime: `PASS`
- quality: `PASS`
- live suite: `PASS`
- lower-memory: `PASS`
- memory source: `request_metrics`
- live model swap: `PASS`
- candidate swap: `WARN`

Decision:

- The operator-facing status can now show the active model is ready while the
  tested 27B dense candidate remains blocked by speed. This is a warning, not a
  runtime failure, because the active A3B model remains the accepted model.

## M183 Operator Readiness UI Contract

M183 makes the M182 readiness bundle a stable UI/TUI contract.

Artifacts:

- `docs/mac-local-inference-platform/operator-readiness-ui-contract.md`
- `artifacts/m183-operator-readiness-contract/operator-readiness-contract-m183-qwen-a3b.json`

Result:

- contract probe: `PASS`
- readiness: `operator-readiness-contract-ready`
- failures: `0`

Decision:

- Dax, Prowl, or future operator surfaces should consume the M182 readiness
  bundle as the primary readiness source and use `/engine/ui` for live controls.
  `candidate_swap=WARN` is displayable as a non-blocking warning when the active
  model remains ready.

## M184 Operator Readiness Renderer

M184 adds a reusable renderer for the operator readiness bundle.

Artifacts:

- `benchmarks/python/operator_readiness_render.py`
- `artifacts/m184-operator-readiness-render/operator-readiness-render-m184-qwen-a3b.json`
- `artifacts/m184-operator-readiness-render/operator-readiness-render-m184-qwen-a3b.txt`

Result:

- render verdict: `PASS`
- active model: `Qwen3.6-35B-A3B-UD-MLX-4bit`
- candidate model: `Qwen3.6-27B-UD-MLX-4bit`
- swap decision: `REJECT`
- status line includes runtime, quality, live suite, lower-memory,
  request-metrics memory source, live model swap, and candidate-swap warning.

Decision:

- Dax/Prowl/TUI clients can reuse the renderer output for compact status cards
  instead of reimplementing readiness formatting. The JSON renderer artifact is
  the stable bridge for richer UI presentation.

## M185 Packaged Operator Readiness CLI

M185 exposes the M184 readiness renderer through `bin/mlx-engine`.

Artifacts:

- `artifacts/m185-cli-operator-readiness/operator-readiness-cli-m185-qwen-a3b.json`
- `artifacts/m185-cli-operator-readiness/operator-readiness-cli-m185-qwen-a3b.txt`

Command:

- `bin/mlx-engine operator-readiness`

Result:

- CLI render verdict: `PASS`
- active model: `Qwen3.6-35B-A3B-UD-MLX-4bit`
- candidate model: `Qwen3.6-27B-UD-MLX-4bit`
- swap decision: `REJECT`
- status line matches the M184 shared renderer output.

Decision:

- External clients no longer need to know the internal benchmark script path.
  Dax, Prowl, shell scripts, or packaged operator surfaces can call
  `bin/mlx-engine operator-readiness` as the stable entry point.

## M186 Live Operator Readiness Endpoint

M186 adds a live HTTP endpoint for operator readiness:

- `GET /engine/operator-readiness`

Result:

- endpoint type: `operator_readiness_live_status`
- live verdict: `PASS`
- readiness: `operator-live-ready`
- runtime: `PASS`
- GPU: `PASS`
- warm: `PASS`
- can generate: `PASS`
- live controls: `PASS`
- memory source: `engine_ui`

Decision:

- Prowl, Dax, and UI clients can read current runtime readiness without shelling
  out. The endpoint reports live state only; artifact-backed release readiness
  remains covered by the M182/M185 bundle path.

## M187 Operator Readiness Endpoint Probe

M187 validates the new live readiness endpoint.

Artifact:

- `artifacts/m187-operator-readiness-endpoint/operator-readiness-endpoint-m187-qwen-a3b.json`

Result:

- probe verdict: `PASS`
- readiness: `operator-readiness-endpoint-ready`
- failures: `0`
- active model: `Qwen3.6-35B-A3B-UD-MLX-4bit`
- engine preset: `async-experimental`
- GPU ready: `true`

Decision:

- The live endpoint has a contract probe and is safe for UI/Prowl consumers to
  smoke-test against a running resident engine.

## M188 Packaged Operator Readiness Refresh

M188 exposes readiness bundle regeneration through the packaged CLI:

- `bin/mlx-engine operator-readiness-refresh`

Artifacts:

- `artifacts/m188-operator-readiness-refresh/operator-readiness-refresh-m188-qwen-a3b.json`
- `artifacts/m188-operator-readiness-refresh/operator-readiness-refresh-m188-qwen-a3b.md`

Result:

- refresh verdict: `PASS`
- readiness: `operator-readiness-ready`
- failures: `0`
- warnings: `1`
- candidate swap: `WARN`

Decision:

- Operators can now refresh the artifact-backed readiness bundle with one
  packaged command instead of invoking the lower-level benchmark script.

## M189 Model Candidate Registry

M189 creates an explicit registry for active and tested MLX model candidates.

Artifact:

- `artifacts/m189-model-candidate-registry/model-candidate-registry-m189-qwen.json`

Result:

- verdict: `PASS`
- readiness: `model-candidate-registry-ready`
- candidates: `2`
- failures: `0`

Decision:

- Operator surfaces and future model-swap automation can read active and tested
  candidates from one registry instead of inferring them from comparison
  artifacts.

## M190 Lower-Memory Candidate Gate

M190 gates lower-memory candidate readiness from the model registry and
request-metric lower-memory evidence.

Artifact:

- `artifacts/m190-lower-memory-candidate/lower-memory-candidate-gate-m190-qwen.json`

Result:

- verdict: `PASS`
- readiness: `lower-memory-candidate-gated`
- max active memory: `21.02259841 GB`
- threshold: `24 GB`
- failures: `0`
- warnings: `1`

Decision:

- The active A3B model remains acceptable for the current lower-memory target.
  The tested 27B alternate remains visible but not promotable because the swap
  decision is still `REJECT`.

## M191 Operator UI Field Map

M191 defines the fields UI/Prowl/TUI consumers should display from the readiness
bundle, renderer, and live endpoint.

Artifact:

- `artifacts/m191-operator-ui-field-map/operator-ui-field-map-m191.json`

Result:

- verdict: `PASS`
- readiness: `operator-ui-field-map-ready`
- fields: `11`
- failures: `0`

Decision:

- UI consumers now have a field-level map for readiness headers, badges, runtime
  details, memory, warnings, and failures.

## M192 Prompt-Processing Next Target Gate

M192 reopens the prompt-processing performance lane with a quality-protected
next target.

Artifact:

- `artifacts/m192-prompt-processing-next-target/prompt-processing-next-target-m192-qwen-a3b.json`

Result:

- verdict: `PASS`
- readiness: `prompt-processing-next-target-ready`
- baseline service request: `1411.08045889996 ms`
- mature reusable-turn service request: `204.03116615489125 ms`
- speedup: `6.91600447859388x`
- quality threshold: `PASS`
- failures: `0`
- warnings: `1`

Decision:

- The next speed target is to reduce mature reusable-turn latency toward
  `175 ms` while preserving quality threshold `PASS` and at least `4x` speedup.

## M193 Milestone Completion Audit

M193 audits the M186-M193 batch against concrete artifacts.

Artifact:

- `artifacts/m193-completion-audit/milestone-completion-audit-m193-m186-m193.json`

Result:

- audit verdict: `PASS`
- readiness: `milestone-batch-complete`
- audited artifacts: `6`
- failures: `0`

Decision:

- The M186-M193 milestone batch is complete from the repo artifact perspective.

## M194-M201 Performance Report Batch

M194-M201 add a performance-reporting lane around the current prompt-processing
baseline and the next latency target.

Artifacts:

- `artifacts/m194-performance-report/prompt-processing-performance-report-m194-qwen-a3b.json`
- `artifacts/m195-optimization-matrix/prompt-processing-optimization-matrix-m195-qwen-a3b.json`
- `artifacts/m196-performance-budget/performance-budget-gate-m196-qwen-a3b.json`
- `artifacts/m197-live-performance-snapshot/live-performance-snapshot-m197-qwen-a3b.json`
- `artifacts/m198-performance-report-contract/performance-report-contract-m198-qwen-a3b.json`
- `artifacts/m199-performance-report-render/performance-report-render-m199-qwen-a3b.json`
- `artifacts/m200-next-milestones/next-milestone-plan-m200.json`
- `artifacts/m201-performance-batch-report/performance-batch-report-m201.json`
- `artifacts/m201-performance-batch-report/milestone-completion-audit-m201-m194-m201.json`

Result:

- performance report: `PASS`
- optimization matrix: `PASS`
- budget gate: `PASS`
- live performance snapshot: `PASS`
- report contract: `PASS`
- report renderer: `PASS`
- next milestone plan: `PASS`
- batch report: `PASS`
- completion audit: `PASS`
- audited artifacts: `8`
- failures: `0`

Performance summary:

- baseline service request: `1411.08045889996 ms`
- mature reusable-turn service request: `204.03116615489125 ms`
- speedup vs baseline: `6.91600447859388x`
- max active memory: `21.02259841 GB`
- quality threshold: `PASS`
- next mature-hit target: `175 ms`
- required reduction: `29.031 ms`
- required reduction percent: `14.229%`

Decision:

- The next implementation lane should target mature reusable-turn latency
  reduction while preserving the existing quality threshold and at least `4x`
  speedup versus baseline.

## M202 Cache Lookup Fast Path

M202 moves exact repeated-prompt detection into a lightweight prefix-cache helper
module and adds an exact token-hash index to avoid scanning recent prompt
candidates on mature exact hits.

Artifacts:

- `benchmarks/python/cache_lookup_fast_path_probe.py`
- `artifacts/m202-cache-lookup-fast-path/cache-lookup-fast-path-m202-qwen-a3b.json`
- `artifacts/m202-cache-lookup-fast-path/next-milestones-after-m202.json`
- `artifacts/m202-cache-lookup-fast-path/milestone-completion-audit-m202.json`

Result:

- verdict: `PASS`
- readiness: `cache-lookup-fast-path-ready`
- exact repeated prompt fast path: `true`
- exact scan candidates: `0`
- near-match scan behavior preserved: `true`
- completion audit: `PASS`
- quality threshold baseline: `PASS`

Decision:

- Exact repeated prompts now skip redundant prefix-candidate scans before cache
  reuse.
- Non-exact prefix matches still use the existing scan path, preserving route and
  cache-scope safety.

## M203 Tokenized Prompt Reuse

M203 adds a bounded tokenized-prompt cache for identical repeated workspace
prompts. The cache is keyed by normalized prompt plus tokenizer scope, not by
route-level request metadata.

Artifacts:

- `benchmarks/python/tokenized_prompt_reuse_probe.py`
- `artifacts/m203-tokenized-prompt-reuse/tokenized-prompt-reuse-m203-qwen-a3b.json`
- `artifacts/m203-tokenized-prompt-reuse/next-milestones-after-m203.json`
- `artifacts/m203-tokenized-prompt-reuse/milestone-completion-audit-m203.json`

Result:

- verdict: `PASS`
- readiness: `tokenized-prompt-reuse-ready`
- identical prompt cache hit: `true`
- token list copy safety: `true`
- tokenizer-scope separation: `true`
- completion audit: `PASS`

Decision:

- Repeated workspace prompts can now reuse token IDs before prefix lookup.
- Cache scope includes model, backend, tokenizer class, and chat template hash to
  avoid unsafe reuse across tokenizer/template changes.

## M204 Async Cache Completion Wait

M204 turns the prior async maturation sweep into an explicit runtime
recommendation for duplicate requests that arrive while an async prefix build is
already pending.

Artifacts:

- `benchmarks/python/async_cache_completion_wait_report.py`
- `artifacts/m204-async-cache-completion-wait/async-cache-completion-wait-m204-qwen-a3b.json`
- `artifacts/m204-async-cache-completion-wait/next-milestones-after-m204.json`
- `artifacts/m204-async-cache-completion-wait/milestone-completion-audit-m204.json`

Result:

- verdict: `PASS`
- readiness: `async-cache-completion-wait-ready`
- recommended pending wait: `1000 ms`
- observed pending wait: `801.0062498506159 ms`
- wait-hit actual prefill tokens: `10`
- source async maturation gate: `PASS`

Decision:

- Keep pending waits bounded and conditional on an already-pending async build.
- Do not use pending waits as a general foreground delay mechanism.
