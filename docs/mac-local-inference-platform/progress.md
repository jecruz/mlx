# Progress

- Added an isolated benchmark worktree at `.worktrees/prompt-processing-bench`.
- Added `benchmarks/python/vlm_prompt_decode_bench.py` to measure load time, prompt processing, and first-token generation timing.
- Verified the 35B A3B checkpoint runs through the benchmark harness successfully.
- Recorded the current baseline result for the minimal prompt `Hi` so the next iteration can compare against it.
- Attempted a longer prompt on the same checkpoint; it remained prompt-bound long enough that the run was stopped, confirming the prompt phase is still the main bottleneck for this test shape.
- Added explicit runtime device reporting to the benchmark harness.
- Ran fixed-length prompt sweeps on the text-only `gpt-oss-20b` checkpoint with the repo-local path:
  - 8 tokens completed successfully
  - 16 tokens completed successfully
- Ran a 32-token fixed-length prompt sweep successfully on the same checkpoint, which gives a better view of the prompt scaling curve.
- Ran a 64-token fixed-length prompt sweep successfully on the same checkpoint, giving a third scaling point and confirming prompt throughput remains in the same low band.
- Confirmed the sandbox runtime is CPU-only for the repo-local path, which explains the long prompt times.
- Tried to rebuild a GPU-capable local MLX extension, but the build is blocked by the Metal toolchain state in this environment.
- Ran a checkpoint integrity check for `gpt-oss-20b-MXFP4-Q8` and confirmed shard completeness plus loader/model-type alignment.
- Added a `--require-gpu` guard to prevent accidental long CPU fallback runs when collecting Metal numbers.
- Added JSON result output to make sweep comparison scriptable.
- Added `benchmarks/python/run_prompt_sweep.sh` for one-command 8/16/32/64 token sweeps in a Metal-capable shell.
- Ran the first Metal-backed `gpt-oss-20b-MXFP4-Q8` prompt sweep from the tmux pane and confirmed GPU execution.
- Fixed the text-backend benchmark path so it no longer passes VLM-only `temperature` into `mlx_lm.generate_step`.
- Added `benchmarks/python/summarize_prompt_sweep.py` for JSONL result summaries and GPU/CPU validity verdicts.
- Added `benchmarks/python/inprocess_prompt_sweep.py` to load the model once, warm up once, and measure steady-state prompt processing without repeated load/compile noise.
- Ran the in-process steady-state sweep through 512 prompt tokens, producing `gpu-prompt-sweep-steady.jsonl`.
- Current meaningful result: warmed Metal prompt processing reaches about `1.7-1.8k tok/s` at 512 prompt tokens on `gpt-oss-20b-MXFP4-Q8`, so the earlier apparent prompt slowness was mostly cold-start and measurement-shape noise.
- Ran a long-context in-process sweep through 4096 prompt tokens, producing `gpu-prompt-sweep-long.jsonl`.
- Current long-context result: warmed Metal prompt processing stays around `1.7k-2.1k tok/s` from 512 through 4096 tokens, with the 4096-token point completing in `2158.82 ms`.
- Ran a 4096-token `prefill_step_size` sweep for 512, 1024, 2048, and 4096.
- Current chunking result: `prefill_step_size=2048` is fastest at `2082.167 tok/s`, while `512` uses the least peak memory at `12.652 GB`.
- Added `benchmarks/python/prefill_profile.py` to convert benchmark JSONL files into an engine-consumable prefill policy profile.
- Generated `gpt-oss-20b-MXFP4-Q8-prefill-profile.json` from the measured candidate chunk-size files.
- Current profile result: use `prefill_step_size=2048` for throughput/default behavior and `512` for memory-saver behavior.
- Added `benchmarks/python/resident_mlx_service.py` plus `run_resident_service.sh` for a resident localhost MLX service.
- Verified `/health`, `/profile`, and `/generate` against the resident service on `127.0.0.1:8765`.
- Fixed service text accumulation so `/generate` returns the full streamed response text rather than only the final detokenizer segment.
- Added `policy=auto` to select `memory_saver` for prompts below 512 estimated tokens and `throughput_default` for longer prompts.
- Restarted the resident service and verified `policy=auto` chooses `prefill_step_size=512` for a 110-token request.
- Added `benchmarks/python/qwen_imrope_static_probe.py` to compare MLX Qwen3.6 IMROPE lane ownership against the puma.cpp/panthro.cpp IMROPE sector rule.
- Ran the Qwen3.6 IMROPE parity probe in a Metal-capable tmux shell and wrote `qwen3_6-imrope-parity-report.json`.
- Current correctness result: both tested Qwen3.6 MLX checkpoints, dense 27B and 35B-A3B MoE, match the puma/panthro IMROPE lane rule with zero mismatches.
- Added `docs/mac-local-inference-platform/qwen-imrope-parity.md` and `docs/mac-local-inference-platform/inference-correctness-risks.md` as M1 correctness evidence.
- Productionized the resident service API surface for the first M4 slice:
  - profile auto-discovery
  - `/metrics`
  - request IDs and effective policy reporting
  - OpenAI-style `/v1/completions`
  - OpenAI-style `/v1/chat/completions`
  - repeatable smoke client
- Fixed the launcher so `run_resident_service.sh "$MODEL" 8765` works without an explicit profile argument.
- Restarted the service without `--profile`; it discovered `gpt-oss-20b-MXFP4-Q8-prefill-profile.json` from the worktree and stayed on `Device(gpu, 0)`.
- Smoke-tested health, raw generate, completions, chat completions, and metrics against the resident service on `127.0.0.1:8765`.
- Added streaming support:
  - `/generate` streams newline-delimited JSON when `stream=true`
  - `/v1/completions` streams OpenAI-style SSE when `stream=true`
  - `/v1/chat/completions` streams OpenAI-style SSE when `stream=true`
- Extended the smoke client to validate streaming completion and chat responses; both emitted data events and `[DONE]`.
- Added `EngineManager` lifecycle control around the resident engine.
- Added `/engine` to report loaded model, profile state, policy names, warm-up state, reload count, and metrics.
- Added `/engine/reload` to load a replacement resident engine and swap it in after the old engine is idle.
- Extended the smoke client to validate lifecycle metadata and same-model reload.
- Validated lifecycle reload on the GPU-backed service: reload count advanced to `1`, device stayed `Device(gpu, 0)`, profile remained loaded, and warm-up tokens changed to `[64]`.
- Added packaged CLI wrapper `bin/mlx-engine` with `serve`, `smoke`, and `correctness` subcommands.
- Validated `bin/mlx-engine smoke` and `bin/mlx-engine correctness` against the running GPU resident service.
- Current packaged CLI result: smoke passed raw generation, OpenAI completion, OpenAI chat, streaming completion/chat, metrics, and reload; correctness passed with `Device(gpu, 0)`, profile loaded, `2` total correctness requests, and `0` failures.
- Created M5 hardening milestone evidence.
- Added `/engine/unload` plus unloaded-state handling; smoke now validates unload followed by reload.
- Added launchd template at `packaging/launchd/com.jecruz.mlx-engine.plist.template`.
- Added `benchmarks/python/vlm_processor_static_probe.py` and generated `qwen3_6-vlm-processor-static-report.json`.
- Static VLM processor probe passed for both Qwen3.6 dense 27B and Qwen3.6 35B-A3B MoE MLX checkpoints.
- Added `docs/mac-local-inference-platform/github-mlx-project-research.md` with a public GitHub research pass covering MLX projects worth studying for resident-engine, caching, VLM, native Swift, packaging, and speculative-decoding ideas.
- Attempted to launch Claude Code from tmux pane `codex-gpt5_5-panthro_cpp:2.1` for a public-only MLX GitHub research pass. `--bare` could not use the existing login, and the authenticated retry stalled with no output, so it was interrupted. The durable research artifact is the web-sourced research note.
- Added `docs/mac-local-inference-platform/verified-mlx-research-results.md` to reconcile web-verified MLX project research against agent-generated results.
- Started M6 prefix-cache instrumentation:
  - added `PrefixOpportunityTracker` to `benchmarks/python/resident_mlx_service.py`
  - added rendered prompt hash and tokenized prompt hash fields
  - added longest common prefix token detection against recent requests
  - added prefix reuse ratio, estimated recompute tokens, and cache-candidate verdicts
  - added aggregate prefix metrics to `/metrics`
  - extended `benchmarks/python/smoke_resident_service.py` with two related prompts to validate shared-prefix detection
- Validation status: `python3 -m py_compile benchmarks/python/resident_mlx_service.py benchmarks/python/smoke_resident_service.py` passed. Full GPU service smoke is blocked from this Codex process because `/Volumes/StudioStackSSD4TB/.../gpt-oss-20b-MXFP4-Q8/config.json` returns `Operation not permitted`, and importing MLX directly in the sandbox crashes while initializing the Metal device.
- User ran the updated smoke test from a GPU-capable shell and M6 validation passed:
  - health stayed on `Device(gpu, 0)`
  - generated/completion/chat/streaming checks passed
  - prefix probe reported `prefix False 38 0.95 True`
  - `/metrics` reported `7` total successful requests and `2` cache-candidate requests
  - unload/reload still worked and reload stayed on `Device(gpu, 0)`
- Added `benchmarks/python/prefix_opportunity_sweep.py` and ran a realistic agent-style repeated-prefix sweep against the live GPU service from a trusted terminal pane.
- Prefix sweep result: `6` requests, `5` cache candidates, `970` total matched prefix tokens, mean prefix match `161.67` tokens. After the first cold request, every related request matched `194` prefix tokens with reuse ratios from `0.937` to `0.951`.
- Prefix sweep artifact: `prefix-opportunity-sweep.jsonl`.
- Started the conservative real prefix-cache reuse prototype:
  - added an in-memory LRU `PrefixKVCacheStore`
  - precomputes matched-prefix `mlx-lm` prompt caches with `generate_step(..., max_tokens=0)`
  - deep-copies cached prefix state for the current request
  - runs generation on only the uncached suffix tokens when a safe shorter-prefix match exists
  - reports `cache_reuse_enabled`, `cache_hit`, `cache_created`, `cached_prefix_tokens`, and `actual_prefill_tokens`
  - exposes `prefix_kv_cache` state in `/health` and `/engine`
- Extended smoke and prefix-sweep output to print real cache-reuse fields, not just prefix-opportunity fields.
- Validation status: `python3 -m py_compile benchmarks/python/resident_mlx_service.py benchmarks/python/smoke_resident_service.py benchmarks/python/prefix_opportunity_sweep.py` passed.
- Live GPU validation status: blocked from Codex-launched tmux commands by macOS permissions on `/Volumes/StudioStackSSD4TB/.../config.json`. The old user-launched service had model access, but the patched service must be restarted from a Terminal process with the required volume permission.
- Dedicated tmux session routing:
  - `codex-mlx-server` is reserved for the resident service.
  - `codex-mlx-testing` is reserved for smoke/sweep/client validation.
- Confirmed both dedicated tmux contexts can see the model config metadata but cannot open the file contents; even `wc -c` returns `Operation not permitted`.
- Added model-access preflight checks to `resident_mlx_service.py` and `run_resident_service.sh`; the server launcher now exits `77` with a clear unreadable-model-volume message instead of a deep Python stack trace.
- User reran validation from a permitted terminal context and confirmed the
  conservative prefix-cache reuse prototype works on GPU:
  - health stayed on `Device(gpu, 0)`
  - smoke passed raw generation, OpenAI completion, chat, streaming completion,
    streaming chat, unload, and reload
  - smoke prefix probe reported `prefix False 38 0.95 True True False True 38 2`
  - prefix sweep request 1 did full prefill: `206` actual prefill tokens
  - prefix sweep request 2 created the reusable prefix cache:
    `cache_reuse_enabled=True`, `cache_created=True`, `actual_prefill_tokens=11`
  - prefix sweep requests 3-6 hit the cache:
    `cache_hit=True`, `actual_prefill_tokens=11,12,13,10`
  - summary stayed `6` requests, `5` cache candidates, mean reuse `0.787`
- Current M7 result: repeated coding-agent prompts with ~194 shared prefix tokens
  now avoid recomputing that prefix after the cache is created, reducing actual
  prefill work to only the suffix tokens on cache-hit requests.
- Added `benchmarks/python/prefix_latency_sweep.py` for the next validation
  slice: compare full-prefill, cache-create, and cache-hit request latency using
  grouped repeated-prefix prompts.
- Latency sweep compile validation passed.
- Retried after a tmux server reboot with sessions recreated at `2026-05-13
  01:05:15`; `codex-mlx-server` still cannot open the external-volume model
  config.
- Process ancestry check: the `codex-mlx-server` pane shell is child of the
  detached tmux server `/opt/homebrew/bin/tmux` whose parent is launchd
  (`PPID=1`). This indicates the permission that matters is the detached tmux
  server context, not only the attached Terminal window.
- Retried with new panes split from `codex-gpt5_5-panthro_cpp`:
  - server pane: `codex-gpt5_5-panthro_cpp:1.2`
  - testing pane: `codex-gpt5_5-panthro_cpp:1.3`
  - server started successfully on `127.0.0.1:8765`
  - smoke, prefix opportunity sweep, and prefix latency sweep all completed
- Added service-side timing instrumentation:
  - `cache_prepare_ms`
  - `service_request_ms`
- Latest prefix opportunity result with timing:
  - request 2 cache creation prepared the `194` token prefix in `147.96 ms`
  - requests 3-6 were cache hits with `cache_prepare_ms=0.11 ms`
- Latest latency sweep result:
  - `full_prefill`: `3` requests, mean `run_ms=600.45`, mean
    `service_request_ms=601.77`, mean actual prefill `929.67`
  - `cache_create`: `3` requests, mean `cache_prepare_ms=443.81`, mean
    `run_ms=186.16`, mean `service_request_ms=631.28`, mean actual prefill `10`
  - `cache_hit`: `12` requests, mean `cache_prepare_ms=0.16`, mean
    `run_ms=197.99`, mean `service_request_ms=199.53`, mean actual prefill `9.5`
- Current performance conclusion: cache hits reduce service-side request time
  from about `602 ms` to about `200 ms` on ~930-token prompts with repeated
  prefixes, roughly a `3x` improvement after the cache is built.
- Added `--skip-lifecycle` to `benchmarks/python/smoke_resident_service.py` so
  smoke validation can be chained before benchmark sweeps without unloading the
  resident service.
- Safe validation chain now leaves the service alive:
  - `smoke_resident_service.py --skip-lifecycle`
  - `prefix_opportunity_sweep.py`
  - `prefix_latency_sweep.py`
- Fixed `prefix_opportunity_sweep.py` to insert a unique run id at the first
  prompt line. This prevents repeated runs in the same resident process from
  matching entire old prompts and hiding the shorter-prefix cache path.
- Corrected opportunity-sweep behavior after the run-id fix:
  - request 1: `220` tokens, `1` prefix token, no cache candidate
  - request 2: `219` tokens, `208` matched prefix tokens, cache created,
    `actual_prefill_tokens=11`
  - requests 3-6: cache hits with `actual_prefill_tokens=11,12,13,10`
- Added scoped prefix-cache keys:
  - model path
  - profile path
  - backend
  - effective policy
  - prefill step size
  - tokenizer class
  - chat-template hash
- Extended real prefix-cache reuse to streaming paths:
  - `/generate` with `stream=true`
  - `/v1/completions` with `stream=true`
  - `/v1/chat/completions` with `stream=true`
- Extended smoke validation to parse final SSE events and assert streaming
  prefix-cache reuse.
- Streaming smoke evidence: `stream_prefix 64 0.955 True True False True
  96.28 64 3`, proving streaming cache creation and suffix-only prefill.
- Final M7 opportunity sweep evidence:
  - request 1: `221` tokens, `1` matched token, no cache candidate
  - request 2: `220` tokens, `209` matched prefix tokens, cache created,
    `actual_prefill_tokens=11`
  - requests 3-6: cache hits with `actual_prefill_tokens=11,12,13,10`
- Final M7 latency evidence:
  - `full_prefill`: mean `service_request_ms=600.18`, mean actual prefill
    `930.67`
  - `cache_create`: mean `service_request_ms=631.11`, mean
    `cache_prepare_ms=446.22`, mean actual prefill `10`
  - `cache_hit`: mean `service_request_ms=183.63`, mean
    `cache_prepare_ms=0.17`, mean actual prefill `9.5`
- M7 completion result: cache-hit requests are now about `3.27x` faster than
  full-prefill requests for the measured ~930-token repeated-prefix workload,
  non-streaming and streaming paths both reuse prefix caches, cache keys are
  scoped to compatibility metadata, and safe chained validation leaves the
  resident service alive.
- Started M8 scheduler and multi-request serving work.
- Added bounded scheduler/admission control to the resident engine:
  - default `max_concurrent_requests=1`
  - default `max_queued_requests=16`
  - default `queue_timeout_ms=30000`
  - exposed via CLI args and `run_resident_service.sh` environment variables
  - exposed scheduler snapshot in `/health` and `/engine`
  - records `scheduler_queue_wait_ms`,
    `scheduler_active_requests_at_admit`, and
    `scheduler_queued_requests_at_admit` per request
- Added `benchmarks/python/scheduler_admission_probe.py` to create concurrent
  client pressure and validate queue metrics.
- M8 scheduler probe evidence with three concurrent clients:
  - request 1: queue wait `0.0 ms`
  - request 2: queue wait `403.45 ms`
  - request 3: queue wait `648.21 ms`
  - scheduler after probe: `total_admitted=3`, `total_completed=3`,
    `total_rejected=0`, mean queue wait `350.55 ms`
- Safe smoke still passes after scheduler admission control, including streaming
  prefix reuse.
- Added streaming latency metrics:
  - `stream_first_token_ms`
  - `stream_mean_token_gap_ms`
  - `stream_token_events`
- Streaming smoke evidence after metrics addition:
  - `stream_prefix 62 0.954 True True False True 93.01 62 3 100.76 7.55`
  - first token latency `100.76 ms`
  - mean streamed token gap `7.55 ms`
- Extended `scheduler_admission_probe.py` to report scheduler 503 rejections
  instead of failing the whole probe.
- Rejection-path validation with `MAX_QUEUED_REQUESTS=1` and
  `QUEUE_TIMEOUT_MS=50`:
  - one request admitted
  - three requests rejected
  - rejection details included `resident engine queue is full` and
    `resident engine queue wait timed out`
  - scheduler after probe: `total_admitted=1`, `total_completed=1`,
    `total_rejected=3`
- Restored the resident service to normal scheduler defaults after rejection
  validation.
- Added `docs/mac-local-inference-platform/native-overlap-audit.md` comparing
  MLX native C++/Metal/GGUF/RoPE/cache/scheduler domains against
  `llama.cpp`, `puma.cpp`, and `panthro.cpp`.
- Ran larger-context M8 prefix-cache sweeps:
  - ~2k prompt shape: full prefill `2783.02 ms` service request, cache hit
    `186.41 ms`, actual prefill `10` tokens, about `14.9x` cache-hit speedup
  - ~4k prompt shape: full prefill `2021.29 ms`, cache hit `248.66 ms`, actual
    prefill `10` tokens, about `8.1x` cache-hit speedup
  - ~7.4k prompt shape: full prefill `3718.98 ms`, cache hit `211.4 ms`, actual
    prefill `10` tokens, about `17.6x` cache-hit speedup
- M8 milestone result: scheduler/admission control, streaming latency metrics,
  rejection handling, larger-context cache-hit sweeps, and native-overlap audit
  are now complete. Remaining work moves to M9 optimization experiments:
  fused kernels, memory pressure/eviction, and safe batching/concurrency.
- Added the native overlap audit to M8 planning. The goal is to compare MLX
  C++/Metal/GGUF/RoPE/attention/quantization/cache/scheduler areas against
  `llama.cpp`, `puma.cpp`, and `panthro.cpp` so prior fixes and performance
  enhancements can guide MLX optimization without blindly porting incompatible
  code.
- Started M9 optimization observability.
- Added prefix-cache eviction telemetry:
  - `PrefixKVCacheStore` now tracks cumulative `evictions`.
  - `/health` and `/engine` expose `prefix_kv_cache.entries`,
    `prefix_kv_cache.max_entries`, `prefix_kv_cache.evictions`, and retained
    cache-key metadata.
  - `run_resident_service.sh` accepts `PREFIX_CACHE_MAX_ENTRIES`.
  - `resident_mlx_service.py` accepts `--prefix-cache-max-entries`.
- Added MLX memory telemetry to `/health` and `/engine`:
  - `active_memory_bytes`
  - `cache_memory_bytes`
  - `peak_memory_bytes`
- Added engine lock-wait telemetry:
  - per-request `engine_lock_wait_ms`
  - scheduler probe output now includes engine lock wait
- Ran a controlled `MAX_CONCURRENT_REQUESTS=2` experiment. The scheduler admits
  two active requests, but model execution is still serialized by the engine
  lock:
  - request 2: active-at-admit `1`, engine lock wait `0.0 ms`
  - request 1: active-at-admit `2`, engine lock wait `555.12 ms`
  - request 3: queue wait `516.11 ms`, engine lock wait `213.01 ms`
- M9 concurrency conclusion: increasing `max_concurrent_requests` above `1`
  does not create true parallel MLX model execution yet. It moves some waiting
  from scheduler queue time into engine-lock time, so the safe default remains
  `1` until the runtime has a real concurrent execution or batching design.
- Validated prefix-cache eviction with `PREFIX_CACHE_MAX_ENTRIES=2` and four
  repeated-prefix cache groups:
  - `prefix_kv_cache.entries=2`
  - `prefix_kv_cache.max_entries=2`
  - `prefix_kv_cache.evictions=2`
  - MLX memory snapshot after the run:
    `active_memory_bytes=12135785624`,
    `cache_memory_bytes=32158024`,
    `peak_memory_bytes=12898081034`
- M9 eviction sweep result:
  - `full_prefill`: mean service request `659.16 ms`, mean actual prefill
    `929.25` tokens
  - `cache_create`: mean service request `597.75 ms`, mean cache prepare
    `443.93 ms`, mean actual prefill `10` tokens
  - `cache_hit`: mean service request `157.83 ms`, mean cache prepare
    `0.19 ms`, mean actual prefill `11` tokens
- Current M9 milestone result: observability for cache eviction, MLX memory,
  scheduler queueing, and engine lock contention is in place and validated.
  The next M9 slice should use those signals to implement memory-pressure
  policy and decide whether to pursue batching, async prefill-cache creation,
  or lower-level Metal kernel work first.
- Implemented M9 memory-pressure policy:
  - `PREFIX_CACHE_MEMORY_LIMIT_MB` / `--prefix-cache-memory-limit-mb`
  - `PREFIX_CACHE_MIN_ENTRIES` / `--prefix-cache-min-entries`
  - `prefix_cache_policy` in `/health` and `/engine`
  - per-request `memory_prune_applied` and
    `memory_prune_removed_entries`
  - `/engine/cache/prune` manual recovery/testing endpoint
  - cache store `prunes` counter
- Added `benchmarks/python/memory_pressure_probe.py` for repeatable validation.
- Validated forced memory pressure with `PREFIX_CACHE_MEMORY_LIMIT_MB=1` and
  `PREFIX_CACHE_MIN_ENTRIES=0`:
  - first request had no cache candidate and no prune
  - second request matched `65` prefix tokens, created a prefix cache, then
    applied memory pruning
  - probe output: `memory_probe 2 65 True False True True 1 236.11`
  - health after requests: `entries=0`, `evictions=1`, `prunes=1`
  - MLX cache memory changed from `3577334` bytes before prune to `0` bytes
    after prune
  - manual prune endpoint returned `before_entries=0`, `after_entries=0`,
    `removed_entries=0`, confirming it is safe when already empty
- Restored the resident service to normal defaults after the forced
  memory-pressure test.
- Implemented async prefix-cache population:
  - `PREFIX_CACHE_POPULATION_MODE` / `--prefix-cache-population-mode`
  - supported modes: `sync`, `async`, `off`
  - async mode schedules a background cache build on cache-candidate miss and
    lets the current request fall back to full prompt processing
  - cache policy now reports pending, started, completed, failed async builds,
    and the last async error
  - per-request metrics now include `cache_population_mode`,
    `cache_scheduled`, and `cache_pending`
- Added `benchmarks/python/async_prefix_cache_probe.py`.
- Validated async prefix-cache population with
  `PREFIX_CACHE_POPULATION_MODE=async`:
  - request 1: no prefix candidate, full prompt path
  - request 2: matched `52` prefix tokens, scheduled background cache build,
    did not pay synchronous cache-create cost, `cache_prepare_ms=0.13 ms`,
    service request `206.95 ms`
  - async wait: pending `0`, started `1`, completed `1`, failed `0`, cache
    entries `1`
  - request 3: cache hit, `cache_prepare_ms=0.15 ms`, service request
    `141.43 ms`, actual prefill `2` tokens
- Restored the resident service to default sync cache-population mode after the
  async validation run.
- Extended `prefix_latency_sweep.py` to classify and summarize
  `cache_scheduled` requests separately from `full_prefill`, `cache_create`,
  and `cache_hit`.
- Ran async-vs-sync latency exploration and found an important scheduling
  issue:
  - first async sweep showed request 3 could block on background cache creation,
    producing `cache_prepare_ms` around `444-450 ms`
  - fixed the async path so pending background builds do not block cache-state
    checks through the engine lock
  - second async sweep showed request 2 could still slow down because the
    background builder could take the engine lock before the current request
    started generation
  - fixed that by deferring background cache-build scheduling until after the
    current request completes
- Validated deferred async prefix-cache sweep:
  - `cache_scheduled`: `3` requests, mean service request `612.14 ms`, mean
    cache prepare `0.09 ms`, mean actual prefill `930` tokens
  - `cache_hit`: `9` requests, mean service request `188.71 ms`, mean cache
    prepare `0.18 ms`, mean actual prefill `9` tokens
  - artifact: `prefix-latency-sweep-async-deferred.jsonl`
- Async population conclusion:
  - async mode successfully removes synchronous cache-build cost from the
    scheduling request
  - cache hits remain fast once the background build completes
  - immediate requests that arrive while the background builder is active can
    still contend for the model engine lock, so async should remain opt-in
    until the builder becomes idle-aware or queue-aware
- Implemented queue-aware async cache building:
  - async builder waits for scheduler idle before taking the engine lock
  - added `PREFIX_CACHE_ASYNC_IDLE_TIMEOUT_MS` /
    `--prefix-cache-async-idle-timeout-ms`
  - added async telemetry:
    `async_builds_skipped` and `async_idle_timeout_ms`
- Validated queue-aware async sweep:
  - `cache_scheduled`: `3` requests, mean service request `601.03 ms`, mean
    cache prepare `0.09 ms`, mean actual prefill `931.33` tokens
  - `cache_hit`: `9` requests, mean service request `184.55 ms`, mean cache
    prepare `0.17 ms`, mean actual prefill `9` tokens
  - async health: started `3`, completed `3`, failed `0`, skipped `0`
  - artifact: `prefix-latency-sweep-async-idle.jsonl`
- Queue-aware async conclusion:
  - scheduled requests no longer pay synchronous cache-build preparation
  - later hits remain fast and near sync hit latency
  - a race remains: if the scheduler becomes idle and the background worker
    grabs the engine lock just before the next foreground request arrives, that
    foreground request can still wait behind the background build
  - therefore async remains opt-in; the next optimization should implement a
    foreground-priority engine lock or debounce/idle-grace policy before making
    async the default
- Implemented foreground-priority execution locking:
  - replaced direct resident model `RLock` use on inference/cache-build paths
    with `EngineExecutionLock`
  - foreground inference acquires the foreground side of the lock
  - async cache builds acquire the background side and cannot enter while
    foreground requests are waiting
  - `/health` and `/engine` expose `execution_lock` telemetry
  - async cache policy now records `async_background_wait_ms` and
    `async_priority_deferrals`
- Validated foreground-priority async sweep:
  - artifact: `prefix-latency-sweep-async-priority.jsonl`
  - `cache_scheduled`: `3` requests, mean service request `598.67 ms`, mean
    cache prepare `0.08 ms`, mean actual prefill `930.67` tokens
  - `cache_hit`: `9` requests, mean service request `185.65 ms`, mean cache
    prepare `0.18 ms`, mean actual prefill `9` tokens
  - async health: started `3`, completed `3`, failed `0`, skipped `0`
  - execution lock telemetry: foreground acquires `20`, background acquires
    `3`, no pending waiters at the end of the run
- Foreground-priority conclusion:
  - async remains opt-in, but the engine now has the lock semantics needed to
    prevent known background-cache work from overtaking waiting foreground work
  - next validation should add a synthetic race probe with concurrent foreground
    traffic to prove priority deferrals occur under pressure
- Added synthetic execution-lock priority probe:
  - endpoint: `/engine/lock/priority-probe`
  - holds the execution lock, starts a background waiter, then starts a
    foreground waiter
  - releases the lock and verifies foreground acquires before background
  - validates `background_priority_deferrals` increments
- Priority probe evidence:
  - `ok=True`
  - acquisition order: `foreground`, then `background`
  - `background_priority_deferrals_delta=1`
  - foreground wait `0.03 ms`
  - background wait `0.07 ms`
- Final sync-mode smoke still passed after the probe:
  - `health True Device(gpu, 0)`
  - streaming prefix reuse remained valid:
    `stream_prefix 65 0.956 True True False True 93.31 65 3 108.9 7.55`
- Added operator engine presets:
  - launcher env: `ENGINE_PRESET=sync-safe|async-experimental|memory-saver|custom`
  - service arg: `--engine-preset`
  - `/health` and `/engine` report `engine_preset`
  - preset defaults are applied in `run_resident_service.sh`, while explicit
    per-knob env vars still override the preset
- Preset intent:
  - `sync-safe`: conservative default, sync prefix-cache population, 16 cache
    entries, no memory cap
  - `async-experimental`: same scheduler/cache size as `sync-safe`, but async
    prefix-cache population
  - `memory-saver`: smaller queue/cache surface, 4 cache entries, 64 MiB MLX
    cache-memory limit, retains at least 1 prefix-cache entry
- Preset validation evidence:
  - `async-experimental`: `preset_probe async-experimental async 16 None 16`
  - `memory-saver`: `preset_probe memory-saver sync 4 67108864 1 8`
  - restored default: `preset_probe sync-safe sync 16 None 16`
  - final smoke after restore:
    `stream_prefix 65 0.956 True True False True 93.26 65 3 110.71 7.58`
- Added live runtime configuration:
  - endpoint: `POST /engine/config`
  - accepts `engine_preset` and explicit overrides for scheduler, prefix-cache
    size, memory-pressure policy, cache population mode, and async idle timeout
  - preset updates apply without reloading model weights
  - explicit overrides can customize a preset, for example `memory-saver` with
    `prefix_cache_max_entries=3`
- Runtime config validation evidence:
  - switched live to `async-experimental`:
    `config_probe {'engine_preset': 'async-experimental'} async-experimental async 16 None 16`
  - switched live to customized `memory-saver`:
    `config_probe {'engine_preset': 'memory-saver', 'prefix_cache_max_entries': 3} memory-saver sync 3 67108864 8`
  - restored live to `sync-safe`:
    `config_probe {'engine_preset': 'sync-safe'} sync-safe sync 16 None 16`
  - final smoke after live mutation:
    `stream_prefix 64 0.955 True True False True 95.61 64 3 116.66 7.52`
  - final runtime state:
    `final_config_probe sync-safe sync 16 None 16`
- Validation caveat:
  - importing `resident_mlx_service.py` from a Codex-spawned Python subprocess
    can abort in MLX Metal initialization with
    `-[__NSArray0 objectAtIndex:]: index 0 beyond bounds for empty array`
  - this is not the resident server crashing; it is the sandboxed subprocess
    importing `mlx.core`
  - use `py_compile` for syntax validation and tmux-hosted runtime probes for
    MLX behavior
- Added repeatable config policy probe:
  - script: `benchmarks/python/config_policy_probe.py`
  - uses HTTP only, so it does not import `mlx.core`
  - validates `dry_run`, async preset apply, memory-saver override apply,
    restore to sync-safe, and smoke after config changes
- Config policy probe evidence:
  - `initial_config sync-safe sync 16 None 16`
  - `dry_run_config memory-saver sync 3 67108864 8`
  - `apply_async async-experimental async 16 None 16`
  - `apply_memory_saver_override memory-saver sync 3 67108864 8`
  - `restore_sync_safe sync-safe sync 16 None 16`
  - smoke after config still passed:
    `smoke_after_config stream_prefix 62 0.954 True True False True 93.74 62 3 119.4 7.6`
- Added unified resident benchmark harness:
  - script: `benchmarks/python/resident_benchmark_harness.py`
  - writes health snapshots, config application, cache prune evidence, request
    rows, streaming rows, and phase summaries to one JSONL artifact
  - accepts `--engine-preset`, `--reset-cache`, `--requests`, `--prefix-repeats`,
    and `--output-jsonl`
- First harness artifact:
  - `resident-benchmark-sync-safe.jsonl`
  - `15` JSONL rows
  - run id: `1778730833-29612fa9`
- Harness validation evidence:
  - `harness_health_before sync-safe Device(gpu, 0) sync 16`
  - `harness_cache_prune 3 0`
  - full prefill: `571` actual prefill tokens, `2516.39 ms` service request
  - cache create: mean `469.54 ms` service request, mean `7.5` actual prefill
    tokens
  - cache hit: mean `189.66 ms` service request, mean `8.0` actual prefill
    tokens
  - streaming cache-create: first token `125.35 ms`, mean token gap `7.55 ms`
- Added resident benchmark comparison:
  - script: `benchmarks/python/compare_resident_benchmarks.py`
  - compared `resident-benchmark-sync-safe.jsonl`,
    `resident-benchmark-async-experimental.jsonl`, and
    `resident-benchmark-memory-saver.jsonl`
- Preset comparison artifacts:
  - `sync-safe`: mode `sync`, cache entries `16`, run id
    `1778730833-29612fa9`
  - `async-experimental`: mode `async`, cache entries `16`, run id
    `1778731069-8e0b324a`
  - `memory-saver`: mode `sync`, cache entries `4`, memory limit `67108864`,
    run id `1778731075-a72f3233`
- Preset comparison evidence:
  - cache hit mean service request:
    - `sync-safe`: `189.66 ms`, actual prefill `8.00`
    - `async-experimental`: `192.86 ms`, actual prefill `8.00`
    - `memory-saver`: `190.85 ms`, actual prefill `8.00`
  - async scheduled requests:
    - `async-experimental`: `589.86 ms`, actual prefill `572.50`
  - cache create:
    - `sync-safe`: `469.54 ms`, actual prefill `7.50`
    - `memory-saver`: `476.36 ms`, actual prefill `7.50`
  - caveat: full-prefill rows are warm-state sensitive across sequential preset
    runs, so cache-hit rows are the better cross-preset comparison for this
    batch
- Added prefill-isolation benchmark mode:
  - command mode: `--mode prefill-isolation`
  - forces `prefix_cache_population_mode=off`
  - prunes prefix cache and clears MLX cache before the first measured request
  - records `prefill_cold` for the first full-prefill request and
    `prefill_warm` for subsequent full-prefill requests
  - optionally restores the engine preset after the run
- Prefill-isolation artifact:
  - `resident-prefill-isolation-sync-safe.jsonl`
  - `13` JSONL rows
  - run id: `1778734638-71cd2892`
- Prefill-isolation evidence:
  - cold full-prefill: `586` actual prefill tokens, `2520.02 ms` service
    request, `246.48` prompt tok/s
  - warm full-prefill: `586` actual prefill tokens, `426.14 ms` mean service
    request, about `1.88k` prompt tok/s
  - cache reuse stayed disabled: `cache_reuse_enabled=False`
  - final artifact state restored to `sync-safe` with cache population `sync`
- Interpretation:
  - the large first-request latency is primarily warmup/compile/cache-state
    cost, not steady-state prefill throughput
  - steady-state full prefill for this ~586-token shape is about `426 ms`
  - prefix-cache hits at about `190 ms` remain faster than warmed full prefill,
    but the realistic full-prefill baseline for warmed resident service is far
    below the first cold-ish request
- Added artifact-based regression gate:
  - script: `benchmarks/python/resident_regression_gate.py`
  - consumes one cache benchmark artifact and one prefill-isolation artifact
  - default thresholds:
    - cache-hit mean service request <= `250 ms`
    - cache-hit mean actual prefill tokens <= `16`
    - warm-prefill mean service request <= `550 ms`
    - warm-prefill actual prefill tokens >= `500`
    - cold/warm prefill ratio <= `8x`
  - also validates every cache-hit row has suffix reuse enabled and every
    warm-prefill row has cache reuse disabled
- Regression gate evidence:
  - current artifacts passed:
    `gate_result PASS`
  - intentional failure with `--max-cache-hit-service-ms 100` failed as expected:
    `gate_failure cache_hit.mean_service_request_ms: 189.659 > 100.000`
- Added one-command regression suite:
  - script: `benchmarks/python/run_resident_regression_suite.py`
  - runs sync-safe cache benchmark
  - runs sync-safe prefill-isolation benchmark
  - compares the generated artifacts
  - runs `resident_regression_gate.py`
  - exits non-zero if benchmark generation, comparison, or regression gate fails
- Regression suite smoke evidence:
  - command tag: `suite-smoke`
  - cache artifact: `resident-benchmark-sync-safe-suite-smoke.jsonl`
  - prefill artifact: `resident-prefill-isolation-sync-safe-suite-smoke.jsonl`
  - cache-hit mean service request: `180.23 ms`, actual prefill `8.00`
  - prefill-warm mean service request: `432.51 ms`, actual prefill `585.00`
  - gate result: `gate_result PASS`
  - suite result:
    `suite_result PASS resident-benchmark-sync-safe-suite-smoke.jsonl resident-prefill-isolation-sync-safe-suite-smoke.jsonl`
- Suite interpretation:
  - the one-command flow is now suitable as the default local performance
    regression check
  - the suite's `prefill_cold` row can be warm-state dependent if the service
    has already run similar shapes, so the regression gate primarily protects
    warm-prefill and cache-hit behavior
- Added cold-start suite mode:
  - flag: `--cold-start`
  - writes lifecycle artifact:
    `resident-cold-start-sync-safe-<tag>.jsonl`
  - records pre-unload health, unload response, reload response, and
    post-reload health
  - then runs the standard benchmark, comparison, and regression gate flow
- Cold-start suite smoke evidence:
  - tag: `cold-suite-smoke`
  - lifecycle artifact: `resident-cold-start-sync-safe-cold-suite-smoke.jsonl`
  - cache artifact:
    `resident-benchmark-sync-safe-cold-suite-smoke.jsonl`
  - prefill artifact:
    `resident-prefill-isolation-sync-safe-cold-suite-smoke.jsonl`
  - unload elapsed: `940.13 ms`
  - reload elapsed: `6457.05 ms`
  - model load time reported by service: `4385.97 ms`
  - warmup tokens: `[64, 512]`
  - first post-reload full-prefill request: `443.67 ms`, `571` actual prefill
    tokens
  - cache-hit mean: `174.70 ms`, `8.00` actual prefill tokens
  - warm-prefill mean: `422.68 ms`, `585.00` actual prefill tokens
  - gate result: `gate_result PASS`
  - suite result:
    `suite_result PASS resident-benchmark-sync-safe-cold-suite-smoke.jsonl resident-prefill-isolation-sync-safe-cold-suite-smoke.jsonl resident-cold-start-sync-safe-cold-suite-smoke.jsonl`
- Cold-start interpretation:
  - the lifecycle reload path captures model unload/reload/load/warmup overhead
  - after reload warmup, first benchmark full-prefill was already warm-state
    speed, so strict OS/process cold-start still requires a process restart
  - this mode is still useful because it turns lifecycle overhead into a tracked
    artifact and validates post-reload performance does not regress
- Added exact-prompt prefix-cache reuse:
  - prior behavior rejected cache reuse when the prefix match covered the full
    current prompt
  - new behavior trims exact matches to cache `len(prompt_tokens) - 1` tokens
    and prefill only the final trailing token
  - this mirrors the useful LM Studio cache-wrapper behavior without sending an
    empty prompt segment into MLX generation
- Exact-prompt validation:
  - script: `benchmarks/python/exact_prefix_cache_probe.py`
  - endpoint: `/v1/completions`, because it returns `engine_metrics`
  - evidence:
    - first unique prompt run: `59` prompt tokens, partial prior prefix match
      from previous requests, `25` actual prefill tokens
    - second exact repeat: `59` prompt tokens, `59` matched tokens,
      `cache_exact_match_trimmed=True`, `58` cached prefix tokens, `1` actual
      prefill token, `213.78 ms`
    - third exact repeat: cache hit with `58` cached prefix tokens, `1` actual
      prefill token, `117.11 ms`
    - result: `exact_prefix_result PASS`
- Added native prompt-progress telemetry:
  - wires `mlx_lm.generate_step` `prompt_progress_callback(processed, total)`
    through resident text inference
  - final `engine_metrics` now include:
    - `prompt_progress_events`
    - `prompt_progress_total_tokens`
    - `prompt_progress_processed_tokens`
    - `prompt_progress_first_ms`
    - `prompt_progress_last_ms`
    - `prompt_progress_complete`
    - bounded `prompt_progress_trace`
  - benchmark artifacts now carry the same progress summary fields
- Prompt-progress validation:
  - script: `benchmarks/python/prompt_progress_probe.py`
  - test settings: `prefill_step_size=16`, `64` repeated prompt segments,
    prefix cache disabled for full-prefill isolation
  - evidence:
    - `1112` prompt tokens
    - `1112` actual prefill tokens
    - `72` native progress events
    - final processed/total: `1112/1112`
    - completion flag: `prompt_progress_complete=True`
    - final progress timestamp: `2747.41 ms`
    - result: `prompt_progress_result PASS`
- Added live prompt-progress streaming:
  - raw `/generate` with `stream=true` now uses a worker-thread JSONL stream
    path
  - progress callback events are emitted as JSON lines with
    `type=prompt_progress` while MLX is still processing prefill
  - token events and final events keep the existing JSONL shape
  - OpenAI-compatible SSE streaming remains unchanged for compatibility
- Live prompt-progress validation:
  - script: `benchmarks/python/live_prompt_progress_probe.py`
  - test settings: `prefill_step_size=16`, `64` repeated prompt segments,
    prefix cache disabled for full-prefill isolation
  - evidence:
    - streamed progress events: `64`
    - streamed progress events before first token: `64`
    - token events: `4`
    - actual prefill tokens: `987`
    - final metric progress events: `64`
    - completion flag: `True`
    - first progress event reached client at `82.98 ms`
    - final progress event: `987/987` at `2443.4 ms`
    - first token latency: `2439.85 ms`
    - result: `live_prompt_progress_result PASS`
- Added best-effort request cancellation:
  - active request registry tracks route, status, prompt tokens, policy,
    prefill step size, cancellation state, and recent completed requests
  - endpoints:
    - `GET /engine/requests`
    - `POST /engine/requests/{request_id}/cancel`
  - cancellation is checked at native MLX prompt-progress callback boundaries
    and between decode token events
  - raw `/generate` JSONL stream emits `type=cancelled` when a request is
    cancelled
- Request-cancellation validation:
  - script: `benchmarks/python/cancel_request_probe.py`
  - test settings: `prefill_step_size=16`, `96` repeated prompt segments,
    prefix cache disabled, `max_tokens=32`
  - probe starts a raw streaming request, waits for first `prompt_progress`,
    calls the cancel endpoint with the streamed `request_id`, then validates the
    stream and registry state
  - evidence:
    - request id: `req_ab6ffa1750c44d6889c2aa09c7b03359`
    - progress events before cancellation: `2`
    - token events before cancellation: `0`
    - cancelled event progress count: `2`
    - completed registry status: `cancelled`
    - cancel endpoint immediate status: `cancelling`
    - result: `cancel_request_result PASS`
- Added OpenAI-compatible SSE prompt-progress comments:
  - `/v1/completions` with `stream=true` now uses the live worker stream and
    emits prompt progress as SSE comments:
    `: prompt_progress {...}`
  - `/v1/chat/completions` with `stream=true` uses the same comment strategy
  - OpenAI payload compatibility is preserved because generated content and
    final metrics still use normal `data:` chunks
  - cancellation on OpenAI streams maps to a final `data:` chunk with
    `finish_reason="cancelled"`
- OpenAI SSE progress validation:
  - script: `benchmarks/python/openai_sse_progress_probe.py`
  - test settings: `prefill_step_size=16`, `64` repeated prompt segments,
    prefix cache disabled for full-prefill isolation
  - evidence:
    - streamed prompt-progress comments: `68`
    - comments before first `data:` chunk: `68`
    - OpenAI `data:` chunks: `5`
    - actual prefill tokens: `1050`
    - final metric progress events: `68`
    - completion flag: `True`
    - first comment reached client at `89.97 ms`
    - final comment: `1050/1050` at `2633.08 ms`
    - first token latency: `2629.04 ms`
    - result: `openai_sse_progress_result PASS`
- Added generated-token prefix-cache recording:
  - sync requests and live worker streams now keep the mutable MLX
    `prompt_cache` used during generation
  - generated token IDs are recorded from `GenerationResponse.token`
  - after successful generation, the engine records a prefix tracker entry for
    `prompt_tokens + generated_token_ids`
  - the same full generated prefix is stored in `PrefixKVCacheStore` without
    recomputing prefill
  - warmup rows strip internal prompt-cache objects before `/health` serialization
- Generated-token cache validation:
  - script: `benchmarks/python/generated_prefix_cache_probe.py`
  - probe sends an initial completion, builds a follow-up prompt beginning with
    the original prompt plus generated text, then verifies prefix-cache reuse
  - evidence:
    - first prompt tokens: `41`
    - first generation tokens recorded: `12`
    - generated prefix cache recorded: `True`
    - generated prefix cache tokens: `53`
    - second prompt tokens: `59`
    - second longest prefix match: `53`
    - second cache reuse enabled: `True`
    - second cache hit: `True`
    - second cached prefix tokens: `53`
    - second actual prefill tokens: `6`
    - result: `generated_prefix_cache_result PASS`
- Added generated-prefix cache safety probe:
  - script: `benchmarks/python/generated_prefix_cache_safety_probe.py`
  - covers:
    - longer sync continuation reuse
    - raw streaming continuation reuse
    - cancelled prefill does not add generated-prefix cache entries
  - discovered and fixed a stream-path bug where `_stream_run_live_jsonl`
    received only public metadata and therefore lacked private `_prompt_tokens`
    during generated-cache recording
  - the stream helper now accepts explicit prompt tokens/text for generated
    cache recording and reports post-generation cache-recording errors instead
    of hanging the client
- Generated-prefix cache safety evidence:
  - long sync continuation:
    `generated_cache_long_safety 33 32 32 True 65 72 65 True True 7`
  - raw stream continuation:
    `generated_cache_stream_safety 33 12 12 True 45 50 45 True True 5`
  - cancelled prefill:
    `generated_cache_cancel_safety 0 0 2 0 2`
  - result: `generated_prefix_cache_safety_result PASS`
- Integrated generated-prefix cache safety into the one-command regression
  suite:
  - script: `benchmarks/python/run_resident_regression_suite.py`
  - new optional controls:
    - `--skip-generated-cache-safety`
    - `--generated-cache-long-max-tokens`
    - `--generated-cache-stream-max-tokens`
    - `--generated-cache-cancel-repeats`
    - `--generated-cache-prefill-step-size`
  - the suite now runs the cache benchmark, prefill-isolation benchmark,
    comparison, regression gate, and generated-cache safety probe unless the
    safety stage is explicitly skipped
- Integrated suite smoke evidence:
  - tag: `generated-cache-suite-smoke2`
  - command used a shorter prompt shape with `--prefix-repeats 16`, so the
    warm-prefill gate was adjusted to `--min-warm-prefill-tokens 350`
  - cache artifact:
    `resident-benchmark-sync-safe-generated-cache-suite-smoke2.jsonl`
  - prefill artifact:
    `resident-prefill-isolation-sync-safe-generated-cache-suite-smoke2.jsonl`
  - cache-hit mean service request: `163.24 ms`
  - cache-hit mean actual prefill: `8.00` tokens
  - warm-prefill mean service request: `352.03 ms`
  - warm-prefill mean actual prefill: `409.00` tokens
  - regression gate result: `gate_result PASS`
  - generated-cache safety:
    - long sync: `generated_cache_long_safety 35 12 12 True 47 54 47 True True 7`
    - raw stream: `generated_cache_stream_safety 35 6 6 True 41 46 41 True True 5`
    - cancelled prefill: `generated_cache_cancel_safety 0 0 2 0 2`
    - result: `generated_prefix_cache_safety_result PASS`
  - suite result:
    `suite_result PASS resident-benchmark-sync-safe-generated-cache-suite-smoke2.jsonl resident-prefill-isolation-sync-safe-generated-cache-suite-smoke2.jsonl generated_cache_safety= True`
- Integration note:
  - an earlier reduced-prompt smoke failed because `--prefix-repeats 16` only
    produced about `411` warm-prefill tokens while the default gate expected at
    least `500`
  - this was a threshold/prompt-shape mismatch, not an engine regression
- Full-size integrated suite evidence:
  - tag: `generated-cache-suite-full`
  - command used default-size prompt validation with `--prefix-repeats 24`,
    default `--min-warm-prefill-tokens 500`, and generated-cache safety enabled
  - cache artifact:
    `resident-benchmark-sync-safe-generated-cache-suite-full.jsonl`
  - prefill artifact:
    `resident-prefill-isolation-sync-safe-generated-cache-suite-full.jsonl`
  - full-prefill request: `572` actual prefill tokens, `702.49 ms`
  - cache-create mean: `457.29 ms`, `7.50` actual prefill tokens
  - cache-hit mean: `183.51 ms`, `8.00` actual prefill tokens
  - warm-prefill mean: `429.61 ms`, `589.00` actual prefill tokens
  - regression gate:
    - `cache_hit.mean_service_request_ms 183.512 <= 250.0`
    - `cache_hit.mean_actual_prefill_tokens 8.0 <= 16.0`
    - `prefill_warm.mean_service_request_ms 429.609 <= 550.0`
    - `prefill_warm.mean_actual_prefill_tokens 589.0 >= 500.0`
    - `cache_hit_rows_reuse_suffix 4 / 4`
    - `prefill_warm_rows_no_cache_full_prefill 4 / 4`
    - result: `gate_result PASS`
  - generated-cache safety:
    - long sync: `generated_cache_long_safety 36 32 32 True 68 75 68 True True 7`
    - raw stream: `generated_cache_stream_safety 35 12 12 True 47 52 47 True True 5`
    - cancelled prefill: `generated_cache_cancel_safety 0 0 2 0 2`
    - result: `generated_prefix_cache_safety_result PASS`
  - suite result:
    `suite_result PASS resident-benchmark-sync-safe-generated-cache-suite-full.jsonl resident-prefill-isolation-sync-safe-generated-cache-suite-full.jsonl generated_cache_safety= True`
- Added strict process-level cold-start suite:
  - script: `benchmarks/python/process_cold_start_suite.py`
  - starts a separate resident service process on an isolated port
  - waits for `/health` to report loaded GPU state
  - records startup, health-ready, suite, and process-exit rows to JSONL
  - runs the existing one-command regression suite against the fresh process
  - terminates the fresh service process after validation
- Strict process cold-start validation evidence:
  - tag: `process-cold-full`
  - port: `127.0.0.1:8766`
  - fresh service PID: `15989`
  - process artifact:
    `resident-process-cold-start-process-cold-full.jsonl`
  - service log:
    `resident-process-cold-start-process-cold-full.log`
  - cold health ready elapsed: `16049.67 ms`
  - service-reported model load: `8578.13 ms`
  - device: `Device(gpu, 0)`
  - warmup prompt tokens: `[64, 512]`
  - suite elapsed: `7105.00 ms`
  - suite return code: `0`
  - fresh process exit: `-15` after intentional SIGTERM
  - post-run check: no listener remained on port `8766`
- Strict process cold-start suite result:
  - cache artifact:
    `resident-benchmark-sync-safe-process-cold-full-suite.jsonl`
  - prefill artifact:
    `resident-prefill-isolation-sync-safe-process-cold-full-suite.jsonl`
  - full-prefill request: `571` actual prefill tokens, `490.36 ms`
  - cache-hit mean: `185.48 ms`, `8.00` actual prefill tokens
  - warm-prefill mean: `431.17 ms`, `586.00` actual prefill tokens
  - regression gate: `gate_result PASS`
  - generated-cache safety:
    - long sync: `generated_cache_long_safety 37 32 32 True 69 76 69 True True 7`
    - raw stream: `generated_cache_stream_safety 36 12 12 True 48 53 48 True True 5`
    - cancelled prefill: `generated_cache_cancel_safety 0 0 2 0 2`
    - result: `generated_prefix_cache_safety_result PASS`
  - suite result:
    `suite_result PASS resident-benchmark-sync-safe-process-cold-full-suite.jsonl resident-prefill-isolation-sync-safe-process-cold-full-suite.jsonl generated_cache_safety= True`
- Added startup phase instrumentation:
  - `resident_mlx_service.py` now exposes `startup_timings` in `/health`
  - timings include parent-spawn to module import, profile discovery, device
    detection, model access validation, backend detection, `mlx_lm` helper
    imports, profile load, engine state init, model load, warmup, total engine
    init, and parent-spawn to health response
  - `process_cold_start_suite.py` sets
    `MLX_ENGINE_PARENT_STARTED_AT_EPOCH`, records the `/health`
    `startup_timings` block in the process JSONL artifact, and prints a compact
    `process_cold_startup_breakdown` line
- Startup phase breakdown evidence:
  - tag: `process-cold-phases`
  - port: `127.0.0.1:8767`
  - fresh service PID: `18607`
  - process artifact:
    `resident-process-cold-start-process-cold-phases.jsonl`
  - service log:
    `resident-process-cold-start-process-cold-phases.log`
  - parent spawn to module import: `349.09 ms`
  - parent spawn to engine init start: `352.53 ms`
  - runtime device info: `0.01 ms`
  - model access validation: `0.12 ms`
  - backend detection: `0.41 ms`
  - `mlx_lm` helper imports: `3130.47 ms`
  - profile discovery/load combined: `0.52 ms`
  - model load: `6939.15 ms`
  - warmup: `2532.66 ms`
  - engine init total: `12603.19 ms`
  - parent spawn to health response: `13154.25 ms`
  - wrapper-observed health ready: `13151.65 ms`
  - suite elapsed after readiness: `6847.01 ms`
  - post-run check: no listener remained on port `8767`
- Instrumented cold-start suite result:
  - cache artifact:
    `resident-benchmark-sync-safe-process-cold-phases-suite.jsonl`
  - prefill artifact:
    `resident-prefill-isolation-sync-safe-process-cold-phases-suite.jsonl`
  - cache-hit mean: `186.29 ms`, `8.00` actual prefill tokens
  - warm-prefill mean: `436.01 ms`, `588.00` actual prefill tokens
  - regression gate: `gate_result PASS`
  - generated-cache safety: `generated_prefix_cache_safety_result PASS`
  - suite result:
    `suite_result PASS resident-benchmark-sync-safe-process-cold-phases-suite.jsonl resident-prefill-isolation-sync-safe-process-cold-phases-suite.jsonl generated_cache_safety= True`
- Added async warmup mode:
  - `resident_mlx_service.py` now supports `--warmup-mode sync|async|off`
  - default remains `sync` to preserve existing startup behavior
  - async mode marks the engine loaded after model load and starts warmup in a
    background thread
  - `/health` now includes a `warmup` status object with mode, running,
    completed, error, timestamps, and result count
  - `run_resident_service.sh` accepts `WARMUP_MODE`
  - `process_cold_start_suite.py` accepts `--warmup-mode` and can wait for
    warmup completion before running the regression suite
- Async warmup cold-start validation:
  - tag: `process-cold-async-warmup`
  - port: `127.0.0.1:8768`
  - fresh service PID: `58751`
  - process artifact:
    `resident-process-cold-start-process-cold-async-warmup.jsonl`
  - service log:
    `resident-process-cold-start-process-cold-async-warmup.log`
  - health-ready elapsed: `8135.73 ms`
  - health-ready model load: `4442.99 ms`
  - parent spawn to health response: `8139.15 ms`
  - parent spawn to module import: `342.75 ms`
  - `mlx_lm` helper imports: `2966.59 ms`
  - engine init total before background warmup: `7410.54 ms`
  - background warmup wait after health: `1538.82 ms`
  - full warmup completed at about `9678.86 ms` from parent spawn
  - warmup result count: `2`
  - post-run check: no listener remained on port `8768`
- Async warmup regression result:
  - cache artifact:
    `resident-benchmark-sync-safe-process-cold-async-warmup-suite.jsonl`
  - prefill artifact:
    `resident-prefill-isolation-sync-safe-process-cold-async-warmup-suite.jsonl`
  - cache-hit mean: `174.66 ms`, `8.00` actual prefill tokens
  - warm-prefill mean: `420.60 ms`, `586.00` actual prefill tokens
  - regression gate: `gate_result PASS`
  - generated-cache safety: `generated_prefix_cache_safety_result PASS`
  - suite result:
    `suite_result PASS resident-benchmark-sync-safe-process-cold-async-warmup-suite.jsonl resident-prefill-isolation-sync-safe-process-cold-async-warmup-suite.jsonl generated_cache_safety= True`
- Async warmup result:
  - HTTP readiness improved from the prior instrumented sync-warmup result of
    `13154.25 ms` to `8139.15 ms`, a `5015.10 ms` readiness reduction
  - full warmup still completed before the regression suite ran
  - cache-hit, warm-prefill isolation, generated continuation reuse, stream
    continuation reuse, and cancellation non-pollution still passed
- Validated no-warmup startup mode:
  - command uses `--warmup-mode off`
  - tag: `process-cold-no-warmup`
  - port: `127.0.0.1:8769`
  - fresh service PID: `82264`
  - process artifact:
    `resident-process-cold-start-process-cold-no-warmup.jsonl`
  - service log:
    `resident-process-cold-start-process-cold-no-warmup.log`
  - health-ready elapsed: `8652.24 ms`
  - parent spawn to health response: `8654.98 ms`
  - model load: `4972.17 ms`
  - `mlx_lm` helper imports: `2955.78 ms`
  - warmup mode: `off`
  - warmup result count: `0`
  - post-run check: no listener remained on port `8769`
- No-warmup regression result:
  - cache artifact:
    `resident-benchmark-sync-safe-process-cold-no-warmup-suite.jsonl`
  - prefill artifact:
    `resident-prefill-isolation-sync-safe-process-cold-no-warmup-suite.jsonl`
  - first real full-prefill request: `2189.62 ms`, `574` actual prefill tokens
  - cache-hit mean: `182.60 ms`, `8.00` actual prefill tokens
  - warm-prefill mean: `431.62 ms`, `588.00` actual prefill tokens
  - regression gate: `gate_result PASS`
  - generated-cache safety: `generated_prefix_cache_safety_result PASS`
  - suite result:
    `suite_result PASS resident-benchmark-sync-safe-process-cold-no-warmup-suite.jsonl resident-prefill-isolation-sync-safe-process-cold-no-warmup-suite.jsonl generated_cache_safety= True`
- Warmup policy conclusion:
  - `off` does not materially beat async readiness on this run
    (`8654.98 ms` off vs `8139.15 ms` async)
  - `off` exposes a first-request latency spike (`2189.62 ms`) because no
    representative prefill has been warmed
  - `async` remains the preferred default for interactive service readiness:
    early HTTP readiness, background warmup, and no first-request cold penalty
    when clients wait for `warmup.completed=true`
- Promoted async warmup to launcher default:
  - `run_resident_service.sh` now defaults `WARMUP_MODE` to `async`
  - direct `resident_mlx_service.py` still defaults to `sync` for explicit
    benchmark compatibility
  - operators can still override launcher behavior with `WARMUP_MODE=sync` or
    `WARMUP_MODE=off`
  - launcher smoke validation started the service on `127.0.0.1:8770` through
    `run_resident_service.sh` and terminated it with `timeout 20s`
  - post-run check confirmed no listener remained on port `8770`
- Added resident readiness probe:
  - script: `benchmarks/python/wait_resident_ready.py`
  - waits for `/health` to report `ok=true` and loaded model state
  - optional `--require-gpu` verifies `Device(gpu, 0)` style GPU readiness
  - optional `--require-warmup` waits for `warmup.completed=true`
  - includes backward-compatible warmup inference for legacy service processes
    that expose `warmup_results` but not the newer `warmup` object
- Readiness probe validation against live server:
  - loaded/GPU check:
    `resident_ready True sync-safe Device(gpu, 0) legacy True 2`
  - loaded/GPU/warmup check:
    `resident_ready True sync-safe Device(gpu, 0) legacy True 2`
  - validation used the current live resident server on `127.0.0.1:8765`
- Promoted readiness probe into packaged CLI:
  - added `bin/mlx-engine ready`
  - supports `--require-gpu` and `--require-warmup`
  - packaged CLI validation against live server:
    - `resident_ready True sync-safe Device(gpu, 0) legacy True 2`
    - `resident_ready True sync-safe Device(gpu, 0) legacy True 2`
- Promoted regression suite into packaged CLI:
  - added `bin/mlx-engine suite`
  - wraps `benchmarks/python/run_resident_regression_suite.py`
  - packaged CLI full-suite validation:
    - command: `bin/mlx-engine suite --base-url http://127.0.0.1:8765 --tag cli-suite-full`
    - cache-hit mean: `178.02 ms`, `8.00` actual prefill tokens
    - warm-prefill mean: `415.59 ms`, `586.00` actual prefill tokens
    - `gate_result PASS`
    - `generated_prefix_cache_safety_result PASS`
    - `suite_result PASS resident-benchmark-sync-safe-cli-suite-full.jsonl resident-prefill-isolation-sync-safe-cli-suite-full.jsonl generated_cache_safety= True`
- Started package cleanup:
  - moved stable resident service implementation into
    `mlx_engine/resident_service.py`
  - added `mlx_engine/__init__.py`
  - replaced `benchmarks/python/resident_mlx_service.py` with a compatibility
    wrapper that imports `mlx_engine.resident_service.main`
  - updated `bin/mlx-engine serve` to target the packaged service path
  - added `--warmup-mode` to `bin/mlx-engine serve`, defaulting to `async`
- Package-path validation:
  - command:
    `timeout 20s bin/mlx-engine serve --model /Volumes/StudioStackSSD4TB/Development/LLM/lmstudio/models/mlx-community/gpt-oss-20b-MXFP4-Q8 --port 8771`
  - result:
    `INFO: Uvicorn running on http://127.0.0.1:8771`
  - timeout shutdown completed:
    `INFO: Finished server process [57278]`
  - post-run check confirmed no listener remained on port `8771`
- Compatibility wrapper validation:
  - command:
    `timeout 20s python3 benchmarks/python/resident_mlx_service.py --model /Volumes/StudioStackSSD4TB/Development/LLM/lmstudio/models/mlx-community/gpt-oss-20b-MXFP4-Q8 --port 8772 --warmup-mode async --require-gpu`
  - result:
    `INFO: Uvicorn running on http://127.0.0.1:8772`
  - timeout shutdown completed:
    `INFO: Finished server process [99286]`
  - post-run check confirmed no listener remained on port `8772`
- Added package/source hygiene:
  - added `mlx_engine/README.md` to define the stable package boundary
  - added `.gitignore` rules for local MLX engine run artifacts:
    `*.jsonl`, `resident-*.log`, and `resident-service-*.log`
  - generated benchmark artifacts are now ignored, while source scripts, docs,
    profile JSON, and Qwen static report JSON files remain visible for review
- Updated launchd packaging:
  - `packaging/launchd/com.jecruz.mlx-engine.plist.template` now passes
    `--warmup-mode async` explicitly
  - added `packaging/launchd/README.md` with template substitutions and
    readiness commands for loaded and warm states
- Completed M9.1 generated-prefix cache edge hardening:
  - added API stop-string support to raw `/generate`, `/v1/completions`, and
    `/v1/chat/completions`, including streaming paths
  - added a generated-prefix token-boundary guard before storing generated KV
    cache entries
  - stop-string-trimmed responses now skip generated-prefix cache storage when
    returned text no longer retokenizes to the recorded generated token IDs
  - added `benchmarks/python/generated_prefix_cache_edge_probe.py`
  - integrated the edge probe into `benchmarks/python/run_resident_regression_suite.py`
    and `bin/mlx-engine suite`
  - `bin/mlx-engine suite` now includes generated-cache safety and generated-cache
    edge probes by default
- M9.1 validation against patched fresh server on `127.0.0.1:8773`:
  - readiness:
    `resident_ready True custom Device(gpu, 0) async True 2`
  - standalone edge probe:
    `generated_prefix_cache_edge_result PASS`
  - default integrated suite:
    - cache-hit mean: `185.04 ms`, `8.00` actual prefill tokens
    - warm-prefill mean: `425.83 ms`, `589.00` actual prefill tokens
    - `gate_result PASS`
    - `generated_prefix_cache_safety_result PASS`
    - `generated_prefix_cache_edge_result PASS`
    - `suite_result PASS resident-benchmark-sync-safe-edge-integrated-suite.jsonl resident-prefill-isolation-sync-safe-edge-integrated-suite.jsonl generated_cache_safety= True generated_cache_edges= True`
- Completed M9.2 concurrent cancellation pressure hardening:
  - added `benchmarks/python/concurrent_cancel_pressure_probe.py`
  - probe starts one cancellable long-prefill stream, stacks four foreground
    completion clients behind it, cancels at the first prompt-progress event,
    verifies queued clients complete, verifies the cancelled stream emits no
    token events, verifies request registry state is `cancelled`, verifies the
    scheduler returns idle, and verifies cache entries do not change while cache
    population is off
  - integrated the pressure probe into the default `bin/mlx-engine suite`
  - added `--skip-concurrent-cancel-pressure` for explicit bypasses
- M9.2 validation against patched fresh server on `127.0.0.1:8773`:
  - standalone pressure probe:
    `concurrent_cancel_pressure_result PASS`
  - standalone probe queue evidence:
    - cancelled request progress events: `2`
    - cancelled request token events: `0`
    - four client requests completed with queue waits from about `299.95 ms`
      to `962.33 ms`
    - scheduler after probe: `total_admitted=5`, `total_completed=5`,
      `total_rejected=0`
  - default integrated suite:
    - cache-hit mean: `178.24 ms`, `8.00` actual prefill tokens
    - warm-prefill mean: `424.66 ms`, `587.00` actual prefill tokens
    - `gate_result PASS`
    - `generated_prefix_cache_safety_result PASS`
    - `generated_prefix_cache_edge_result PASS`
    - `concurrent_cancel_pressure_result PASS`
    - `suite_result PASS resident-benchmark-sync-safe-concurrent-integrated-suite.jsonl resident-prefill-isolation-sync-safe-concurrent-integrated-suite.jsonl generated_cache_safety= True generated_cache_edges= True concurrent_cancel_pressure= True`
- Completed launchd operational packaging slice:
  - added `packaging/launchd/install.sh`
  - added `packaging/launchd/uninstall.sh`
  - template now supports rendered `__LABEL__`, `__HOST__`, `__PORT__`, and
    `__WARMUP_MODE__` values in addition to repo/model/log paths
  - install script renders the plist, creates log/plist directories, runs
    `plutil -lint`, and optionally bootstraps the LaunchAgent with `--load`
  - uninstall script bootouts the LaunchAgent and removes the rendered plist
    unless `--keep-plist` is passed
  - updated `packaging/launchd/README.md` with install, load, readiness, and
    uninstall commands
- Launchd packaging validation:
  - template lint:
    `packaging/launchd/com.jecruz.mlx-engine.plist.template: OK`
  - dry render command used temporary paths:
    `packaging/launchd/install.sh --model /Volumes/StudioStackSSD4TB/Development/LLM/lmstudio/models/mlx-community/gpt-oss-20b-MXFP4-Q8 --plist-dir /tmp/mlx-engine-launchagents --log-dir /tmp/mlx-engine-logs --label com.jecruz.mlx-engine.test --port 8774`
  - rendered plist lint:
    `/tmp/mlx-engine-launchagents/com.jecruz.mlx-engine.test.plist: OK`
  - rendered plist used `bin/mlx-engine serve`, the target model path,
    `127.0.0.1:8774`, `--warmup-mode async`, and `--require-gpu`
  - uninstall validation removed the temporary plist:
    `mlx_engine_launchd_plist_removed /tmp/mlx-engine-launchagents/com.jecruz.mlx-engine.test.plist`
- Completed M13 profile-prefill warmup latency measurement:
  - added `benchmarks/python/profile_prefill_warmup_latency_probe.py`
  - probe reloads the resident engine twice against the same model/profile:
    once with `warmup_profile_prefill=false`, once with
    `warmup_profile_prefill=true`
  - each case waits for async warmup completion, prunes prefix cache, then sends
    the same first real prompt and records `service_request_ms`,
    `prompt_tokens_estimate`, `actual_prefill_tokens`, selected
    `prefill_step_size`, and warmup results
  - short initial run at `1025` prompt tokens selected `prefill_step_size=None`
    and showed no expected profile-prefill advantage:
    `587.76 ms` off vs `588.71 ms` on
  - long run targeted the measured long-prompt band:
    `4102` prompt tokens, `prefill_step_size=2048`,
    `actual_prefill_tokens=4102`
  - profile-prefill-on warmup included the extra `4096` token profile-band
    target with `prefill_step_size=2048` before the first real prompt
  - long-run first real prompt result:
    `2032.46 ms` with profile-prefill off vs `2048.37 ms` with
    profile-prefill on
  - M13 conclusion: profile-selected prefill warmup validates warmup coverage
    but does not materially improve first real long-prompt latency for this
    shape; the next optimization should target reusable compiled prefill graphs,
    prompt-cache construction/reuse, or request-shape batching rather than
    simply adding more warmup prompts
- Completed M14 prefix-cache population mode measurement:
  - added `benchmarks/python/prefix_cache_population_mode_probe.py`
  - probe compares `sync-safe` foreground cache creation against
    `async-experimental` background cache population for the same repeated-prefix
    prompt sequence
  - each mode runs baseline, populate, and follow-up hit requests, prunes cache
    before the case, records `service_request_ms`, `cache_prepare_ms`,
    `actual_prefill_tokens`, cache-created/scheduled/hit state, and writes a
    JSONL summary
  - 622-token run:
    - sync populate: `467.60 ms`, including `315.86 ms` foreground
      `cache_prepare_ms`, suffix-only `actual_prefill_tokens=8`
    - async populate: `444.45 ms`, `0.07 ms` cache prepare, full
      `actual_prefill_tokens=625`, cache scheduled in background
    - async follow-up hit: `167.49 ms`, `actual_prefill_tokens=10`
  - 1520-token run:
    - sync populate: `854.33 ms`, including `699.92 ms` foreground
      `cache_prepare_ms`, suffix-only `actual_prefill_tokens=8`
    - async populate: `842.08 ms`, `0.09 ms` cache prepare, full
      `actual_prefill_tokens=1524`, cache scheduled in background
    - async follow-up hit: `156.47 ms`, `actual_prefill_tokens=10`
  - M14 conclusion: async cache population removes the foreground cache-build
    stall from the populate request, but the populate request still pays full
    prefill; end-to-end populate latency is therefore roughly neutral. The real
    win is operational: avoid blocking the request path on cache construction
    and let the next related request get the fast cache-hit path. The next
    optimization should target reusing the populate request's own prompt cache
    or safely slicing prompt-cache state so cache creation does not require a
    second prefill at all.
- Completed M15 request-derived prefix-cache guardrail:
  - added experimental `prefix_cache_population_mode=request`
  - request mode first tries to store a matched prefix by deep-copying the
    request-owned prompt cache after generation and trimming generated tokens
    plus the non-shared suffix
  - if the active `mlx-lm` cache stack reports that prompt-cache trimming is
    unsafe, request mode falls back to async prefix-cache population instead of
    silently losing cache reuse
  - added `benchmarks/python/request_prefix_cache_probe.py`
  - 1520-token validation against
    `/Volumes/StudioStackSSD4TB/Development/LLM/lmstudio/models/mlx-community/gpt-oss-20b-MXFP4-Q8`:
    - async populate: `827.14 ms`, `cache_prepare_ms=0.10`,
      `actual_prefill_tokens=1523`, `cache_scheduled=True`
    - async follow-up hit: `162.66 ms`, `actual_prefill_tokens=7`
    - request populate: `832.39 ms`, `cache_prepare_ms=0.10`,
      `actual_prefill_tokens=1526`, `cache_request_store_reason=not_trimmable_fallback_async`,
      `cache_scheduled=True`
    - request follow-up hit: `151.76 ms`, `actual_prefill_tokens=7`
  - M15 conclusion: request-derived cache slicing is not safe for this
    `gpt-oss-20b-MXFP4-Q8` cache stack because `mlx-lm` reports at least one
    prompt-cache component as non-trimmable. The new mode is still useful as a
    correctness gate: it proves the engine can attempt zero-extra-prefill cache
    population only when MLX cache classes support it, and otherwise degrade to
    async population while preserving the next-request cache-hit path. The next
    performance path should identify which Qwen/MLX cache classes are trimmable
    and validate request-derived prefix slicing on that model family before
    enabling it in an operator preset.
- Completed M16 Qwen request-cache validation and loader hardening:
  - fixed backend detection so Qwen text generation architectures are not
    rejected only because their converted config includes `vision_config`
  - added a constrained text-loader fallback for local Qwen packages that carry
    extra `language_model.vision_tower.*` tensors: strict load is attempted
    first, then `strict=False` is used only when the strict failure is caused by
    extra vision-tower weights
  - exposed `load_strict`, `load_fallback_reason`, and
    `prompt_cache_capabilities` in `/health` and `/engine`
  - extended `benchmarks/python/request_prefix_cache_probe.py` to write and
    print prompt-cache capability rows
  - Qwen model validated:
    `/Volumes/StudioStackSSD4TB/Development/LLM/lmstudio/models/unsloth/Qwen3.6-35B-A3B-UD-MLX-4bit`
  - health evidence from the live Qwen server:
    `m16_health True False extra_vision_tower_weights_ignored False ['ArraysCache', 'KVCache'] Device(gpu, 0)`
  - request-cache probe evidence:
    - prompt cache entries: `40`
    - prompt cache classes: `ArraysCache, KVCache`
    - all trimmable: `False`
    - async populate: `519.63 ms`, `actual_prefill_tokens=631`,
      `cache_scheduled=True`
    - async follow-up hit: `225.97 ms`, `actual_prefill_tokens=7`
    - request populate: `487.47 ms`, `actual_prefill_tokens=627`,
      `cache_request_store_reason=not_trimmable_fallback_async`,
      `cache_scheduled=True`
    - request follow-up hit: `205.30 ms`, `actual_prefill_tokens=7`
  - M16 conclusion: this local Qwen A3B MLX package is now loadable in the
    resident text engine, but request-derived prefix-cache slicing is still not
    enabled because `ArraysCache` is not trimmable. The safe performance path is
    still async cache population plus cache-hit reuse. The next optimization
    should either add safe trimming support for the relevant `ArraysCache`
    state, or locate a Qwen text model whose prompt cache is composed only of
    trimmable KV cache classes.
- Completed M17 recurrent-cache slicing safety:
  - inspected `mlx_lm.models.qwen3_5` and confirmed Qwen3.5 linear layers use
    `ArraysCache(size=2)` for convolution state and gated-delta recurrent state
  - added explicit trim-blocker telemetry for non-KV prompt-cache entries
  - `/health` and `/engine` now report:
    - `prompt_cache_capabilities.trimmable_entries`
    - `prompt_cache_capabilities.non_trimmable_entries`
    - `prompt_cache_capabilities.non_trimmable_classes`
    - `prompt_cache_capabilities.trim_blocker_reasons`
  - extended `benchmarks/python/request_prefix_cache_probe.py` so request mode
    fails if it stores a prefix from a non-trimmable cache stack, and
    specifically asserts the `ArraysCache` fallback path
  - live Qwen validation:
    - entries: `40`
    - trimmable entries: `10`
    - non-trimmable entries: `30`
    - non-trimmable class: `ArraysCache`
    - blocker: `array_or_recurrent_state_not_suffix_trimmable`
    - async populate: `491.42 ms`, follow-up hit `207.61 ms`,
      `actual_prefill_tokens=7`
    - request populate: `490.71 ms`,
      `cache_request_store_reason=not_trimmable_fallback_async`
    - request follow-up hit: `204.07 ms`, `actual_prefill_tokens=7`
  - M17 conclusion: `ArraysCache` must not be suffix-trimmed for
    request-derived prefix storage because it carries recurrent state after the
    whole processed sequence. The engine now exposes and enforces that safety
    boundary. The next speed milestone should not try to "trim" this state;
    it should instead avoid computing the suffix before cache storage, for
    example by prefill-splitting the populate request at the matched prefix
    boundary and then continuing generation from a copied prefix cache.
- Completed M18 split-prefill request population:
  - changed `prefix_cache_population_mode=request` for non-trimmable cache
    stacks from "full prefill, then async fallback build" to explicit
    split-prefill:
    - synchronously build/store the matched prefix cache
    - copy that prefix cache into the current request
    - continue the current request through only the suffix tokens
    - do not schedule a background rebuild
  - added request metrics:
    - `cache_split_prefill`
    - `cache_split_prefill_reason`
  - extended `benchmarks/python/request_prefix_cache_probe.py` output and
    assertions for the split-prefill path
  - live Qwen A3B validation:
    - async populate: `493.64 ms`, `actual_prefill_tokens=630`,
      `cache_scheduled=True`
    - async follow-up hit: `204.00 ms`, `actual_prefill_tokens=7`
    - request split-prefill populate: `531.53 ms`,
      `cache_prepare_ms=321.00`, `actual_prefill_tokens=9`,
      `cache_split_prefill=True`, `cache_scheduled=False`
    - request follow-up hit: `211.41 ms`, `actual_prefill_tokens=7`
  - M18 conclusion: split-prefill is now the safe recurrent-cache population
    path. On the ~630 token Qwen probe it is about `37.89 ms` slower than async
    end-to-end because the prefix cache is built in the foreground, but it
    eliminates full populate prefill and the separate background rebuild. The
    next performance test should repeat this at longer prompts where avoiding
    full populate prefill and background rebuild should matter more.
- Completed M19 split-prefill length sweep:
  - added `benchmarks/python/request_prefix_cache_length_sweep.py`
  - swept Qwen A3B repeated-prefix shapes at `24`, `60`, and `120` shared
    context repeats, corresponding to roughly `628`, `1531`, and `3031`
    populate prompt tokens
  - M19 live sweep results:
    - repeats `24`: async populate `492.09 ms` with `628` actual prefill
      tokens; request split-prefill populate `530.38 ms` with `9` actual
      prefill tokens; delta `-38.29 ms`
    - repeats `60`: async populate `832.92 ms` with `1531` actual prefill
      tokens; request split-prefill populate `869.10 ms` with `9` actual
      prefill tokens; delta `-36.18 ms`
    - repeats `120`: async populate `1497.13 ms` with `3031` actual prefill
      tokens; request split-prefill populate `1546.66 ms` with `9` actual
      prefill tokens; delta `-49.52 ms`
  - cache-hit behavior remained stable:
    - async hit range: `203.18-223.24 ms`
    - request hit range: `196.70-210.04 ms`
  - M19 conclusion: split-prefill delivers the intended compute-shape change
    by reducing populate-request prefill from full prompt length to suffix-only
    `9` tokens and eliminating async rebuild scheduling. It still does not beat
    async end-to-end through ~3k tokens because foreground prefix preparation is
    effectively the same expensive work as the async full-prefill path. The
    next optimization should target prefix-cache construction cost directly:
    reuse the foreground prefix build across multiple waiting requests, move it
    off the foreground path with admission-aware scheduling, or add lower-level
    cache continuation that avoids reprocessing the matched prefix.
- Completed M20 async prefix-build amortization probe:
  - added `benchmarks/python/async_prefix_build_amortization_probe.py`
  - added prefix-cache policy counters:
    - `existing_build_reuses`
    - `pending_build_deduplications`
  - added per-request metrics:
    - `cache_build_deduplicated`
    - `cache_build_dedup_reason`
  - live Qwen A3B validation with
    `/Volumes/StudioStackSSD4TB/Development/LLM/lmstudio/models/unsloth/Qwen3.6-35B-A3B-UD-MLX-4bit`:
    - baseline: `1285.07 ms`, `actual_prefill_tokens=1343`
    - schedule: `771.20 ms`, `cache_scheduled=True`,
      `actual_prefill_tokens=1346`
    - duplicate pending request: `772.63 ms`, `cache_pending=True`,
      `cache_build_deduplicated=True`,
      `cache_build_dedup_reason=pending_async_build`
    - final hit: `217.74 ms`, `cache_hit=True`,
      `actual_prefill_tokens=9`
    - summary: `started_delta=1`, `completed_delta=1`,
      `pending_build_deduplications_delta=1`
  - M20 conclusion: in-flight async prefix builds are now explicitly shared
    and measurable. A second related request no longer launches another
    background build while the first build is pending. This does not reduce the
    duplicate request's own prefill yet; it prevents redundant background
    rebuild work and gives M21 an admission/scheduling signal to decide when
    requests should wait for a nearly-ready prefix build versus proceed through
    full prefill.
- Completed M21 admission-aware pending-build wait:
  - added runtime config:
    - `prefix_cache_pending_wait_ms`
  - added prefix-cache policy counters:
    - `pending_waits`
    - `pending_wait_hits`
    - `pending_wait_timeouts`
    - `pending_wait_misses`
    - `pending_wait_total_ms`
  - added per-request metrics:
    - `cache_pending_wait_ms`
    - `cache_pending_wait_result`
  - added `benchmarks/python/async_prefix_pending_wait_probe.py`
  - live Qwen A3B validation:
    - baseline: `1185.13 ms`, `actual_prefill_tokens=1222`
    - schedule: `717.99 ms`, `cache_scheduled=True`,
      `actual_prefill_tokens=1226`
    - pending wait hit: `1267.09 ms`, `cache_pending=True`,
      `cache_build_deduplicated=True`,
      `cache_pending_wait_result=hit`,
      `cache_pending_wait_ms=1053.43`, `cache_hit=True`,
      `actual_prefill_tokens=10`
    - summary: `started_delta=1`, `completed_delta=1`,
      `pending_waits_delta=1`, `pending_wait_hits_delta=1`
  - M21 conclusion: a duplicate foreground request can now yield its scheduler
    active slot while a matching async prefix build completes, then resume as a
    cache hit instead of full-prefilling. This is the first path where pending
    async construction directly improves the duplicate request's prefill shape,
    not just background work duplication.
- Completed M22 lower-level MLX cache continuation readiness:
  - added `/health` and `/engine` report:
    - `prompt_cache_continuation`
    - `native_replay_free_prefix_store_supported`
    - `replay_free_supported_entries`
    - `blocked_entries`
    - `blocked_classes`
    - `blocker_reasons`
    - `safe_request_prefix_store_strategy`
    - `required_lower_level_work`
  - added `benchmarks/python/cache_continuation_capabilities_probe.py`
  - source inspection target:
    - installed `mlx-lm` version: `0.30.7`
    - `KVCache` exposes offset/update/trim semantics
    - `ArraysCache` stores recurrent array state but has no offset or trim
      semantics, so it is not safe for generic replay-free prefix slicing
  - live Qwen A3B validation:
    - entries: `40`
    - replay-free supported entries: `10`
    - blocked entries: `30`
    - blocked class: `ArraysCache`
    - blocker: `arrays_cache_has_recurrent_state_without_offset_or_trim`
    - native replay-free prefix store supported: `False`
    - safe strategy: `split_prefill_or_async_build`
    - required lower-level work:
      `model_specific_recurrent_state_continuation_for_arrays_cache`
  - M22 conclusion: the current MLX/Qwen cache stack should not attempt a
    generic lower-level replay-free prefix-store optimization. KV layers are
    structurally compatible, but the 30 recurrent `ArraysCache` layers need
    model-specific continuation semantics before we can avoid replaying the
    matched prefix safely.
- Completed M23 productization / engine readiness:
  - added `docs/mac-local-inference-platform/engine-readiness.md`
  - added `benchmarks/python/engine_readiness_probe.py`
  - readiness probe validates:
    - health is OK
    - Metal GPU is active
    - M20 build deduplication counters are exposed
    - M21 pending-wait controls and counters are exposed
    - M22 continuation report is exposed
    - `/engine/config` dry-run plans `prefix_cache_pending_wait_ms`
  - live readiness validation:
    - backend: `text`
    - device: `Device(gpu, 0)`
    - `mlx-lm`: `0.30.7`
    - safe strategy: `split_prefill_or_async_build`
  - M23 conclusion: M20-M22 are now packaged into an operator-facing readiness
    surface with named controls, probes, and go/no-go checks suitable for the
    next product/UI integration pass.
- Completed M24 profile presets and readiness API contract:
  - added product-facing `runtime_profile` control:
    - `interactive`
    - `agent-workspace`
    - `memory-saver`
    - `diagnostics`
  - added `/engine/profiles` catalog endpoint
  - extended `/engine/config` dry-run and apply paths to accept
    `runtime_profile`
  - added `benchmarks/python/runtime_profile_probe.py`
  - updated `engine-readiness.md` to make named profiles the product-facing
    surface over lower-level cache/scheduler knobs
  - M24 conclusion: product/UI integration can target named runtime profiles
    instead of exposing raw implementation controls first.
- Completed M25 UI/API integration contract:
  - added `GET /engine/ui`
  - added UI-facing snapshot sections:
    - `readiness`
    - `controls`
    - `cache`
    - `scheduler`
    - `memory`
    - `metrics`
    - `profiles`
  - added `benchmarks/python/ui_status_contract_probe.py`
  - updated `engine-readiness.md` with the UI integration contract
  - M25 conclusion: a UI or app integration can now consume one stable status
    endpoint instead of composing low-level engine endpoints directly.
- Completed M26 UI client adapter:
  - added `mlx_engine/ui_client.py`
  - added `EngineUiClient`
  - added normalized `EngineUiSummary`
  - added `benchmarks/python/ui_client_adapter_probe.py`
  - updated `engine-readiness.md` with the adapter validation command
  - M26 conclusion: Python CLI/TUI/product integrations can consume `/engine/ui`
    through a small stable adapter instead of binding directly to raw JSON.
- Completed M27 Dax TUI consumer:
  - added `dax mlx-engine` in
    `/Users/jeffreycruz/Development/AI_AGENTS/dax-stereo`
  - Dax consumes:
    - `GET /engine/ui`
    - `GET /engine/profiles`
    - `POST /engine/config`
  - added a Dax TUI status panel plus `--once` and `--json` modes for scripts
  - added profile dry-run/apply support through `--profile` and `--dry-run`
  - live validation against the Qwen A3B server on port `8773` reported:
    - loaded: `yes`
    - model: `Qwen3.6-35B-A3B-UD-MLX-4bit`
    - GPU ready: `yes`
    - can generate: `yes`
    - cache strategy: `split_prefill_or_async_build`
    - profiles: `interactive`, `agent-workspace`, `memory-saver`,
      `diagnostics`
  - M27 conclusion: the MLX engine control surface is now validated by a real
    terminal product consumer without coupling Dax to internal MLX engine code.
- Completed M28 Dax generation path:
  - extended `dax mlx-engine` with:
    - `--prompt`
    - `--max-tokens`
    - `--completion`
  - default generation path uses `POST /v1/chat/completions`
  - `--completion` uses `POST /v1/completions`
  - live Qwen A3B validation through Dax:
    - chat completion returned usage `prompt=20 completion=8 total=28`
    - raw text completion returned usage `prompt=4 completion=6 total=10`
  - M28 conclusion: Dax is no longer only an engine monitor; it can now submit
    real generation work to the resident MLX engine while still using the
    OpenAI-compatible HTTP boundary.
- Completed M29 Dax streaming generation:
  - extended `dax mlx-engine` with `--stream`
  - streaming mode consumes OpenAI-compatible SSE events from:
    - `POST /v1/chat/completions`
    - `POST /v1/completions`
  - added SSE data-block parsing, `[DONE]` handling, chunk printing, and final
    usage reporting
  - live Qwen A3B validation through Dax:
    - chat streaming returned usage `prompt=18 completion=8 total=26`
    - raw completion streaming returned usage `prompt=4 completion=6 total=10`
  - M29 conclusion: Dax can now display generation as the resident MLX engine
    emits tokens, which is the correct interaction model for a terminal
    operator UI and agentic coding workflow.
- Completed M30 Dax interactive prompt panel:
  - extended `dax mlx-engine` with `--interactive`
  - added a focused Dax TUI prompt panel with:
    - model/GPU/profile header
    - current runtime profile catalog
    - single-line prompt input
    - short transcript
    - streamed assistant response updates
    - usage summary after final stream event
  - added component-level test coverage for prompt submission, streamed response
    accumulation, usage rendering, and re-render callbacks
  - M30 conclusion: Dax now has the first product-shaped terminal interaction
    surface for the resident MLX engine instead of only one-shot command output.
- Completed M31 interactive runtime profile controls:
  - added in-panel commands:
    - `/profiles`
    - `/profile <name>`
    - `/profile next`
  - profile application calls `POST /engine/config` and refreshes `GET
    /engine/ui`
  - the panel header updates after a successful profile switch
  - added tests for in-panel profile listing, cycling, application, and rendered
    status update
  - M31 conclusion: Dax can now control resident-engine runtime behavior from
    inside the interactive terminal panel without leaving the MLX operator UI.
- Completed M32 interactive generation cancellation:
  - added configurable stop key support:
    - `--stop-key`
    - `DAX_MLX_ENGINE_STOP_KEY`
    - default: `escape`
  - `streamGeneration` now accepts an `AbortSignal` and passes it to `fetch`
  - the interactive panel owns one `AbortController` per in-flight generation
  - stopping a generation records `generation stopped` in the transcript and
    leaves the TUI running
  - added tests for in-flight abort behavior and partial transcript retention
  - M32 conclusion: long or bad generations can be interrupted without killing
    the Dax MLX prompt panel.
- Completed M33 interactive live engine refresh:
  - the interactive panel now accepts refreshed `GET /engine/ui` snapshots
  - interactive mode polls:
    - `GET /engine/ui`
    - `GET /engine/profiles`
  - refresh cadence uses existing `--refresh-ms`
  - the panel header now shows:
    - active requests
    - queued requests
    - cache strategy/population mode
    - failed request count
    - total request count
  - added tests for refreshed active/queued/cache/failure rendering
  - M33 conclusion: the interactive Dax panel now behaves like a live operator
    surface instead of a static prompt shell.
- Completed M34 interactive transcript export:
  - added in-panel command:
    - `/export [path]`
  - default export path is a timestamped `mlx-engine-session-*.json` file in
    the current working directory
  - exported evidence JSON includes:
    - export timestamp
    - mode
    - max token cap
    - latest engine UI snapshot
    - profile catalog
    - plain-text transcript
  - added tests for export file creation and transcript payload shape
  - M34 conclusion: Dax prompt sessions can now be saved as reproducible local
    inference evidence artifacts.
- Completed M35 interactive lifecycle controls:
  - added Dax client helpers for:
    - `POST /engine/reload`
    - `POST /engine/unload`
  - added in-panel commands:
    - `/reload`
    - `/reload <model-path>`
    - `/unload`
  - reload and unload commands refresh the panel from `GET /engine/ui` after
    the lifecycle action completes
  - added tests for client lifecycle calls and in-panel lifecycle transcript
    rendering
  - M35 conclusion: the Dax prompt panel can now control resident model
    lifecycle directly instead of requiring a separate terminal or HTTP client.
- Completed M36 interactive cache controls:
  - added Dax client helper for:
    - `POST /engine/cache/prune`
  - added in-panel command:
    - `/cache prune [target_entries]`
  - default prune target is `0` entries, matching the server manual-prune
    recovery path
  - cache prune commands refresh the panel from `GET /engine/ui` after the
    prune completes
  - added tests for direct cache prune calls, in-panel cache prune transcript
    rendering, and invalid target validation
  - M36 conclusion: the Dax prompt panel can now perform manual prefix-cache
    recovery without requiring a separate HTTP client.
- Completed M37 interactive runtime config controls:
  - added Dax client helper for:
    - `POST /engine/config`
  - added in-panel command:
    - `/config [--dry-run] key=value ...`
  - supported config keys include:
    - `runtime_profile`
    - `engine_preset`
    - scheduler limits
    - prefix-cache policy knobs
  - config commands refresh the panel from `GET /engine/ui` after the config
    request completes
  - invalid keys and invalid numeric values are rejected in the panel before
    any HTTP request is sent
  - added tests for direct config calls, in-panel dry-run/apply behavior, and
    invalid key validation
  - M37 conclusion: the Dax prompt panel can now tune runtime profiles, engine
    presets, scheduler policy, and prefix-cache policy without leaving the TUI.
- Completed M38 interactive help and compact status:
  - added in-panel commands:
    - `/help`
    - `/status`
  - `/help` appends the current interactive command surface to the transcript
  - `/status` appends a compact status block with:
    - loaded/GPU/warm state
    - model
    - runtime profile and engine preset
    - cache strategy/population mode
    - active/queued/failure counters
    - available profiles
  - added tests for help discoverability and compact status rendering
  - M38 conclusion: the growing Dax operator surface is now discoverable from
    inside the prompt panel itself.
- Completed M39 interactive transcript search:
  - added in-panel command:
    - `/find <text>`
  - searches the current interactive transcript after stripping terminal color
    sequences
  - returns compact recent matches or an explicit no-match message
  - added tests for prompt/response transcript matches and no-match behavior
  - M39 conclusion: longer Dax MLX operator sessions can now recover prior
    prompts, responses, and command evidence without exporting or leaving the
    prompt panel.
- Completed M40 interactive prompt history and recall:
  - added in-panel commands:
    - `/history`
    - `/again [n]`
  - prompt history records natural-language prompts, not operator commands
  - `/history` appends recent prompts with stable history numbers
  - `/again` reruns the latest prompt, and `/again <n>` reruns the numbered
    prompt from history
  - invalid recall arguments produce a usage message instead of attempting
    generation
  - added tests for history listing, numbered replay, and invalid recall
  - M40 conclusion: longer Dax MLX sessions can rerun useful prompts without
    relying on terminal arrow-key behavior.
- Completed M41 interactive diagnostic snapshot export:
  - added in-panel command:
    - `/snapshot [path]`
  - default snapshot path is a timestamped `mlx-engine-snapshot-*.json` file in
    the current working directory
  - snapshot JSON includes:
    - export timestamp
    - artifact kind
    - mode and max token cap
    - compact status lines
    - raw engine UI snapshot
    - runtime profile catalog
    - prompt history
    - plain-text transcript
  - added tests for snapshot file creation, status capture, prompt history, raw
    snapshot payload, and transcript payload
  - M41 conclusion: Dax can now produce a single debugging artifact that
    captures engine state and session context without leaving the prompt panel.
- Completed M42 attach-ready snapshot summary:
  - `/snapshot [path]` now writes a Markdown sidecar next to the JSON snapshot
  - `.json` paths produce same-stem `.md` summaries
  - non-JSON paths produce `<path>.md` summaries
  - Markdown summary includes:
    - export timestamp
    - mode and max token cap
    - compact status lines
    - recent prompt history
    - recent transcript excerpt
  - added tests for Markdown sidecar creation and summary content
  - M42 conclusion: snapshot artifacts are now readable and attach-ready without
    requiring someone to inspect the raw JSON first.
- Completed M43 redacted snapshot export:
  - extended in-panel snapshot command:
    - `/snapshot --redact [path]`
  - redacted snapshots preserve:
    - compact status lines
    - raw engine UI snapshot
    - runtime profile catalog
    - artifact metadata
  - redacted snapshots replace prompt history and transcript content with
    deterministic redaction markers
  - Markdown sidecar marks redacted snapshots with `Redacted: yes`
  - added tests verifying prompt and response content are excluded from both
    JSON and Markdown outputs
  - M43 conclusion: Dax snapshot artifacts can now be shared more safely when
    prompts or model responses may contain sensitive content.
- Completed M44 safe snapshot export:
  - extended in-panel snapshot command:
    - `/snapshot --safe [path]`
  - safe snapshots imply prompt/transcript redaction
  - safe snapshots also scrub local filesystem-style model paths from:
    - compact status lines
    - raw engine UI snapshot payload
    - runtime profile catalog
    - Markdown sidecar
  - JSON payloads now include `safe=true` for safe exports
  - Markdown sidecars mark safe snapshots with `Safe: yes`
  - added tests verifying local model paths and prompt/response content are
    excluded from JSON and Markdown outputs
  - M44 conclusion: Dax can now produce diagnostics suitable for external
    tickets or shared handoffs without leaking local model paths.
- Completed M45 raw snapshot omission:
  - extended in-panel snapshot command:
    - `/snapshot --no-raw [path]`
  - `--no-raw` can be combined with `--safe` for compact ticket artifacts
  - JSON payloads now include `include_raw=false` when raw engine payloads are
    omitted
  - Markdown sidecars mark omitted raw snapshots with `Raw snapshot: no`
  - no-raw snapshots preserve:
    - artifact metadata
    - compact status lines
    - runtime profile catalog
    - prompt history or prompt redaction markers
    - transcript or transcript redaction markers
  - added tests verifying `--safe --no-raw` excludes the raw engine snapshot,
    local model paths, prompt content, and response content from JSON and
    Markdown outputs
  - M45 conclusion: Dax can now create compact, attach-safe diagnostics for
    tickets and handoffs without carrying the full raw engine state payload.
- Completed M46 transcript view controls:
  - added in-panel commands:
    - `/view recent`
    - `/view all`
    - `/clear`
  - default rendering remains a recent transcript window for long sessions
  - `/view all` renders the full current transcript in the panel
  - `/view recent` restores the compact recent transcript window
  - `/clear` clears the current visible/exported transcript while preserving
    prompt history for `/history` and `/again`
  - added tests for recent/all rendering, invalid view usage, clear behavior,
    and prompt-history preservation after clear
  - M46 conclusion: long Dax MLX operator sessions are now easier to manage
    without losing prompt recall.
- Completed M47 snapshot presets:
  - extended in-panel snapshot command with preset forms:
    - `/snapshot ticket [path]`
    - `/snapshot internal [path]`
    - `/snapshot full [path]`
  - `ticket` expands to `--safe --no-raw`
  - `internal` expands to `--redact`
  - `full` preserves the full raw snapshot behavior
  - JSON payloads now include `preset` when a preset is used
  - Markdown sidecars include the selected preset or `custom`
  - added tests verifying ticket, internal, and full preset behavior
  - M47 conclusion: operators can choose the right diagnostic privacy level
    without remembering low-level flag combinations.
- Completed M48 generation timing feedback:
  - every completed Dax MLX prompt now appends a timing line with:
    - elapsed milliseconds
    - completion tokens per second when completion-token usage is available
  - usage counters remain visible when returned by the engine
  - timing works without requiring any engine API changes
  - added tests verifying usage and timing lines are recorded in the
    interactive transcript
  - M48 conclusion: interactive MLX sessions now provide immediate performance
    feedback during prompt-processing and generation tuning.
- Completed M49 structured generation metrics:
  - Dax now stores per-generation metrics separately from transcript text:
    - generation index
    - elapsed milliseconds
    - completion tokens per second, or `null` when unavailable
    - usage counters when returned by the engine
  - `/export` includes `generation_metrics`
  - `/snapshot` includes `generation_metrics`
  - Markdown snapshot sidecars include a recent generation metrics section
  - metric records intentionally omit prompt text so ticket/safe snapshots can
    carry performance evidence without leaking prompt content
  - added tests verifying structured metrics are exported and summarized
  - M49 conclusion: Dax diagnostic artifacts now carry machine-readable
    performance evidence for later comparison.
- Completed M50 live metrics review:
  - added in-panel command:
    - `/metrics`
  - `/metrics` appends:
    - total completed generation count
    - average completion tokens per second when known
    - recent generation metric rows with elapsed time, throughput, and usage
  - no prompt text is included in metric rows
  - added tests verifying the live metrics summary appears after a generation
  - M50 conclusion: operators can inspect recent performance evidence without
    leaving the Dax MLX prompt panel or exporting a snapshot.
- Completed M51 metrics window controls:
  - extended in-panel metrics command:
    - `/metrics`
    - `/metrics all`
    - `/metrics clear`
  - default `/metrics` shows a recent metrics window
  - `/metrics all` shows every recorded metric in the current session
  - `/metrics clear` resets metric tracking without clearing transcript or
    prompt history
  - invalid metrics arguments return usage guidance
  - added tests for all-metrics rendering, invalid usage, and metric reset
  - M51 conclusion: operators can manage long-session performance evidence
    without restarting the Dax MLX panel.
- Completed M52 generation metrics summary:
  - Dax exports and snapshots now include `generation_metrics_summary`
  - summary includes:
    - generation count
    - elapsed milliseconds min/average/max
    - completion tokens-per-second min/average/max when known
  - Markdown snapshot sidecars include the same aggregate summary above recent
    metric rows
  - summary handles missing throughput by using `null`/`unknown` instead of
    fabricating a value
  - added tests verifying structured summary fields and Markdown summary output
  - M52 conclusion: Dax artifacts now support quick benchmark comparison
    without parsing every generation metric row.
- Completed M53 metrics-only export:
  - extended in-panel metrics command:
    - `/metrics export [path]`
  - exports a compact JSON artifact with:
    - `kind=mlx-engine-generation-metrics`
    - mode and max token cap
    - `generation_metrics`
    - `generation_metrics_summary`
  - metrics-only exports intentionally omit prompt history and transcript
  - default output path is `mlx-engine-metrics-*.json`
  - added tests verifying metrics-only export content and absence of
    prompt/transcript payloads
  - M53 conclusion: Dax can now produce lightweight performance evidence
    artifacts without full session or engine snapshot payloads.
- Completed M54 resident benchmark evidence:
  - ran the resident benchmark harness against the live MLX server on
    `http://127.0.0.1:8773`
  - live engine reported:
    - model:
      `/Volumes/StudioStackSSD4TB/Development/LLM/lmstudio/models/unsloth/Qwen3.6-35B-A3B-UD-MLX-4bit`
    - device: `Device(gpu, 0)`
    - engine preset: `custom`
    - prefix cache population: `sync`
  - command used:
    - `python3 benchmarks/python/resident_benchmark_harness.py --base-url http://127.0.0.1:8773 --output-jsonl m54-dax-evidence-resident-benchmark.jsonl --reset-cache --requests 3 --prefix-repeats 8 --max-tokens 6 --policy memory_saver`
  - observed request phases:
    - `full_prefill`: 247 actual prefill tokens, 87728.97 ms service time
    - `cache_create`: 7.5 mean actual prefill tokens, 434.44 ms mean service
      time, 183.32 ms mean cache prepare time
    - `cache_hit`: 8 actual prefill tokens, 219.72 ms service time, 0.21 ms
      cache prepare time
  - M54 conclusion: the biggest measured prompt-processing speedup is already
    coming from prefix-cache reuse; the next meaningful optimization target is
    reducing cache creation overhead and making cache-hit paths easier to
    trigger consistently from real operator workflows.
- Completed M55 derived benchmark comparison:
  - extended `benchmarks/python/compare_resident_benchmarks.py` with derived
    per-artifact cache-reuse analysis
  - new derived columns:
    - `service_speedup_vs_full_prefill`
    - `prefill_reduction_vs_full_prefill`
    - `cache_prepare_share`
  - verified against the M54 artifact:
    - `cache_create`: `201.94x` service speedup, `97.0%` prefill reduction,
      `42.2%` cache prepare share
    - `cache_hit`: `399.27x` service speedup, `96.8%` prefill reduction,
      `0.1%` cache prepare share
  - verified against a deterministic synthetic JSONL fixture in `/private/tmp`
  - M55 conclusion: benchmark comparison now surfaces the exact prompt
    processing speedup and cache-creation overhead that matter for the next
    optimization pass.
- Completed M56 cache-reuse regression gate:
  - extended `benchmarks/python/resident_regression_gate.py` with:
    - `--min-cache-hit-speedup-vs-full-prefill`
    - `--min-cache-hit-prefill-reduction-vs-full-prefill`
  - default gate thresholds require:
    - cache-hit service speedup at least `4.0x` versus full prefill
    - cache-hit actual-prefill-token reduction at least `0.90` versus full
      prefill
  - wired both thresholds through
    `benchmarks/python/run_resident_regression_suite.py`
  - validation passed:
    - `python3 -m py_compile benchmarks/python/resident_regression_gate.py benchmarks/python/run_resident_regression_suite.py`
    - synthetic PASS fixture produced `gate_result PASS`
    - synthetic FAIL fixture produced failures for both derived cache-hit gates
    - regression suite help exposes both new threshold flags
    - `git diff --check`
  - M56 conclusion: cache-hit regressions can now fail automatically even when
    absolute latency thresholds are relaxed.
- Completed M57 cache-create regression gate:
  - extended `benchmarks/python/resident_regression_gate.py` with:
    - `--max-cache-create-service-ms`
    - `--max-cache-create-prepare-share`
  - default gate thresholds require:
    - cache-create mean service time at most `750 ms`
    - cache-create cache-prepare share at most `0.80`
  - wired both thresholds through
    `benchmarks/python/run_resident_regression_suite.py`
  - validation passed:
    - `python3 -m py_compile benchmarks/python/resident_regression_gate.py benchmarks/python/run_resident_regression_suite.py`
    - synthetic PASS fixture produced `gate_result PASS`
    - synthetic cache-create overhead fixture failed both new checks
    - M54 real cache artifact passed with
      `cache_create.mean_service_request_ms=434.44` and
      `cache_create.cache_prepare_share=0.422`
    - regression suite help exposes both new threshold flags
    - `git diff --check`
  - M57 conclusion: cache-hit quality and cache-create cost are now separately
    protected, which gives the next prompt-processing optimization pass a
    concrete gate.
- Completed M58 machine-readable gate reports:
  - added `--output-json PATH` to
    `benchmarks/python/resident_regression_gate.py`
  - report includes:
    - `type=resident_regression_gate`
    - `verdict`
    - `cache_artifact`
    - `prefill_artifact`
    - structured `checks`
    - `failures`
  - scalar checks include label, verdict, actual, operator, and threshold
  - row-count checks include label, verdict, passed rows, and total rows
  - `benchmarks/python/run_resident_regression_suite.py` now writes
    `resident-regression-gate-<tag>.json` beside the benchmark JSONL artifacts
  - validation passed:
    - `python3 -m py_compile benchmarks/python/resident_regression_gate.py benchmarks/python/run_resident_regression_suite.py`
    - synthetic PASS report contained `verdict=PASS`, `11` checks, `0`
      failures
    - synthetic FAIL report contained `verdict=FAIL`, `11` checks, `2`
      failures
    - failing gate still wrote the JSON report before returning non-zero
    - `git diff --check`
  - M58 conclusion: resident regression evidence is now directly consumable by
    CI, Dax, Redmine, or other operator tooling without scraping stdout.
- Completed M59 regression suite manifest:
  - `benchmarks/python/run_resident_regression_suite.py` now writes
    `resident-regression-suite-<tag>.json`
  - manifest includes:
    - `type=resident_regression_suite`
    - `verdict`
    - `tag`
    - `base_url`
    - `output_dir`
    - artifact entries for cache, prefill, gate, and cold-start outputs
    - executed step flags
    - embedded `gate_report` when the gate artifact exists
  - validation passed:
    - skipped-runtime manifest produced `verdict=PASS`, all runtime steps
      disabled, and `gate_report=null`
    - gate-enabled synthetic manifest produced `verdict=PASS`,
      `artifacts.gate.exists=true`, embedded gate report `verdict=PASS`, `11`
      checks, and `0` failures
    - `python3 -m py_compile benchmarks/python/run_resident_regression_suite.py benchmarks/python/resident_regression_gate.py`
    - `git diff --check`
  - M59 conclusion: suite runs now produce one compact machine-readable index
    for Dax, Redmine, CI, or future app surfaces to attach and compare.
- Completed M60 failure suite manifest:
  - `benchmarks/python/run_resident_regression_suite.py` now keeps active suite
    context during child subprocess execution
  - if a child subprocess fails, the suite writes
    `resident-regression-suite-<tag>.json` with:
    - `verdict=FAIL`
    - artifact paths and existence flags
    - executed step flags
    - embedded `gate_report` when available
    - failure type, command, and return code
  - suite exits with the child return code without a Python traceback
  - validation passed:
    - skipped-runtime PASS manifest still wrote `failure=null`
    - forced synthetic gate failure wrote `verdict=FAIL`,
      `failure.type=subprocess`, `failure.returncode=1`,
      `gate_report.verdict=FAIL`, `2` gate failures, and
      `artifacts.gate.exists=true`
    - `python3 -m py_compile benchmarks/python/run_resident_regression_suite.py benchmarks/python/resident_regression_gate.py`
    - `git diff --check`
  - M60 conclusion: failed suite runs now leave durable machine-readable
    evidence for CI, Redmine, Dax, or future app surfaces.
- Completed M61 suite manifest summarizer:
  - added `benchmarks/python/summarize_resident_suite_manifest.py`
  - summarizer prints stable line-based sections:
    - `suite`
    - `steps`
    - `artifact`
    - `gate`
    - `gate_failure`
    - `failure`
  - validation passed:
    - PASS manifest summary printed `suite PASS`, disabled steps, artifact
      existence flags, and `gate none`
    - FAIL manifest summary printed `suite FAIL`, `gate FAIL checks 11 failures
      2`, both cache-create gate failures, and the failing subprocess command
    - `python3 -m py_compile benchmarks/python/summarize_resident_suite_manifest.py benchmarks/python/run_resident_regression_suite.py benchmarks/python/resident_regression_gate.py`
    - `git diff --check`
  - M61 conclusion: operators and automation can inspect suite manifests
    without parsing raw JSON manually.
- Completed M62 suite summary CI exit:
  - added `--fail-on-fail` to
    `benchmarks/python/summarize_resident_suite_manifest.py`
  - default summary behavior still exits `0` for valid manifests, including
    failed suite manifests
  - `--fail-on-fail` exits `1` when the suite manifest verdict is not `PASS`
  - validation passed:
    - PASS manifest with `--fail-on-fail` exited `0`
    - FAIL manifest without `--fail-on-fail` exited `0`
    - FAIL manifest with `--fail-on-fail` exited `1`
    - `python3 -m py_compile benchmarks/python/summarize_resident_suite_manifest.py`
    - `git diff --check`
  - M62 conclusion: the manifest summarizer can now be used directly as a CI
    assertion step while remaining safe for manual inspection by default.
- Completed M63 inline suite manifest summary:
  - added `--print-manifest-summary` to
    `benchmarks/python/run_resident_regression_suite.py`
  - refactored `benchmarks/python/summarize_resident_suite_manifest.py` so the
    suite reuses the same formatter
  - success path prints the manifest summary before the existing
    `suite_result PASS` line when the flag is set
  - subprocess failure path prints the failure manifest summary after the
    existing `suite_result FAIL` line and exits with the child return code
  - validation passed:
    - PASS skipped-runtime run printed `suite PASS`, artifact existence flags,
      and `gate none`
    - forced synthetic gate failure exited `1` and printed `suite FAIL`,
      `gate FAIL checks 11 failures 2`, both cache-create failures, and the
      failing subprocess command
    - `python3 -m py_compile benchmarks/python/summarize_resident_suite_manifest.py benchmarks/python/run_resident_regression_suite.py benchmarks/python/resident_regression_gate.py`
    - `git diff --check`
  - M63 conclusion: a single suite command can now produce both durable JSON
    evidence and immediately readable terminal evidence.
- Completed M64 real suite evidence:
  - ran `benchmarks/python/run_resident_regression_suite.py` against the live
    server at `http://127.0.0.1:8773`
  - live model:
    `/Volumes/StudioStackSSD4TB/Development/LLM/lmstudio/models/unsloth/Qwen3.6-35B-A3B-UD-MLX-4bit`
  - suite tag: `m64-qwen-a3b`
  - runtime preset applied by the harness: `sync-safe`
  - optional long stress probes were skipped for this bounded evidence run:
    generated-cache safety, generated-cache edges, concurrent cancel pressure,
    and async cache priority
  - artifacts:
    - `artifacts/m64-real-suite/resident-benchmark-sync-safe-m64-qwen-a3b.jsonl`
      local ignored raw benchmark JSONL
    - `artifacts/m64-real-suite/resident-prefill-isolation-sync-safe-m64-qwen-a3b.jsonl`
      local ignored raw prefill JSONL
    - `artifacts/m64-real-suite/resident-regression-gate-m64-qwen-a3b.json`
    - `artifacts/m64-real-suite/resident-regression-suite-m64-qwen-a3b.json`
  - measured summary:
    - `full_prefill`: `4256.93 ms`, `246` actual prefill tokens
    - `cache_create`: `420.22 ms`, `7.5` mean actual prefill tokens
    - `cache_hit`: `236.74 ms`, `8` actual prefill tokens
    - `prefill_cold`: `386.06 ms`, `252` actual prefill tokens
    - `prefill_warm`: `351.43 ms`, `252` actual prefill tokens
  - derived comparison:
    - `cache_create`: `10.13x` service speedup, `97.0%` prefill reduction,
      `43.9%` cache prepare share
    - `cache_hit`: `17.98x` service speedup, `96.7%` prefill reduction,
      `0.1%` cache prepare share
  - gate result:
    - suite verdict `PASS`
    - gate verdict `PASS`
    - `11` checks
    - `0` failures
  - M64 conclusion: the benchmark/gate/manifest pipeline works against the live
    Qwen resident engine, and prefix-cache reuse remains the confirmed
    prompt-processing win.
- Completed M65 evidence package helper:
  - added `benchmarks/python/package_resident_suite_evidence.py`
  - helper validates `resident_regression_suite` manifests
  - helper copies the suite manifest and every existing artifact referenced by
    the manifest into a handoff directory
  - helper writes `resident-suite-evidence-index.json` with copied files and
    missing artifact paths
  - validation against M64 passed:
    - command copied `4` files and recorded `1` missing disabled cold-start
      artifact
    - copied cache JSONL, prefill JSONL, gate JSON, and suite JSON
    - index reported `resident_suite_evidence_package PASS m64-qwen-a3b`
    - `python3 -m py_compile benchmarks/python/package_resident_suite_evidence.py`
    - `git diff --check`
  - M65 conclusion: M64 evidence can now be packaged into one handoff directory
    for Redmine, Dax, CI, or future app surfaces.
- Completed M66 Dax suite manifest ingestion:
  - updated Dax in
    `/Users/jeffreycruz/Development/AI_AGENTS/dax-stereo`
  - Dax commit: `3f967990 Add MLX resident suite manifest summary`
  - added Dax helpers:
    - `readResidentSuiteManifest(path)`
    - `formatResidentSuiteManifestSummary(manifest)`
  - added Dax TUI command:
    `/bench summary <resident-regression-suite.json>`
  - the Dax panel now shows suite verdict, tag, base URL, executed steps,
    artifact paths, gate verdict, gate failure count, individual gate failures,
    and failing subprocess details
  - validation passed:
    - `npm --prefix packages/coding-agent test -- mlx-engine-status.test.ts`
    - `27` focused tests passed
    - Dax pre-commit checks passed: Biome, `tsgo --noEmit`,
      browser-smoke check, and web-ui checks
  - M66 conclusion: resident suite evidence is now consumable inside the Dax
    operator panel rather than only by Python scripts.
- Completed M67 Dax suite runner:
  - updated Dax in
    `/Users/jeffreycruz/Development/AI_AGENTS/dax-stereo`
  - Dax commit: `36252308 Add MLX resident suite runner to Dax`
  - added Dax helper:
    `runResidentRegressionSuite(options)`
  - added Dax TUI command:
    `/bench run <mlx-worktree> [output-dir] [tag]`
  - the command invokes
    `benchmarks/python/run_resident_regression_suite.py` with bounded
    M64-style defaults, uses the active panel base URL, writes the suite
    artifacts, then reads and displays the generated suite manifest
  - validation passed:
    - `npm --prefix packages/coding-agent test -- mlx-engine-status.test.ts`
    - `28` focused tests passed
    - Dax pre-commit checks passed: Biome, `tsgo --noEmit`,
      browser-smoke check, and web-ui checks
  - M67 conclusion: Dax can now run the resident regression suite and summarize
    the result from the same operator panel.
- Completed M68 cache-create optimization probe:
  - added `benchmarks/python/cache_create_optimization_probe.py`
  - the probe reads resident benchmark or prefix-latency JSONL and computes:
    full-prefill service mean, cache-create service mean, cache-create prepare
    share, cache-hit service mean, cache-hit speedup, and estimated deferred
    cache-create service time
  - wrote real M64 analysis:
    `artifacts/m64-real-suite/cache-create-optimization-m64-qwen-a3b.json`
  - validation passed:
    - `python3 -m py_compile benchmarks/python/cache_create_optimization_probe.py`
    - synthetic prepare-dominated sample:
      `cache_create_probe PASS prepare_share 0.703 hit_speedup 3.211`
    - M64 real-suite sample with calibrated threshold:
      `cache_create_probe PASS prepare_share 0.439 hit_speedup 17.981 deferred_service_ms 235.55`
    - `python3 -m json.tool artifacts/m64-real-suite/cache-create-optimization-m64-qwen-a3b.json`
  - M68 conclusion: cache-create overhead is now independently measurable, so
    future async/deferred cache-build work can be gated separately from cache
    hit correctness.
- Completed M69 runtime profile comparison suite:
  - added `benchmarks/python/runtime_profile_comparison_suite.py`
  - the suite runs `resident_benchmark_harness.py` once per requested engine
    preset, then runs `cache_create_optimization_probe.py` against each
    per-preset benchmark artifact
  - writes `runtime-profile-comparison-<tag>.json` with commands, artifact
    paths, return codes, and embedded cache-create probe reports when present
  - validation passed:
    - `python3 -m py_compile benchmarks/python/runtime_profile_comparison_suite.py`
    - dry-run command emitted benchmark/probe commands for
      `sync-safe,async-experimental`
    - dry-run manifest passed `python3 -m json.tool`
  - M69 conclusion: runtime preset comparisons now have a repeatable suite
    entry point instead of being ad hoc benchmark invocations.
- Completed M70 threshold calibration:
  - added `benchmarks/python/calibrate_resident_thresholds.py`
  - the helper reads one or more `resident_regression_gate` reports and emits
    calibrated `run_resident_regression_suite.py` threshold flags
  - wrote M64 calibration:
    `artifacts/m64-real-suite/resident-threshold-calibration-m64-qwen-a3b.json`
  - M64-derived thresholds include:
    - `--max-cache-hit-service-ms 295.929324`
    - `--max-cache-create-service-ms 525.27586`
    - `--max-cache-create-prepare-share 0.549328`
    - `--min-cache-hit-speedup-vs-full-prefill 13.485895`
  - validation passed:
    - `python3 -m py_compile benchmarks/python/calibrate_resident_thresholds.py`
    - calibration command against the M64 gate report
    - `python3 -m json.tool artifacts/m64-real-suite/resident-threshold-calibration-m64-qwen-a3b.json`
  - M70 conclusion: regression thresholds can now be recalibrated from measured
    evidence with explicit headroom instead of being hand-tuned constants.
