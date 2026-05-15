# Fast MLX Engine Plan

## Current Conclusion

The `gpt-oss-20b-MXFP4-Q8` checkpoint is valid and performs well on Metal once
the model is resident and prompt shapes are warm. The main engine problem is not
raw MLX prefill capability; it is avoiding cold-start costs and choosing the
right prefill policy for the current memory/performance target.

## Runtime Policy

- Keep the model loaded across requests.
- Warm representative prompt shapes before accepting traffic.
- Use an engine profile generated from local measurements.
- Default to the measured throughput policy unless memory pressure requires a
  lower-memory policy.
- Use an automatic short-prompt policy: small prompts can prefer the lower
  chunk size because the overhead of large prefill chunks can dominate.

For the current `gpt-oss-20b-MXFP4-Q8` profile:

| Policy | prefill_step_size | prompt_tps | peak_memory_gb |
| --- | ---: | ---: | ---: |
| throughput_default | 2048 | 2082.167 | 13.019 |
| memory_saver | 512 | 1811.394 | 12.652 |
| balanced | 2048 | 2082.167 | 13.019 |

The prototype service currently maps `policy=auto` to:

- `memory_saver` for prompts below 512 estimated tokens.
- `throughput_default` for prompts at or above 512 estimated tokens.

## Engine Components

- `ModelResidentWorker`: loads model once and owns the MLX model/process lifetime.
- `ShapeWarmer`: runs synthetic prompts for common prompt lengths after load.
- `PrefillPolicy`: reads the generated JSON profile and selects chunk size.
- `AutoTuner`: benchmarks candidate chunk sizes per model and writes the profile.
- `RequestRouter`: applies policy per request based on prompt length and memory mode.
- `PrefixOpportunityTracker`: records recent prompt token sequences and measures
  repeated-prefix opportunity before real KV-cache reuse is implemented.

## Implemented Prototype Slice

The resident Python service around `mlx_lm` now:

- Starts once with a model path.
- Loads the model and selected prefill profile.
- Discovers a profile automatically when `--profile` is omitted.
- Warms configured prompt shapes.
- Accepts JSON requests over localhost.
- Reports load time, prompt time, generation time, tokens/sec, and peak memory.
- Exposes request metrics at `/metrics`.
- Exposes OpenAI-style `/v1/completions` and `/v1/chat/completions` endpoints.
- Reports prefix-cache opportunity fields on each request:
  - `prompt_hash`
  - `tokenized_prompt_hash`
  - `longest_prefix_match_tokens`
  - `prefix_reuse_ratio`
  - `estimated_recompute_tokens`
  - `cache_candidate`

This will separate engine behavior from one-shot scripts and make LM Studio-style
latency issues easier to reproduce.

## Packaged Service

The resident service now lives in the `mlx_engine` package:

- stable service implementation: `mlx_engine/resident_service.py`
- package boundary note: `mlx_engine/README.md`
- package marker: `mlx_engine/__init__.py`
- compatibility wrapper: `benchmarks/python/resident_mlx_service.py`
- CLI wrapper: `bin/mlx-engine`

The old benchmark path remains available so existing harnesses and tmux commands
continue to work while the engine surface is cleaned up.

Packaged command:

```bash
bin/mlx-engine serve --model "$MODEL" --port 8765
bin/mlx-engine ready --base-url http://127.0.0.1:8765 --require-gpu --require-warmup
bin/mlx-engine smoke --base-url http://127.0.0.1:8765
bin/mlx-engine correctness --base-url http://127.0.0.1:8765
bin/mlx-engine suite --base-url http://127.0.0.1:8765 --tag cli-suite-full
```

Package-path validation:

```bash
timeout 20s bin/mlx-engine serve \
  --model /Volumes/StudioStackSSD4TB/Development/LLM/lmstudio/models/mlx-community/gpt-oss-20b-MXFP4-Q8 \
  --port 8771
```

Evidence:

```text
INFO:     Started server process [57278]
INFO:     Uvicorn running on http://127.0.0.1:8771
INFO:     Finished server process [57278]
```

Post-run listener check confirmed port `8771` was clear.

Packaged regression-suite validation:

```text
gate_check PASS cache_hit.mean_service_request_ms 178.019 <= 250.0
gate_check PASS cache_hit.mean_actual_prefill_tokens 8.0 <= 16.0
gate_check PASS prefill_warm.mean_service_request_ms 415.592 <= 550.0
gate_check PASS prefill_warm.mean_actual_prefill_tokens 586.0 >= 500.0
gate_result PASS
generated_prefix_cache_safety_result PASS
suite_result PASS resident-benchmark-sync-safe-cli-suite-full.jsonl resident-prefill-isolation-sync-safe-cli-suite-full.jsonl generated_cache_safety= True
```

Source hygiene:

- Local benchmark outputs are ignored via `.gitignore`:
  `*.jsonl`, `resident-*.log`, and `resident-service-*.log`.
- Static report JSON and profile JSON remain visible because they are
  source-adjacent evidence/configuration rather than ephemeral run logs.

launchd packaging:

- Template: `packaging/launchd/com.jecruz.mlx-engine.plist.template`.
- Notes: `packaging/launchd/README.md`.
- The template runs `bin/mlx-engine serve` with `--warmup-mode async` and
  `--require-gpu`.
- Use `bin/mlx-engine ready --require-gpu --require-warmup` as the client gate
  when warmed latency matters.

Run it with:

```bash
MODEL="/Volumes/StudioStackSSD4TB/Development/LLM/lmstudio/models/mlx-community/gpt-oss-20b-MXFP4-Q8"
PROFILE="/Users/jeffreycruz/Development/LLM_INFERENCE/mlx/.worktrees/prompt-processing-bench/gpt-oss-20b-MXFP4-Q8-prefill-profile.json"
benchmarks/python/run_resident_service.sh "$MODEL" "$PROFILE" 8765
```

Or rely on profile auto-discovery:

```bash
MODEL="/Volumes/StudioStackSSD4TB/Development/LLM/lmstudio/models/mlx-community/gpt-oss-20b-MXFP4-Q8"
benchmarks/python/run_resident_service.sh "$MODEL" 8765
```

Smoke test:

```bash
curl -sS http://127.0.0.1:8765/health
curl -sS http://127.0.0.1:8765/metrics
curl -sS -X POST http://127.0.0.1:8765/generate \
  -H 'content-type: application/json' \
  -d '{"prompt":"Explain why resident MLX inference is faster than one-shot loading.","max_tokens":32,"policy":"throughput_default"}'
curl -sS -X POST http://127.0.0.1:8765/v1/completions \
  -H 'content-type: application/json' \
  -d '{"model":"local-gpt-oss","prompt":"Name one MLX engine metric:","max_tokens":6,"policy":"auto"}'
curl -sS -X POST http://127.0.0.1:8765/v1/chat/completions \
  -H 'content-type: application/json' \
  -d '{"model":"local-gpt-oss","messages":[{"role":"user","content":"Reply with one word: ready"}],"max_tokens":4,"policy":"auto"}'
```

`policy` can be `auto`, `throughput_default`, `balanced`, or `memory_saver`.

M6 prefix-instrumentation smoke:

```bash
cd /Users/jeffreycruz/Development/LLM_INFERENCE/mlx/.worktrees/prompt-processing-bench
MODEL="/Volumes/StudioStackSSD4TB/Development/LLM/lmstudio/models/mlx-community/gpt-oss-20b-MXFP4-Q8"
benchmarks/python/run_resident_service.sh "$MODEL" 8765
bin/mlx-engine smoke --base-url http://127.0.0.1:8765
```

Expected additional smoke line after the streaming checks:

```text
prefix <first_cache_candidate> <longest_prefix_match_tokens> <prefix_reuse_ratio> <second_cache_candidate>
```

The second related request should report `longest_prefix_match_tokens > 0`.

Validated service behavior:

- `/health` reports `Device(gpu, 0)` and the configured warm-up shapes.
- `/profile` returns the generated prefill profile.
- `/generate` returns full accumulated streamed text.
- `policy=auto` selected `prefill_step_size=512` for a 110-token request.
- `/metrics` returns total requests, failures, token totals, mean run time, and recent request summaries.
- `/v1/completions` returns OpenAI-style text completion response shape plus `engine_metrics`.
- `/v1/chat/completions` renders the tokenizer chat template when available and returns OpenAI-style chat response shape plus `engine_metrics`.
- `stream=true` on `/v1/completions` and `/v1/chat/completions` returns OpenAI-style server-sent events with `[DONE]`.
- `stream=true` on `/generate` returns newline-delimited JSON events.
- `/engine` returns lifecycle metadata, loaded policy names, warm-up state, and metrics.
- `/engine/reload` loads a replacement resident engine and swaps it in after the old engine is idle.
- `benchmarks/python/smoke_resident_service.py` validates health, raw generation, completion, chat completion, and metrics.

Current M6 validation status:

- Syntax validation passed:

```bash
python3 -m py_compile benchmarks/python/resident_mlx_service.py benchmarks/python/smoke_resident_service.py
```

- Full GPU smoke could not be run from the current Codex process because access
  to the external model volume was denied:

```text
PermissionError: [Errno 1] Operation not permitted: '/Volumes/StudioStackSSD4TB/Development/LLM/lmstudio/models/mlx-community/gpt-oss-20b-MXFP4-Q8/config.json'
```

- Direct import-based tracker validation is also blocked in the sandbox because
  importing `mlx.core` crashes while initializing the Metal device.

- GPU shell validation passed after the user ran the updated smoke test:

```text
health True Device(gpu, 0) /Users/jeffreycruz/Development/LLM_INFERENCE/mlx/.worktrees/prompt-processing-bench/gpt-oss-20b-MXFP4-Q8-prefill-profile.json 0
engine 0 True balanced,memory_saver,throughput_default
generate req_60c6d0caedc841e88558e550901a4d5a memory_saver 512 9 8 length
completion text_completion length 13 memory_saver
chat chat.completion assistant 77 512
stream_completion 5 True
stream_chat 6 True
prefix False 38 0.95 True
metrics 7 7 0 7 2
unload False 1 /Volumes/StudioStackSSD4TB/Development/LLM/lmstudio/models/mlx-community/gpt-oss-20b-MXFP4-Q8
reload 1 Device(gpu, 0) True [64]
```

Interpretation:

- The second related request detected `38` shared prefix tokens.
- `prefix_reuse_ratio` was `0.95`.
- The first related request was not cache-eligible because no prior prefix had
  been recorded.
- The second related request was cache-eligible.
- Metrics recorded `2` cache-candidate requests across the smoke run.

M6 agent-style repeated-prefix sweep:

```bash
python3 benchmarks/python/prefix_opportunity_sweep.py \
  --base-url http://127.0.0.1:8765 \
  --output-jsonl prefix-opportunity-sweep.jsonl
```

Observed output:

```text
prefix_sweep 1 206 0 0.0 False
prefix_sweep 2 205 194 0.946 True
prefix_sweep 3 205 194 0.946 True
prefix_sweep 4 206 194 0.942 True
prefix_sweep 5 207 194 0.937 True
prefix_sweep 6 204 194 0.951 True
summary 6 5 0.787 prefix-opportunity-sweep.jsonl
```

Metrics after the sweep:

```text
total_requests=6
successful_requests=6
failed_requests=0
total_prompt_tokens=1233
total_generation_tokens=24
total_prefix_match_tokens=970
cache_candidate_requests=5
mean_prefix_match_tokens=161.67
```

Interpretation:

- The first request paid full prefill and established the recent-prefix record.
- Every subsequent agent-style request detected a `194` token shared prefix.
- Reuse ratios after the first request were `0.937` through `0.951`.
- This confirms coding-agent style prompts have enough repeated prefix structure
  to justify implementing real cache reuse next.

## Conservative Prefix Cache Reuse Prototype

Implemented first pass:

- Detects safe shorter-prefix matches from the recent prompt tracker.
- Builds a reusable `mlx-lm` prompt cache for the matched prefix with
  `generate_step(..., max_tokens=0)`.
- Stores prefix caches in a bounded in-memory LRU.
- Copies cached prefix state per request before passing it to `stream_generate`.
- Sends only the uncached suffix tokens through the generation path when reuse is
  enabled.
- Falls back to full prompt processing when no cache candidate exists, when the
  match is empty, or when the full prompt is already matched.

New evidence fields:

- `cache_reuse_enabled`
- `cache_hit`
- `cache_created`
- `cached_prefix_tokens`
- `actual_prefill_tokens`
- `prefix_kv_cache` in `/health` and `/engine`

Validation state:

- Compile validation passes for the resident service, smoke client, and prefix
  sweep.
- Live GPU validation should use tmux session `codex-mlx-server` for the
  resident service and `codex-mlx-testing` for smoke/sweep clients.
- Both dedicated tmux contexts currently fail content reads from
  `/Volumes/StudioStackSSD4TB/.../gpt-oss-20b-MXFP4-Q8/config.json` with
  `Operation not permitted`. Metadata lookup works, but opening the file does
  not.
- The launcher now detects this case before model load and exits `77` with an
  actionable permission message.
- Retesting after a tmux server reboot did not change this. The
  `codex-mlx-server` pane shell is child of the detached tmux server at
  `/opt/homebrew/bin/tmux`, with launchd as parent. Granting only the attached
  terminal app may not be sufficient if the detached tmux server itself remains
  outside the permitted context.
- User-run validation from a permitted terminal context passed on
  `gpt-oss-20b-MXFP4-Q8` with `Device(gpu, 0)`.
- Real cache reuse evidence:
  - smoke prefix probe: `cache_reuse_enabled=True`, `cache_created=True`,
    `cached_prefix_tokens=38`, `actual_prefill_tokens=2`
  - prefix sweep request 2: cache created for `194` shared prefix tokens, actual
    prefill dropped to `11` suffix tokens
  - prefix sweep requests 3-6: cache hits, actual prefill stayed at suffix size
    only: `11`, `12`, `13`, and `10` tokens

Expected prefix-sweep behavior after a permitted restart:

- Request 1: no candidate, full prefill.
- Request 2: cache candidate, `cache_created=True`, suffix-only actual prefill.
- Requests 3+: `cache_hit=True`, suffix-only actual prefill.

Run from a permitted Terminal:

```bash
cd /Users/jeffreycruz/Development/LLM_INFERENCE/mlx/.worktrees/prompt-processing-bench
MODEL="/Volumes/StudioStackSSD4TB/Development/LLM/lmstudio/models/mlx-community/gpt-oss-20b-MXFP4-Q8"
python3 benchmarks/python/resident_mlx_service.py \
  --model "$MODEL" \
  --port 8765 \
  --warmup-prompt-tokens 64,512 \
  --require-gpu
```

Then in another permitted Terminal:

```bash
cd /Users/jeffreycruz/Development/LLM_INFERENCE/mlx/.worktrees/prompt-processing-bench
python3 benchmarks/python/smoke_resident_service.py \
  --base-url http://127.0.0.1:8765 \
  --skip-lifecycle
rm -f prefix-opportunity-sweep.jsonl
python3 benchmarks/python/prefix_opportunity_sweep.py \
  --base-url http://127.0.0.1:8765 \
  --output-jsonl prefix-opportunity-sweep.jsonl
```

Latency impact validation:

```bash
python3 benchmarks/python/prefix_latency_sweep.py \
  --base-url http://127.0.0.1:8765 \
  --output-jsonl prefix-latency-sweep.jsonl \
  --groups 3 \
  --requests-per-group 6 \
  --prefix-repeats 24
```

The latency sweep reports phase summaries for:

- `full_prefill`
- `cache_create`
- `cache_hit`
- `cache_other`

Latest measured latency result from panes split under
`codex-gpt5_5-panthro_cpp`:

```text
summary_phase full_prefill 3 mean_run_ms 600.45 mean_service_request_ms 601.77 mean_cache_prepare_ms 0.0 mean_elapsed_ms 609.06 mean_actual_prefill 929.67
summary_phase cache_create 3 mean_run_ms 186.16 mean_service_request_ms 631.28 mean_cache_prepare_ms 443.81 mean_elapsed_ms 632.74 mean_actual_prefill 10.0
summary_phase cache_hit 12 mean_run_ms 197.99 mean_service_request_ms 199.53 mean_cache_prepare_ms 0.16 mean_elapsed_ms 200.98 mean_actual_prefill 9.5
```

Interpretation:

- Cache creation is not yet a latency win for the creating request because it
  precomputes the prefix cache, then generates from the suffix.
- Cache hits are a meaningful latency win: service-side request time drops from
  about `602 ms` to about `200 ms` for ~930-token prompts.
- The next optimization target is reducing or amortizing cache-create cost,
  then extending reuse to streaming paths and larger prompt shapes.

Validation safety notes:

- Use `smoke_resident_service.py --skip-lifecycle` before benchmark sweeps so
  the service is not unloaded mid-chain.
- Run full lifecycle smoke separately when explicitly testing unload/reload.
- `prefix_opportunity_sweep.py` inserts a unique run id at the first prompt
  line so repeated benchmark runs in the same resident process do not match
  entire old prompts.

## M7 Completion Evidence

M7 is complete for the conservative resident-engine prefix-cache slice.

Delivered:

- Real prefix-cache reuse for non-streaming generation.
- Real prefix-cache reuse for streaming generation.
- Scoped cache keys that include model path, profile path, backend, effective
  policy, prefill step size, tokenizer class, and chat-template hash.
- Service-side timing fields:
  - `cache_prepare_ms`
  - `service_request_ms`
  - `actual_prefill_tokens`
- Safe smoke validation that can skip unload/reload.
- Repeatable opportunity and latency sweeps.

Streaming smoke evidence:

```text
stream_prefix 64 0.955 True True False True 96.28 64 3
```

Final opportunity sweep:

```text
prefix_sweep 1 221 1 0.005 False False False False 0.0 221
prefix_sweep 2 220 209 0.95 True True False True 154.21 11
prefix_sweep 3 220 209 0.95 True True True False 0.17 11
prefix_sweep 4 221 209 0.946 True True True False 0.21 12
prefix_sweep 5 222 209 0.941 True True True False 0.16 13
prefix_sweep 6 219 209 0.954 True True True False 0.16 10
summary 6 5 0.791 prefix-opportunity-sweep.jsonl
```

Final latency sweep:

```text
summary_phase full_prefill 3 mean_run_ms 598.98 mean_service_request_ms 600.18 mean_cache_prepare_ms 0.0 mean_elapsed_ms 606.77 mean_actual_prefill 930.67
summary_phase cache_create 3 mean_run_ms 183.56 mean_service_request_ms 631.11 mean_cache_prepare_ms 446.22 mean_elapsed_ms 632.55 mean_actual_prefill 10.0
summary_phase cache_hit 12 mean_run_ms 182.19 mean_service_request_ms 183.63 mean_cache_prepare_ms 0.17 mean_elapsed_ms 184.95 mean_actual_prefill 9.5
```

M7 conclusion:

- Cache creation remains roughly cost-neutral for the creating request because
  the engine precomputes the prefix cache.
- Cache hits are a major win: measured service-side request time drops from
  about `600 ms` to about `184 ms` on the ~930-token repeated-prefix workload.
- This is about a `3.27x` cache-hit speedup for the measured shape.

## M8 Scheduler Start

M8 is now focused on scheduler and multi-request serving.

Initial delivered slice:

- Bounded request admission control.
- Configurable limits:
  - `--max-concurrent-requests`
  - `--max-queued-requests`
  - `--queue-timeout-ms`
- `run_resident_service.sh` environment overrides:
  - `MAX_CONCURRENT_REQUESTS`
  - `MAX_QUEUED_REQUESTS`
  - `QUEUE_TIMEOUT_MS`
- Scheduler state in `/health` and `/engine`.
- Per-request scheduler timing fields:
  - `scheduler_queue_wait_ms`
  - `scheduler_active_requests_at_admit`
  - `scheduler_queued_requests_at_admit`
- Concurrent probe:
  `benchmarks/python/scheduler_admission_probe.py`

Scheduler probe evidence:

```text
scheduler_before 1 16 0 0 0 0
scheduler_probe 1 0.0 1 0 403.49 405.34
scheduler_probe 2 403.45 1 1 648.29 649.91
scheduler_probe 3 648.21 1 0 898.41 899.96
scheduler_after 0 0 3 3 0 350.55 648.21
```

Interpretation:

- The default scheduler admits one active generation at a time.
- Concurrent clients queue instead of racing the MLX model.
- Queue wait is now measurable per request and in aggregate.
- No requests were rejected in the three-client probe.

Remaining M8 work:

- Add first-token latency and token cadence metrics for streaming. Done for
  streaming final metrics.
- Add rejection-path validation with small `max_queued_requests`. Done with
  `MAX_QUEUED_REQUESTS=1` and `QUEUE_TIMEOUT_MS=50`.
- Add larger prompt/context sweeps: 2k, 4k, and 8k. Done.
- Evaluate whether `max_concurrent_requests > 1` is safe or whether model access
  must remain strictly serialized. Initial M8 decision: keep default `1` because
  model execution is still guarded by a single engine lock; M9 can add lock-wait
  instrumentation before changing this default.
- Native overlap audit against `llama.cpp`, `puma.cpp`, and `panthro.cpp`:
  identify C++/Metal/GGUF/RoPE/attention/quantization/cache areas where those
  runtimes already contain fixes or performance enhancements that can inform
  MLX work. The goal is not direct code copying; it is to avoid re-solving
  already-solved runtime problems and to squeeze the most performance and speed
  out of the MLX engine.

Native overlap audit acceptance:

- Produce a matrix of shared domains:
  - GGUF parsing and quant support
  - RoPE, MROPE, and IMROPE semantics
  - Metal attention, matmul, normalization, and fused kernels
  - KV-cache layout, reuse, and memory pressure
  - scheduler and batching behavior
  - prompt-processing benchmark shapes
- Classify each item as:
  - direct source overlap
  - semantic overlap only
  - already validated in MLX
  - candidate optimization port
  - not applicable to MLX-format/safetensors models
- Prioritize only changes with expected measurable prompt-processing or decode
  speed impact.

Streaming latency evidence:

```text
stream_prefix 62 0.954 True True False True 93.01 62 3 100.76 7.55
```

Interpretation:

- Streaming prefix cache reuse still works after scheduler integration.
- First token latency for the measured streaming prefix case was `100.76 ms`.
- Mean gap between streamed token events was `7.55 ms`.

Rejection-path evidence:

```text
scheduler_before 1 1 0 0 0 0
scheduler_rejected 2 503 80.77 {"detail":"resident engine queue is full"}
scheduler_rejected 4 503 80.71 {"detail":"resident engine queue wait timed out"}
scheduler_rejected 3 503 135.95 {"detail":"resident engine queue wait timed out"}
scheduler_probe 1 0.0 1 0 575.08 577.02
scheduler_after 0 0 1 1 3 0.0 0.0
```

Larger-context cache-hit evidence:

```text
2k shape:
summary_phase full_prefill 1 mean_service_request_ms 2783.02 mean_actual_prefill 2010.0
summary_phase cache_hit 2 mean_service_request_ms 186.41 mean_actual_prefill 10.0

4k shape:
summary_phase full_prefill 1 mean_service_request_ms 2021.29 mean_actual_prefill 3810.0
summary_phase cache_hit 2 mean_service_request_ms 248.66 mean_actual_prefill 10.0

8k shape:
summary_phase full_prefill 1 mean_service_request_ms 3718.98 mean_actual_prefill 7411.0
summary_phase cache_hit 2 mean_service_request_ms 211.4 mean_actual_prefill 10.0
```

M8 completion:

- Scheduler/admission control exists and is validated.
- Streaming first-token and token cadence metrics exist and are validated.
- Scheduler rejection behavior exists and is validated.
- Larger-context prefix-cache wins are measured through the ~7.4k-token shape.
- Native overlap audit exists:
  `docs/mac-local-inference-platform/native-overlap-audit.md`

M9 optimization direction:

- Add memory-pressure and cache-eviction policy.
- Add lock-wait instrumentation before experimenting with
  `max_concurrent_requests > 1`.
- Investigate puma-style fused Metal kernel opportunities.
- Compare pp/tg benchmark shapes against puma/panthro where model formats are
  reasonably comparable.

## M9 Optimization Observability

M9 has started with the observability needed to make optimization decisions
without guessing.

Delivered:

- Prefix-cache eviction telemetry:
  - `prefix_kv_cache.entries`
  - `prefix_kv_cache.max_entries`
  - `prefix_kv_cache.evictions`
  - retained cache-key metadata in `/health` and `/engine`
- MLX memory telemetry:
  - `active_memory_bytes`
  - `cache_memory_bytes`
  - `peak_memory_bytes`
- Engine lock-wait telemetry:
  - per-request `engine_lock_wait_ms`
  - scheduler admission probe output includes lock wait
- Configurable cache size:
  - `--prefix-cache-max-entries`
  - `PREFIX_CACHE_MAX_ENTRIES` in `run_resident_service.sh`

Concurrency experiment:

```text
scheduler_before 2 16 0 0 0 0
scheduler_probe 2 0.0 1 0 0.0 555.67 595.46
scheduler_probe 1 0.01 2 0 555.12 805.95 845.58
scheduler_probe 3 516.11 2 0 213.01 1018.13 1060.01
scheduler_after 0 0 3 3 0 172.04 516.11
```

Interpretation:

- `MAX_CONCURRENT_REQUESTS=2` admits two requests into the active set.
- The active requests do not execute the MLX model concurrently yet because
  model execution is still guarded by the engine lock.
- The second active request waited `555.12 ms` on the engine lock.
- The queued request waited `516.11 ms` for scheduler admission, then another
  `213.01 ms` on the engine lock.
- The safe default remains `max_concurrent_requests=1` until the runtime has a
  real batching or concurrent execution design.

Eviction experiment:

```bash
MAX_CONCURRENT_REQUESTS=2 PREFIX_CACHE_MAX_ENTRIES=2 \
  benchmarks/python/run_resident_service.sh "$MODEL" 8765

python3 benchmarks/python/prefix_latency_sweep.py \
  --base-url http://127.0.0.1:8765 \
  --output-jsonl prefix-latency-sweep-eviction.jsonl \
  --groups 4 \
  --requests-per-group 3 \
  --prefix-repeats 24 \
  --max-tokens 4
```

Eviction sweep evidence:

```text
summary_phase full_prefill 4 mean_run_ms 657.84 mean_service_request_ms 659.16 mean_cache_prepare_ms 0.0 mean_elapsed_ms 665.08 mean_actual_prefill 929.25
summary_phase cache_create 4 mean_run_ms 152.57 mean_service_request_ms 597.75 mean_cache_prepare_ms 443.93 mean_elapsed_ms 599.28 mean_actual_prefill 10.0
summary_phase cache_hit 4 mean_run_ms 156.31 mean_service_request_ms 157.83 mean_cache_prepare_ms 0.19 mean_elapsed_ms 159.37 mean_actual_prefill 11.0
```

Health evidence after the eviction sweep:

```text
prefix_kv_cache entries=2 max_entries=2 evictions=2
mlx_memory active_memory_bytes=12135785624 cache_memory_bytes=32158024 peak_memory_bytes=12898081034
```

M9 conclusion so far:

- Cache eviction is observable and bounded-cache behavior is validated.
- MLX memory state is now visible to the service layer.
- Lock contention is measurable and proves that admission concurrency is not
  the same as model execution concurrency.
- The next optimization decision should be driven by these measurements:
  async cache creation, memory-pressure eviction, batched prefill/decode, or
  lower-level Metal kernel work.

### M9 Memory-Pressure Policy

The resident service now has an active prefix-cache memory-pressure policy.

Controls:

- `--prefix-cache-memory-limit-mb`
- `--prefix-cache-min-entries`
- `PREFIX_CACHE_MEMORY_LIMIT_MB` in `run_resident_service.sh`
- `PREFIX_CACHE_MIN_ENTRIES` in `run_resident_service.sh`

Runtime surfaces:

- `/health` and `/engine` include `prefix_cache_policy`.
- `prefix_cache_policy.memory_limit_bytes` shows the configured limit, or
  `null` when disabled.
- `prefix_cache_policy.min_entries` shows how many LRU cache entries are
  retained under pressure.
- `prefix_cache_policy.memory_prunes` counts memory-pressure prune events.
- `prefix_cache_policy.last_prune` records before/after memory and removed
  entries from the latest prune.
- `/engine/cache/prune` accepts:

```json
{"target_entries": 0, "clear_mlx_cache": true}
```

Per-request metrics:

- `memory_prune_applied`
- `memory_prune_removed_entries`
- `memory_prune_cache_memory_bytes`
- `memory_prune_limit_bytes`

Validation command:

```bash
PREFIX_CACHE_MEMORY_LIMIT_MB=1 PREFIX_CACHE_MIN_ENTRIES=0 \
  benchmarks/python/run_resident_service.sh "$MODEL" 8765

python3 benchmarks/python/memory_pressure_probe.py \
  --base-url http://127.0.0.1:8765
```

Validation evidence:

```text
memory_before 0 0 {'memory_limit_bytes': 1048576, 'min_entries': 0, 'memory_prunes': 0, 'last_prune': None}
memory_probe 1 0 False False False False 0 575.85
memory_probe 2 65 True False True True 1 236.11
memory_after_requests 0 1 1 {'memory_limit_bytes': 1048576, 'min_entries': 0, 'memory_prunes': 1, 'last_prune': {'reason': 'request', 'target_entries': 0, 'clear_mlx_cache': True, 'memory_before': {'active_memory_bytes': 12098036888, 'cache_memory_bytes': 3577334, 'peak_memory_bytes': 12609505466}, 'memory_after': {'active_memory_bytes': 12088599704, 'cache_memory_bytes': 0, 'peak_memory_bytes': 12609505466}, 'before_entries': 1, 'after_entries': 0, 'removed_entries': 1, 'removed_keys': ['443e83a406cd5efce4ec3b4d55f6ec50'], 'evictions': 1, 'prunes': 1}}
manual_prune 0 0 0 True
memory_after_prune 0 1 1
```

Interpretation:

- The second related request created a reusable prefix cache.
- The configured low memory limit forced immediate pruning.
- The prefix-cache store returned to zero entries.
- MLX cache memory dropped from `3577334` bytes to `0` bytes after pruning.
- The manual prune endpoint is safe when the cache is already empty.

Default behavior remains unchanged because `--prefix-cache-memory-limit-mb`
defaults to `0`, which disables automatic memory-pressure pruning.

### M9 Async Prefix-Cache Population

The resident service now supports configurable prefix-cache population mode.

Controls:

- `--prefix-cache-population-mode sync`
- `--prefix-cache-population-mode async`
- `--prefix-cache-population-mode off`
- `PREFIX_CACHE_POPULATION_MODE` in `run_resident_service.sh`

Mode behavior:

- `sync`: current default. A cache-candidate miss builds the prefix cache before
  generating from the suffix. This gives immediate suffix-only prefill but the
  creating request pays cache-build cost.
- `async`: a cache-candidate miss schedules a background prefix-cache build and
  lets the current request use the full prompt path. Later related requests can
  hit the populated cache after the background worker finishes.
- `off`: disables real prefix-cache population while leaving opportunity
  metrics intact.

Runtime surfaces:

- `prefix_cache_policy.population_mode`
- `prefix_cache_policy.pending_async_builds`
- `prefix_cache_policy.async_builds_started`
- `prefix_cache_policy.async_builds_completed`
- `prefix_cache_policy.async_builds_failed`
- `prefix_cache_policy.last_async_error`

Per-request metrics:

- `cache_population_mode`
- `cache_scheduled`
- `cache_pending`

Validation command:

```bash
PREFIX_CACHE_POPULATION_MODE=async \
  benchmarks/python/run_resident_service.sh "$MODEL" 8765

python3 benchmarks/python/async_prefix_cache_probe.py \
  --base-url http://127.0.0.1:8765
```

Validation evidence:

```text
async_policy {'memory_limit_bytes': None, 'min_entries': 0, 'memory_prunes': 0, 'last_prune': None, 'population_mode': 'async', 'pending_async_builds': 0, 'async_builds_started': 0, 'async_builds_completed': 0, 'async_builds_failed': 0, 'last_async_error': None}
async_probe 1 0 False False False False 0.0 446.94
async_probe 2 52 False True False False 0.13 206.95
async_wait 0 1 1 0 1
async_probe 3 52 True False True False 0.15 141.43 2
```

Interpretation:

- Request 2 found a reusable prefix but did not synchronously build the cache.
- Request 2 scheduled background cache population with only `0.13 ms`
  preparation time.
- The background worker completed before request 3.
- Request 3 hit the asynchronously built cache and reduced actual prefill to
  `2` suffix tokens.

Default behavior remains `sync` so prior M7/M8 latency comparisons are still
valid unless async mode is explicitly selected.

Follow-up latency sweep:

`prefix_latency_sweep.py` now classifies `cache_scheduled` separately. This is
important because async mode has three distinct phases:

- `cache_scheduled`: a candidate miss schedules background population and uses
  the full prompt for the current request.
- `full_prefill`: no cache candidate, or a pending build is not ready yet.
- `cache_hit`: a later request uses the populated cache and processes only the
  suffix.

Deferred async sweep evidence:

```text
summary_phase full_prefill 6 mean_run_ms 858.8 mean_service_request_ms 860.13 mean_cache_prepare_ms 0.05 mean_elapsed_ms 864.73 mean_actual_prefill 930.0
summary_phase cache_scheduled 3 mean_run_ms 610.69 mean_service_request_ms 612.14 mean_cache_prepare_ms 0.09 mean_elapsed_ms 615.13 mean_actual_prefill 930.0
summary_phase cache_hit 9 mean_run_ms 187.22 mean_service_request_ms 188.71 mean_cache_prepare_ms 0.18 mean_elapsed_ms 190.08 mean_actual_prefill 9.0
summary 18 prefix-latency-sweep-async-deferred.jsonl
```

Important finding:

- The first async sweep proved request 3 could block while the background build
  held the engine lock, showing `cache_prepare_ms` around `444-450 ms`.
- The async cache-state path was changed so pending builds no longer block on
  the engine lock.
- The next sweep showed request 2 could still slow down if the background
  builder grabbed the engine lock before current generation started.
- Background scheduling is now deferred until after the current request
  completes.

Decision:

- Keep `sync` as default for now because it has simpler and more predictable
  latency.
- Keep `async` as an opt-in mode because it removes synchronous cache-build
  preparation from `cache_scheduled` requests and still gives fast later hits.
- Before making async default, add an idle-aware or queue-aware background
  builder so cache population does not compete with foreground inference.

Queue-aware async builder:

The async worker now waits for the scheduler to become idle before taking the
engine lock.

Additional controls:

- `--prefix-cache-async-idle-timeout-ms`
- `PREFIX_CACHE_ASYNC_IDLE_TIMEOUT_MS`

Additional telemetry:

- `prefix_cache_policy.async_builds_skipped`
- `prefix_cache_policy.async_idle_timeout_ms`

Queue-aware sweep evidence:

```text
summary_phase full_prefill 6 mean_run_ms 864.85 mean_service_request_ms 866.2 mean_cache_prepare_ms 0.04 mean_elapsed_ms 870.9 mean_actual_prefill 931.33
summary_phase cache_scheduled 3 mean_run_ms 599.68 mean_service_request_ms 601.03 mean_cache_prepare_ms 0.09 mean_elapsed_ms 603.74 mean_actual_prefill 931.33
summary_phase cache_hit 9 mean_run_ms 183.07 mean_service_request_ms 184.55 mean_cache_prepare_ms 0.17 mean_elapsed_ms 185.85 mean_actual_prefill 9.0
summary 18 prefix-latency-sweep-async-idle.jsonl
async_idle_health {'memory_limit_bytes': None, 'min_entries': 0, 'memory_prunes': 0, 'last_prune': None, 'population_mode': 'async', 'pending_async_builds': 0, 'async_builds_started': 3, 'async_builds_completed': 3, 'async_builds_failed': 0, 'async_builds_skipped': 0, 'async_idle_timeout_ms': 30000, 'last_async_error': None}
```

Updated decision:

- Queue-aware async is better than naive async because `cache_scheduled`
  requests avoid synchronous cache-build preparation and later cache hits remain
  fast.
- It is still not safe as the default. A race remains after the scheduler
  becomes idle: the background worker can acquire the engine lock just before
  the next foreground request arrives.
- The next async milestone should introduce foreground-priority engine locking
  or an idle-grace/debounce policy so background cache work cannot sit ahead of
  user-facing inference.

Foreground-priority execution lock:

The resident engine now uses `EngineExecutionLock` on model execution paths.
Foreground inference acquires the foreground lane. Async cache builds acquire
the background lane. Background work cannot enter while foreground requests are
waiting.

Additional telemetry:

- `execution_lock.active`
- `execution_lock.active_kind`
- `execution_lock.foreground_waiters`
- `execution_lock.background_waiters`
- `execution_lock.foreground_acquires`
- `execution_lock.background_acquires`
- `execution_lock.background_priority_deferrals`
- `prefix_cache_policy.async_background_wait_ms`
- `prefix_cache_policy.async_priority_deferrals`

Foreground-priority sweep evidence:

```text
summary_phase full_prefill 6 mean_run_ms 861.1 mean_service_request_ms 862.45 mean_cache_prepare_ms 0.04 mean_elapsed_ms 867.27 mean_actual_prefill 930.67
summary_phase cache_scheduled 3 mean_run_ms 597.36 mean_service_request_ms 598.67 mean_cache_prepare_ms 0.08 mean_elapsed_ms 601.43 mean_actual_prefill 930.67
summary_phase cache_hit 9 mean_run_ms 184.16 mean_service_request_ms 185.65 mean_cache_prepare_ms 0.18 mean_elapsed_ms 186.98 mean_actual_prefill 9.0
summary 18 prefix-latency-sweep-async-priority.jsonl
priority_health {'memory_limit_bytes': None, 'min_entries': 0, 'memory_prunes': 0, 'last_prune': None, 'population_mode': 'async', 'pending_async_builds': 0, 'async_builds_started': 3, 'async_builds_completed': 3, 'async_builds_failed': 0, 'async_builds_skipped': 0, 'async_background_wait_ms': 0.004333094693720341, 'async_priority_deferrals': 0, 'async_idle_timeout_ms': 30000, 'last_async_error': None} {'active': False, 'active_kind': None, 'foreground_waiters': 0, 'background_waiters': 0, 'foreground_acquires': 20, 'background_acquires': 3, 'background_priority_deferrals': 0}
```

Current decision:

- Keep `sync` as default because it is still the most predictable latency path.
- Keep `async` opt-in, but the core priority-lock machinery is now present.
- Next async validation should create an explicit concurrent foreground traffic
  race probe to prove background cache builds defer when foreground waiters are
  present.

Priority-probe validation:

The service now exposes a synthetic execution-lock probe:

```text
POST /engine/lock/priority-probe
```

The probe holds the execution lock, starts a background waiter, then starts a
foreground waiter. When the lock is released, the foreground waiter must acquire
before the background waiter.

Evidence:

```text
{"ok":true,"order":[{"kind":"foreground","wait_ms":0.02587493509054184},{"kind":"background","wait_ms":0.07333408575505018,"deferrals":1}],"background_priority_deferrals_delta":1}
```

Interpretation:

- Foreground acquired before background.
- The background path observed a foreground waiter and deferred once.
- The priority mechanism is now validated independently of timing-sensitive
  model-generation races.

## Next Cache Step

Validate and harden the conservative prefix-cache reuse prototype before full
paged KV:

- Run the permitted Terminal validation above and compare cache-hit requests
  against the prior full-prefill baseline.
- Confirm `actual_prefill_tokens` drops from the full prompt size to the suffix
  size on cache-hit requests.
- Keep a strict correctness fallback: if the cache shape, tokenizer hash, model
  path, policy, or chat template hash differs, recompute full prefill.
- Add a benchmark comparing:
  - current full-prefill path
  - measured prefix opportunity only
  - real cache-reuse path

Latest smoke result after restarting without an explicit profile:

```text
health True Device(gpu, 0) /Users/jeffreycruz/Development/LLM_INFERENCE/mlx/.worktrees/prompt-processing-bench/gpt-oss-20b-MXFP4-Q8-prefill-profile.json 0
generate req_ccb2e97513124068b98e54d67e0817cc memory_saver 512 9 8 length
completion text_completion length 13 memory_saver
chat chat.completion assistant 77 512
metrics 3 3 0 3
```

Latest streaming-inclusive smoke result:

```text
health True Device(gpu, 0) /Users/jeffreycruz/Development/LLM_INFERENCE/mlx/.worktrees/prompt-processing-bench/gpt-oss-20b-MXFP4-Q8-prefill-profile.json 0
generate req_91229b1ccf67446f839469ab8383f374 memory_saver 512 9 8 length
completion text_completion length 13 memory_saver
chat chat.completion assistant 77 512
stream_completion 5 True
stream_chat 6 True
metrics 5 5 0 5
```

Latest lifecycle-inclusive smoke result:

```text
health True Device(gpu, 0) /Users/jeffreycruz/Development/LLM_INFERENCE/mlx/.worktrees/prompt-processing-bench/gpt-oss-20b-MXFP4-Q8-prefill-profile.json 0
engine 0 True balanced,memory_saver,throughput_default
generate req_e68eb83913ea4ce3a24423e93c8fb2d1 memory_saver 512 9 8 length
completion text_completion length 13 memory_saver
chat chat.completion assistant 77 512
stream_completion 5 True
stream_chat 6 True
metrics 5 5 0 5
reload 1 Device(gpu, 0) True [64]
```

Packaged CLI validation:

```text
health True Device(gpu, 0) /Users/jeffreycruz/Development/LLM_INFERENCE/mlx/.worktrees/prompt-processing-bench/gpt-oss-20b-MXFP4-Q8-prefill-profile.json 0
engine 1 True balanced,memory_saver,throughput_default
generate req_fdc17e15b6244a4e8f7221ea614ba6b5 memory_saver 512 9 8 length
completion text_completion length 13 memory_saver
chat chat.completion assistant 77 512
stream_completion 5 True
stream_chat 6 True
metrics 5 5 0 5
reload 2 Device(gpu, 0) True [64]
correctness ok Device(gpu, 0) True 2 0
```

## Remaining M4 Work

- Add explicit unload and memory-pressure policy after reload semantics are stable.
- Move launchd/app-helper packaging to the next milestone.
- Add full VLM processor validation after the text engine contract is stable.

## Engine Presets

The resident-engine launcher now exposes a single preset control surface:

```bash
ENGINE_PRESET=sync-safe benchmarks/python/run_resident_service.sh "$MODEL"
ENGINE_PRESET=async-experimental benchmarks/python/run_resident_service.sh "$MODEL"
ENGINE_PRESET=memory-saver benchmarks/python/run_resident_service.sh "$MODEL"
```

Presets are applied in `run_resident_service.sh` as defaults. Any explicit
per-knob environment variable still wins, so the preset is an operator-friendly
baseline rather than a hard policy lock.

Preset definitions:

- `sync-safe`: default operational mode; one active request, 16 queued
  requests, sync prefix-cache population, 16 prefix-cache entries, no MLX cache
  memory cap.
- `async-experimental`: same scheduler/cache size as `sync-safe`, but prefix
  cache population runs asynchronously behind the foreground-priority execution
  lock.
- `memory-saver`: one active request, 8 queued requests, 4 prefix-cache entries,
  64 MiB MLX cache-memory limit, at least 1 retained prefix-cache entry.
- `custom`: explicit-knob mode; starts from the legacy defaults and expects the
  operator to set individual env vars.

Runtime observability:

- `/health.engine_preset`
- `/engine.engine_preset`
- `/health.prefix_cache_policy.population_mode`
- `/health.prefix_cache_policy.memory_limit_bytes`
- `/health.prefix_kv_cache.max_entries`
- `/health.scheduler.max_concurrent_requests`
- `/health.scheduler.max_queued_requests`

## Live Runtime Config

The service exposes live runtime policy mutation without unloading the model:

```bash
curl -sS -X POST http://127.0.0.1:8765/engine/config \
  -H 'Content-Type: application/json' \
  -d '{"engine_preset":"async-experimental"}'

curl -sS -X POST http://127.0.0.1:8765/engine/config \
  -H 'Content-Type: application/json' \
  -d '{"engine_preset":"memory-saver","prefix_cache_max_entries":3}'

curl -sS -X POST http://127.0.0.1:8765/engine/config \
  -H 'Content-Type: application/json' \
  -d '{"dry_run":true,"engine_preset":"memory-saver","prefix_cache_max_entries":3}'
```

Allowed live fields:

- `engine_preset`
- `max_concurrent_requests`
- `max_queued_requests`
- `queue_timeout_ms`
- `prefix_cache_max_entries`
- `prefix_cache_memory_limit_mb`
- `prefix_cache_min_entries`
- `prefix_cache_population_mode`
- `prefix_cache_async_idle_timeout_ms`

Safety boundary:

- This endpoint changes scheduler and cache policy only.
- It does not reload model weights, tokenizer state, RoPE/IMROPE behavior, or
  prefill-profile selection.
- If `prefix_cache_max_entries` is reduced below current cache size, LRU prefix
  entries are pruned immediately.
- If the memory-pressure limit changes, the memory-pressure policy is evaluated
  immediately.

Validation evidence:

```text
config_probe {'engine_preset': 'async-experimental'} async-experimental async 16 None 16
config_probe {'engine_preset': 'memory-saver', 'prefix_cache_max_entries': 3} memory-saver sync 3 67108864 8
config_probe {'engine_preset': 'sync-safe'} sync-safe sync 16 None 16
final_config_probe sync-safe sync 16 None 16
```

Repeatable validation:

```bash
python3 benchmarks/python/config_policy_probe.py \
  --base-url http://127.0.0.1:8765
```

Probe evidence:

```text
initial_config sync-safe sync 16 None 16
dry_run_config memory-saver sync 3 67108864 8
apply_async async-experimental async 16 None 16
apply_memory_saver_override memory-saver sync 3 67108864 8
restore_sync_safe sync-safe sync 16 None 16
smoke_after_config stream_prefix 62 0.954 True True False True 93.74 62 3 119.4 7.6
```

MLX validation note:

- Do not import `resident_mlx_service.py` from arbitrary Codex-spawned Python
  subprocesses for lightweight unit checks; importing `mlx.core` can abort in
  Metal initialization when the subprocess cannot see the Metal device array.
- Use `python3 -m py_compile` for syntax checks and tmux-hosted HTTP probes for
  runtime validation.

## Unified Benchmark Harness

Use the resident benchmark harness when comparing optimization changes:

```bash
python3 benchmarks/python/resident_benchmark_harness.py \
  --base-url http://127.0.0.1:8765 \
  --engine-preset sync-safe \
  --reset-cache \
  --requests 6 \
  --prefix-repeats 24 \
  --max-tokens 8 \
  --output-jsonl resident-benchmark-sync-safe.jsonl
```

The harness writes one JSONL artifact containing:

- `health_before`
- optional `config_apply`
- optional `cache_prune`
- `health_start`
- per-request completion rows
- streaming completion row
- per-phase summary rows
- `health_after`

First benchmark evidence:

```text
harness_health_before sync-safe Device(gpu, 0) sync 16
harness_cache_prune 3 0
harness_request 1 full_prefill 571 571 2516.39 0.0
harness_request 2 cache_create 571 8 485.1 296.17
harness_request 3 cache_hit 571 8 186.14 0.16
harness_request 4 cache_hit 571 8 193.27 0.19
harness_request 5 cache_hit 571 8 188.91 0.18
harness_request 6 cache_hit 571 8 190.31 0.17
harness_stream cache_create 7 125.35 7.55
harness_summary cache_create 2 469.54 7.5
harness_summary cache_hit 4 189.66 8.0
harness_summary full_prefill 1 2516.39 571.0
```

Interpretation:

- Cache hits reduce actual prefill from `571` tokens to `8` tokens.
- In this run, mean cache-hit service latency was `189.66 ms` versus
  `2516.39 ms` for the full-prefill request.
- The harness artifact is `resident-benchmark-sync-safe.jsonl`.

## Benchmark Comparison

Compare preset artifacts with:

```bash
python3 benchmarks/python/compare_resident_benchmarks.py \
  resident-benchmark-sync-safe.jsonl \
  resident-benchmark-async-experimental.jsonl \
  resident-benchmark-memory-saver.jsonl
```

Comparison evidence:

```text
artifact resident-benchmark-sync-safe.jsonl sync-safe sync 16 None 7 1778730833-29612fa9
artifact resident-benchmark-async-experimental.jsonl async-experimental async 16 None 7 1778731069-8e0b324a
artifact resident-benchmark-memory-saver.jsonl memory-saver sync 4 67108864 7 1778731075-a72f3233

phase cache_hit resident-benchmark-sync-safe.jsonl 4 189.66 8.00 1.00
phase cache_hit resident-benchmark-async-experimental.jsonl 3 192.86 8.00 0.98
phase cache_hit resident-benchmark-memory-saver.jsonl 4 190.85 8.00 0.99
phase cache_scheduled resident-benchmark-async-experimental.jsonl 2 589.86 572.50 -
```

Interpretation:

- Cache-hit latency is stable across presets in this run: about `190 ms` with
  actual prefill reduced to `8` tokens.
- `async-experimental` avoids synchronous cache creation on the scheduling
  request, but those scheduled requests still pay full-prefill cost until the
  background build completes.
- `memory-saver` keeps cache-hit behavior comparable to `sync-safe` while using
  a smaller cache cap.
- Full-prefill rows are warm-state sensitive across sequential runs; do not use
  this batch alone to claim preset-level full-prefill speedups.

## Prefill Isolation

Use prefill-isolation mode to separate first-request warmup cost from warmed
full-prefill throughput:

```bash
python3 benchmarks/python/resident_benchmark_harness.py \
  --base-url http://127.0.0.1:8765 \
  --mode prefill-isolation \
  --engine-preset sync-safe \
  --restore-engine-preset sync-safe \
  --prefill-runs 5 \
  --prefix-repeats 24 \
  --max-tokens 4 \
  --output-jsonl resident-prefill-isolation-sync-safe.jsonl
```

Behavior:

- Sets `prefix_cache_population_mode=off`.
- Clears prefix cache and MLX cache before the first measured request.
- Uses the same full prompt repeatedly.
- Labels the first request `prefill_cold`.
- Labels later requests `prefill_warm`.
- Restores the requested preset at the end when `--restore-engine-preset` is
  provided.

Evidence:

```text
prefill_request 1 prefill_cold 586 586 False 2520.02 246.48
prefill_request 2 prefill_warm 586 586 False 430.58 1877.76
prefill_request 3 prefill_warm 586 586 False 425.76 1881.16
prefill_request 4 prefill_warm 586 586 False 425.35 1882.98
prefill_request 5 prefill_warm 586 586 False 422.88 1883.57
prefill_summary prefill_cold 1 2520.02 586.0
prefill_summary prefill_warm 4 426.14 586.0
```

Interpretation:

- The first full-prefill request after cache clearing is about `2520 ms`.
- Warmed full-prefill for the same `586` prompt tokens stabilizes around
  `426 ms`.
- Prefix cache was disabled, so `actual_prefill_tokens` stayed at `586` and
  `cache_reuse_enabled` stayed `False`.
- This isolates a real warmup effect from actual steady-state prompt processing.

## Regression Gate

Use the artifact-based regression gate after benchmark runs:

```bash
python3 benchmarks/python/resident_regression_gate.py \
  --cache-artifact resident-benchmark-sync-safe.jsonl \
  --prefill-artifact resident-prefill-isolation-sync-safe.jsonl
```

Default gates:

- cache-hit mean service request <= `250 ms`
- cache-hit mean actual prefill tokens <= `16`
- warm-prefill mean service request <= `550 ms`
- warm-prefill actual prefill tokens >= `500`
- cold/warm prefill ratio <= `8x`
- every cache-hit row must have cache reuse enabled and suffix-sized actual
  prefill
- every warm-prefill isolation row must have cache reuse disabled and full
  actual prefill

Passing evidence:

```text
gate_check PASS cache_hit.mean_service_request_ms 189.659 <= 250.0
gate_check PASS cache_hit.mean_actual_prefill_tokens 8.0 <= 16.0
gate_check PASS prefill_warm.mean_service_request_ms 426.143 <= 550.0
gate_check PASS prefill_warm.mean_actual_prefill_tokens 586.0 >= 500.0
gate_check PASS prefill_cold_to_warm_ratio 5.914 <= 8.0
gate_check PASS cache_hit_rows_reuse_suffix 4 / 4
gate_check PASS prefill_warm_rows_no_cache_full_prefill 4 / 4
gate_result PASS
```

Intentional failure evidence:

```text
python3 benchmarks/python/resident_regression_gate.py \
  --cache-artifact resident-benchmark-sync-safe.jsonl \
  --prefill-artifact resident-prefill-isolation-sync-safe.jsonl \
  --max-cache-hit-service-ms 100

gate_result FAIL
gate_failure cache_hit.mean_service_request_ms: 189.659 > 100.000
```

## One-Command Regression Suite

Run cache benchmark, prefill-isolation benchmark, comparison, and regression
gate together:

```bash
python3 benchmarks/python/run_resident_regression_suite.py \
  --base-url http://127.0.0.1:8765 \
  --tag suite-smoke \
  --requests 4 \
  --prefill-runs 4 \
  --prefix-repeats 24 \
  --max-tokens 8 \
  --prefill-max-tokens 4
```

The suite writes:

- `resident-benchmark-sync-safe-<tag>.jsonl`
- `resident-prefill-isolation-sync-safe-<tag>.jsonl`

The suite then runs:

- `compare_resident_benchmarks.py`
- `resident_regression_gate.py`

Smoke evidence:

```text
harness_summary cache_hit 2 180.23 8.0
prefill_summary prefill_warm 3 432.51 585.0
gate_result PASS
suite_result PASS resident-benchmark-sync-safe-suite-smoke.jsonl resident-prefill-isolation-sync-safe-suite-smoke.jsonl
```

Operational note:

- `prefill_cold` is only truly cold when the MLX/runtime state is cold enough.
- The suite is intended primarily to protect steady cache-hit behavior and
  warmed full-prefill behavior.
- For strict cold-start measurement, restart the resident service before running
  the suite or use a dedicated cold-start harness.

## Lifecycle Cold-Start Suite

Use `--cold-start` when lifecycle reload overhead should be captured alongside
the standard performance gate:

```bash
python3 benchmarks/python/run_resident_regression_suite.py \
  --base-url http://127.0.0.1:8765 \
  --cold-start \
  --tag cold-suite-smoke \
  --requests 4 \
  --prefill-runs 4 \
  --prefix-repeats 24 \
  --max-tokens 8 \
  --prefill-max-tokens 4 \
  --reload-warmup-prompt-tokens 64,512
```

The cold-start mode writes:

- `resident-cold-start-sync-safe-<tag>.jsonl`
- `resident-benchmark-sync-safe-<tag>.jsonl`
- `resident-prefill-isolation-sync-safe-<tag>.jsonl`

Lifecycle evidence:

```text
suite_cold_health_before sync-safe True 5701.205708086491
suite_cold_unload 940.13 False 1
suite_cold_reload 6457.05 4385.97 [64, 512]
suite_cold_health_after sync-safe True 4385.97 [64, 512]
```

Post-reload benchmark evidence:

```text
harness_summary cache_hit 2 174.70 8.0
prefill_summary prefill_warm 3 422.68 585.0
gate_result PASS
suite_result PASS resident-benchmark-sync-safe-cold-suite-smoke.jsonl resident-prefill-isolation-sync-safe-cold-suite-smoke.jsonl resident-cold-start-sync-safe-cold-suite-smoke.jsonl
```

Interpretation:

- Lifecycle reload wall time was `6457.05 ms`.
- Service-reported model load time was `4385.97 ms`.
- Warmup used `[64, 512]`.
- After reload warmup, first benchmark full-prefill was already warm-state
  speed: `443.67 ms` for `571` actual prefill tokens.
- This mode measures resident lifecycle reload overhead, not a strict
  process-level cold start.

## Exact-Prompt Prefix Cache Reuse

The LM Studio `mlx-engine` audit highlighted a cache behavior gap: exact prompt
repeats should still be reusable. The resident engine previously rejected exact
matches because there was no suffix left to send to generation. That protected
against empty input but lost the best cache case.

Implemented behavior:

- If the longest prefix match is shorter than the prompt, reuse that prefix as
  before.
- If the longest prefix match covers the full prompt, cache only
  `len(prompt_tokens) - 1` tokens.
- Send the final token as the runtime prompt segment.
- Report `cache_exact_match_trimmed=True` when this exact-match trim path is
  used.

This keeps MLX generation input non-empty while reducing exact repeated prompts
to one actual prefill token.

Validation:

```bash
python3 benchmarks/python/exact_prefix_cache_probe.py \
  --base-url http://127.0.0.1:8765
```

Passing evidence:

```text
exact_prefix 1 59 34 True True False False 34 25 421.37
exact_prefix 2 59 59 True True False True 58 1 213.78
exact_prefix 3 59 59 True False True True 58 1 117.11
exact_prefix_result PASS
```

Interpretation:

- The second request proves exact-match trim creation:
  `cache_exact_match_trimmed=True`, `cached_prefix_tokens=58`,
  `actual_prefill_tokens=1`.
- The third request proves steady exact-match cache hit behavior:
  `cache_hit=True`, `actual_prefill_tokens=1`.

## Native Prompt-Progress Telemetry

The resident engine now wires MLX-LM's native
`prompt_progress_callback(processed, total)` into text inference. This makes
long prompt processing measurable from the service response instead of only
appearing as a large first-token delay.

Final `engine_metrics` include:

- `prompt_progress_events`
- `prompt_progress_total_tokens`
- `prompt_progress_processed_tokens`
- `prompt_progress_first_ms`
- `prompt_progress_last_ms`
- `prompt_progress_complete`
- `prompt_progress_trace`

The trace is bounded to the most recent progress events so responses do not grow
with prompt length.

Validation:

```bash
python3 benchmarks/python/prompt_progress_probe.py \
  --base-url http://127.0.0.1:8765 \
  --prefill-step-size 16 \
  --repeats 64 \
  --max-tokens 4
```

Passing evidence:

```text
prompt_progress 1112 1112 16 72 1112 1112 True 2747.41
prompt_progress_result PASS
```

Interpretation:

- The request processed `1112` prompt tokens with prefix cache disabled.
- The native MLX callback emitted `72` progress events.
- Progress completed at `1112/1112`.
- This final-metric telemetry is also exposed live through the raw JSONL
  `/generate` stream.

## Live Prompt-Progress Streaming

Raw `/generate` requests with `stream=true` now use a worker-thread streaming
path:

- the worker owns MLX generation and the foreground execution lock
- native MLX prompt-progress callbacks are pushed into a queue
- the response iterator emits `type=prompt_progress` JSONL events immediately
- token and final events preserve the existing raw stream shape
- OpenAI-compatible SSE streams are intentionally unchanged for compatibility

Validation:

```bash
python3 benchmarks/python/live_prompt_progress_probe.py \
  --base-url http://127.0.0.1:8765 \
  --prefill-step-size 16 \
  --repeats 64 \
  --max-tokens 4
```

Passing evidence:

```text
live_prompt_progress 64 64 4 987 64 True 2439.85
live_prompt_first 0 987 82.98
live_prompt_last 987 987 2443.4
live_prompt_progress_result PASS
```

Interpretation:

- `64` progress events streamed to the client.
- All `64` progress events arrived before the first generated token event.
- The first progress event reached the client at `82.98 ms`.
- Final progress reached `987/987`.
- First-token latency was `2439.85 ms`, so the stream now provides visibility
  during the otherwise silent prompt-processing window.

Next related borrow candidates from the LM Studio audit:

- Strict process-level cold-start harness.
- Cache safety hardening for generated-token cache recording.

## Request Registry And Cancellation

The resident engine now has a request registry and best-effort cancellation
surface.

Endpoints:

```text
GET  /engine/requests
POST /engine/requests/{request_id}/cancel
```

Tracked request state:

- `request_id`
- route
- status
- prompt tokens
- effective policy
- prefill step size
- cancellation state
- prompt-progress counters
- recent completed requests

Cancellation behavior:

- Active raw `/generate` streams expose the `request_id` in progress events.
- A cancellation request marks the active request as `cancelling` and sets its
  cancellation event.
- MLX text generation checks cancellation at prompt-progress callback
  boundaries during prefill.
- Decode checks cancellation between generated token events.
- Raw `/generate` JSONL emits `type=cancelled` and exits.

Validation:

```bash
python3 benchmarks/python/cancel_request_probe.py \
  --base-url http://127.0.0.1:8765 \
  --prefill-step-size 16 \
  --repeats 96 \
  --max-tokens 32
```

Passing evidence:

```text
cancel_request req_ab6ffa1750c44d6889c2aa09c7b03359 2 0 2 cancelled cancelling
cancel_request_result PASS
```

Interpretation:

- The probe cancelled during prefill after `2` streamed progress events.
- No decode tokens were emitted before cancellation.
- The stream emitted a `cancelled` event.
- `GET /engine/requests` recorded the completed request status as `cancelled`.
- The cancel endpoint returned the immediate active status as `cancelling`.

Limitations:

- Cancellation is best-effort. MLX cannot be interrupted mid-kernel; the request
  stops at callback/decode checkpoints.
- Raw `/generate` JSONL is still the deepest validated cancellation surface.

## OpenAI SSE Prompt-Progress Comments

OpenAI-compatible streaming now exposes long-prefill progress without changing
the `data:` chunk schema.

Behavior:

- `/v1/completions` with `stream=true` emits prompt progress as SSE comments:
  `: prompt_progress {...}`.
- `/v1/chat/completions` with `stream=true` uses the same comment strategy.
- Generated content remains in OpenAI-style `data:` chunks.
- Final usage and `engine_metrics` remain in the final OpenAI-style `data:`
  chunk.
- Cancellation on OpenAI streams maps to a final chunk with
  `finish_reason="cancelled"`.

Validation:

```bash
python3 benchmarks/python/openai_sse_progress_probe.py \
  --base-url http://127.0.0.1:8765 \
  --prefill-step-size 16 \
  --repeats 64 \
  --max-tokens 4
```

Passing evidence:

```text
openai_sse_progress 68 68 5 1050 68 True 2629.04
openai_sse_first 0 1050 89.97
openai_sse_last 1050 1050 2633.08
openai_sse_progress_result PASS
```

Interpretation:

- `68` prompt-progress comments streamed to the client.
- All `68` comments arrived before the first OpenAI `data:` chunk.
- The first comment arrived at `89.97 ms`.
- Final prompt progress reached `1050/1050`.
- First-token latency was `2629.04 ms`, so OpenAI-compatible streaming now has
  prompt-processing visibility during long prefill.

## Generated-Token Prefix Cache Recording

The resident engine now records generated-token continuations into the prefix
cache. This borrows the important LM Studio cache-wrapper idea that a successful
decode should make the full prompt plus generated continuation reusable by later
requests.

Behavior:

- Sync generation and live worker streams keep the mutable MLX `prompt_cache`
  used during generation.
- Generated token IDs are collected from `GenerationResponse.token`.
- After successful generation, the engine records a prefix tracker entry for
  `prompt_tokens + generated_token_ids`.
- The same generated prefix is stored in `PrefixKVCacheStore` under the normal
  model/profile/policy/tokenizer scope.
- This avoids a post-hoc prefill rebuild for the generated continuation cache.
- Warmup strips internal prompt-cache objects before `/health` serialization.

Validation:

```bash
python3 benchmarks/python/generated_prefix_cache_probe.py \
  --base-url http://127.0.0.1:8765 \
  --first-max-tokens 12 \
  --second-max-tokens 4
```

Passing evidence:

```text
generated_prefix_first 41 12 12 True 53
generated_prefix_second 59 53 True True 53 6
generated_prefix_cache_result PASS
```

Interpretation:

- The first request had `41` prompt tokens and generated `12` tokens.
- The engine stored a generated-prefix cache entry with `53` tokens.
- The follow-up prompt had `59` tokens and matched the generated prefix for
  `53` tokens.
- The follow-up request hit the generated prefix cache and only prefetched `6`
  tokens.

Risk notes:

- This assumes MLX's mutable prompt cache state remains aligned with the
  yielded generated token IDs. The probe validates one real follow-up reuse path,
  but broader safety testing should cover EOS/stop behavior, tokenizer boundary
  cases, streaming cancellation, and longer continuations.

## Generated-Cache Safety Probes

The generated-prefix cache path now has a wider safety probe:

```bash
python3 benchmarks/python/generated_prefix_cache_safety_probe.py \
  --base-url http://127.0.0.1:8765 \
  --long-max-tokens 32 \
  --stream-max-tokens 12 \
  --cancel-repeats 96 \
  --prefill-step-size 16
```

Coverage:

- Long sync continuation cache recording and follow-up reuse.
- Raw streaming continuation cache recording and follow-up reuse.
- Cancellation during prefill does not add generated-prefix cache entries.
- Worker-thread post-generation cache recording errors are surfaced to the
  client instead of hanging the stream.

Passing evidence:

```text
generated_cache_long_safety 33 32 32 True 65 72 65 True True 7
generated_cache_stream_safety 33 12 12 True 45 50 45 True True 5
generated_cache_cancel_safety 0 0 2 0 2
generated_prefix_cache_safety_result PASS
```

Interpretation:

- Long sync path stored `65` generated-prefix tokens and follow-up prefilled
  only `7` tokens.
- Raw stream path stored `45` generated-prefix tokens and follow-up prefilled
  only `5` tokens.
- Cancelled prefill left prefix-cache entries unchanged: `0 -> 0`.

Bug fixed during this milestone:

- `_stream_run_live_jsonl` originally received only public metadata, so
  generated-cache recording lacked private `_prompt_tokens`.
- The helper now accepts explicit prompt token/text inputs for generated-cache
  recording.
- Post-generation cache-recording failures now produce an `error` stream event
  instead of leaving the client waiting indefinitely.

## Regression Suite Generated-Cache Safety Stage

Generated-prefix cache safety is now part of the one-command resident regression
suite rather than a manual follow-up probe.

Command shape:

```bash
python3 benchmarks/python/run_resident_regression_suite.py \
  --base-url http://127.0.0.1:8765 \
  --tag generated-cache-suite-smoke2 \
  --requests 4 \
  --prefill-runs 4 \
  --prefix-repeats 16 \
  --max-tokens 6 \
  --prefill-max-tokens 4 \
  --min-warm-prefill-tokens 350 \
  --generated-cache-long-max-tokens 12 \
  --generated-cache-stream-max-tokens 6 \
  --generated-cache-cancel-repeats 48 \
  --generated-cache-prefill-step-size 16
```

Passing evidence:

```text
gate_check PASS cache_hit.mean_service_request_ms 163.237 <= 250.0
gate_check PASS cache_hit.mean_actual_prefill_tokens 8.0 <= 16.0
gate_check PASS prefill_warm.mean_service_request_ms 352.031 <= 550.0
gate_check PASS prefill_warm.mean_actual_prefill_tokens 409.0 >= 350.0
gate_check PASS prefill_cold_to_warm_ratio 0.986 <= 8.0
gate_check PASS cache_hit_rows_reuse_suffix 2 / 2
gate_check PASS prefill_warm_rows_no_cache_full_prefill 3 / 3
gate_result PASS
generated_cache_long_safety 35 12 12 True 47 54 47 True True 7
generated_cache_stream_safety 35 6 6 True 41 46 41 True True 5
generated_cache_cancel_safety 0 0 2 0 2
generated_prefix_cache_safety_result PASS
suite_result PASS resident-benchmark-sync-safe-generated-cache-suite-smoke2.jsonl resident-prefill-isolation-sync-safe-generated-cache-suite-smoke2.jsonl generated_cache_safety= True
```

Interpretation:

- Cache-hit requests stayed below the `250 ms` service-time gate and only
  prefetched the suffix.
- Warm-prefill isolation stayed below the `550 ms` gate and processed full
  prompts with cache reuse disabled.
- Generated-cache safety covers long sync reuse, raw streaming reuse, and
  cancellation during prefill.
- Reduced prompt-shape smoke runs must adjust `--min-warm-prefill-tokens` to
  match the generated prompt length. With `--prefix-repeats 16`, the valid
  threshold is below the default `500` token full-size gate.

Full-size validation:

```bash
python3 benchmarks/python/run_resident_regression_suite.py \
  --base-url http://127.0.0.1:8765 \
  --tag generated-cache-suite-full \
  --requests 6 \
  --prefill-runs 5 \
  --prefix-repeats 24 \
  --max-tokens 8 \
  --prefill-max-tokens 4 \
  --generated-cache-long-max-tokens 32 \
  --generated-cache-stream-max-tokens 12 \
  --generated-cache-cancel-repeats 96 \
  --generated-cache-prefill-step-size 16
```

Passing evidence:

```text
phase full_prefill resident-benchmark-sync-safe-generated-cache-suite-full.jsonl 1 702.49 572.00 1.00
phase cache_create resident-benchmark-sync-safe-generated-cache-suite-full.jsonl 2 457.29 7.50 1.00
phase cache_hit resident-benchmark-sync-safe-generated-cache-suite-full.jsonl 4 183.51 8.00 1.00
phase prefill_warm resident-prefill-isolation-sync-safe-generated-cache-suite-full.jsonl 4 429.61 589.00 -
gate_check PASS cache_hit.mean_service_request_ms 183.512 <= 250.0
gate_check PASS cache_hit.mean_actual_prefill_tokens 8.0 <= 16.0
gate_check PASS prefill_warm.mean_service_request_ms 429.609 <= 550.0
gate_check PASS prefill_warm.mean_actual_prefill_tokens 589.0 >= 500.0
gate_check PASS cache_hit_rows_reuse_suffix 4 / 4
gate_check PASS prefill_warm_rows_no_cache_full_prefill 4 / 4
gate_result PASS
generated_cache_long_safety 36 32 32 True 68 75 68 True True 7
generated_cache_stream_safety 35 12 12 True 47 52 47 True True 5
generated_cache_cancel_safety 0 0 2 0 2
generated_prefix_cache_safety_result PASS
suite_result PASS resident-benchmark-sync-safe-generated-cache-suite-full.jsonl resident-prefill-isolation-sync-safe-generated-cache-suite-full.jsonl generated_cache_safety= True
```

This is the current default acceptance gate for resident-engine cache safety:
cache-hit latency, suffix-only prefill, full warm-prefill isolation, generated
continuation reuse, stream continuation reuse, and cancellation non-pollution
all pass in one command.

## Strict Process Cold-Start Suite

Lifecycle reload captures unload/reload behavior inside an already-running
Python process. Strict cold-start validation needs a separate process so it
includes Python import, MLX/Metal initialization, model load, warmup, and server
startup.

Wrapper:

```bash
python3 benchmarks/python/process_cold_start_suite.py \
  --model /Volumes/StudioStackSSD4TB/Development/LLM/lmstudio/models/mlx-community/gpt-oss-20b-MXFP4-Q8 \
  --port 8766 \
  --tag process-cold-full \
  --requests 6 \
  --prefill-runs 5 \
  --prefix-repeats 24 \
  --max-tokens 8 \
  --prefill-max-tokens 4 \
  --generated-cache-long-max-tokens 32 \
  --generated-cache-stream-max-tokens 12 \
  --generated-cache-cancel-repeats 96 \
  --generated-cache-prefill-step-size 16
```

Behavior:

- Fails fast if the selected port already has a listener.
- Starts `resident_mlx_service.py` as a child process with `--require-gpu`.
- Writes process and health evidence to
  `resident-process-cold-start-<tag>.jsonl`.
- Writes service output to `resident-process-cold-start-<tag>.log`.
- Waits until `/health` reports `ok=true` and `loaded=true`.
- Runs `run_resident_regression_suite.py` against the fresh process.
- Terminates the process group after validation and records the exit code.

Passing evidence:

```text
process_cold_spawned 15989
process_cold_health_ready 16049.67 8578.13 {'metal_available': True, 'default_device': 'Device(gpu, 0)'} [64, 512]
phase full_prefill resident-benchmark-sync-safe-process-cold-full-suite.jsonl 1 490.36 571.00 1.00
phase cache_hit resident-benchmark-sync-safe-process-cold-full-suite.jsonl 4 185.48 8.00 1.00
phase prefill_warm resident-prefill-isolation-sync-safe-process-cold-full-suite.jsonl 4 431.17 586.00 -
gate_check PASS cache_hit.mean_service_request_ms 185.481 <= 250.0
gate_check PASS prefill_warm.mean_service_request_ms 431.17 <= 550.0
gate_check PASS prefill_warm.mean_actual_prefill_tokens 586.0 >= 500.0
gate_result PASS
generated_cache_long_safety 37 32 32 True 69 76 69 True True 7
generated_cache_stream_safety 36 12 12 True 48 53 48 True True 5
generated_cache_cancel_safety 0 0 2 0 2
generated_prefix_cache_safety_result PASS
suite_result PASS resident-benchmark-sync-safe-process-cold-full-suite.jsonl resident-prefill-isolation-sync-safe-process-cold-full-suite.jsonl generated_cache_safety= True
process_cold_suite_done 0 7105.0
process_cold_exit 15989 -15
process_cold_result PASS resident-process-cold-start-process-cold-full.jsonl resident-process-cold-start-process-cold-full.log
```

Interpretation:

- End-to-end process readiness was `16049.67 ms`.
- Service-reported model load was `8578.13 ms`.
- The fresh process stayed on `Device(gpu, 0)`.
- The regression suite passed after true process startup.
- The wrapper cleaned up the process; no listener remained on port `8766`.

## Startup Phase Breakdown

The resident service now exposes startup phase timing through `/health`:

```json
{
  "startup_timings": {
    "parent_start_to_module_import_ms": 349.09,
    "parent_start_to_engine_init_start_ms": 352.53,
    "runtime_device_info_ms": 0.01,
    "validate_model_access_ms": 0.12,
    "detect_backend_ms": 0.41,
    "import_mlx_lm_helpers_ms": 3130.47,
    "profile_discovery_ms": 0.21,
    "load_profile_ms": 0.31,
    "engine_state_init_ms": 0.02,
    "model_load_ms": 6939.15,
    "warmup_ms": 2532.66,
    "engine_init_total_ms": 12603.19,
    "parent_start_to_health_response_ms": 13154.25
  }
}
```

The cold-start wrapper sets `MLX_ENGINE_PARENT_STARTED_AT_EPOCH` before spawning
the service process, so the service can report parent-observed startup
milestones in the same artifact as internal MLX/model timings.

Instrumented validation:

```bash
python3 benchmarks/python/process_cold_start_suite.py \
  --model /Volumes/StudioStackSSD4TB/Development/LLM/lmstudio/models/mlx-community/gpt-oss-20b-MXFP4-Q8 \
  --port 8767 \
  --tag process-cold-phases \
  --requests 6 \
  --prefill-runs 5 \
  --prefix-repeats 24 \
  --max-tokens 8 \
  --prefill-max-tokens 4 \
  --generated-cache-long-max-tokens 32 \
  --generated-cache-stream-max-tokens 12 \
  --generated-cache-cancel-repeats 96 \
  --generated-cache-prefill-step-size 16
```

Passing evidence:

```text
process_cold_spawned 18607
process_cold_health_ready 13151.65 6939.15 {'metal_available': True, 'default_device': 'Device(gpu, 0)'} [64, 512]
process_cold_startup_breakdown 349.09 0.01 3130.47 6939.15 2532.66 13154.25
phase cache_hit resident-benchmark-sync-safe-process-cold-phases-suite.jsonl 4 186.29 8.00 1.00
phase prefill_warm resident-prefill-isolation-sync-safe-process-cold-phases-suite.jsonl 4 436.01 588.00 -
gate_result PASS
generated_prefix_cache_safety_result PASS
suite_result PASS resident-benchmark-sync-safe-process-cold-phases-suite.jsonl resident-prefill-isolation-sync-safe-process-cold-phases-suite.jsonl generated_cache_safety= True
process_cold_suite_done 0 6847.01
process_cold_exit 18607 -15
process_cold_result PASS resident-process-cold-start-process-cold-phases.jsonl resident-process-cold-start-process-cold-phases.log
```

Current startup bottleneck ranking from this run:

1. Model load: `6939.15 ms`.
2. `mlx_lm` helper imports: `3130.47 ms`.
3. Warmup: `2532.66 ms`.
4. Python/process/module startup before engine init: about `352.53 ms`.
5. Profile/config/device/backend checks: effectively negligible for this model.

## Async Warmup Readiness Mode

The resident service now supports three warmup modes:

- `sync`: complete warmup before `/health` can report loaded.
- `async`: report loaded after model load, then complete warmup in a background
  thread.
- `off`: skip startup warmup.

Defaults:

- Direct `resident_mlx_service.py` CLI keeps `sync` for explicit benchmark
  compatibility.
- `run_resident_service.sh` now defaults to `async`, because it is the preferred
  interactive service mode after cold-start validation.

CLI:

```bash
python3 benchmarks/python/resident_mlx_service.py \
  --model "$MODEL" \
  --port 8765 \
  --warmup-mode async \
  --require-gpu
```

Launcher:

```bash
benchmarks/python/run_resident_service.sh "$MODEL" 8765
```

Override launcher warmup mode when needed:

```bash
WARMUP_MODE=sync benchmarks/python/run_resident_service.sh "$MODEL" 8765
WARMUP_MODE=off benchmarks/python/run_resident_service.sh "$MODEL" 8765
```

Launcher validation:

```bash
timeout 20s benchmarks/python/run_resident_service.sh \
  /Volumes/StudioStackSSD4TB/Development/LLM/lmstudio/models/mlx-community/gpt-oss-20b-MXFP4-Q8 \
  8770
```

Evidence:

```text
INFO:     Started server process [63018]
INFO:     Uvicorn running on http://127.0.0.1:8770
INFO:     Finished server process [63018]
```

Post-run listener check confirmed port `8770` was clear.

`/health` now includes:

```json
{
  "warmup": {
    "mode": "async",
    "running": false,
    "completed": true,
    "error": null,
    "result_count": 2
  }
}
```

## Readiness Probe

Async warmup means clients need two distinct readiness concepts:

- loaded readiness: the HTTP service is alive and the model is loaded
- warm readiness: representative prompt warmup has completed

Probe:

```bash
python3 benchmarks/python/wait_resident_ready.py \
  --base-url http://127.0.0.1:8765 \
  --require-gpu
```

Warm-readiness gate:

```bash
bin/mlx-engine ready \
  --base-url http://127.0.0.1:8765 \
  --require-gpu \
  --require-warmup
```

Behavior:

- Exits `0` only when readiness conditions are met.
- Exits `1` on timeout, wrong device, unloaded model, or warmup error.
- Works with new `/health.warmup` responses.
- Backward-compatible with older live processes that only expose
  `warmup_results`.

Live validation against the current resident server:

```text
resident_ready True sync-safe Device(gpu, 0) legacy True 2
resident_ready True sync-safe Device(gpu, 0) legacy True 2
```

The same validation also passes through the packaged CLI:

```bash
bin/mlx-engine ready --base-url http://127.0.0.1:8765 --timeout-s 5 --require-gpu
bin/mlx-engine ready --base-url http://127.0.0.1:8765 --timeout-s 5 --require-gpu --require-warmup
```

Operational rule:

- Service supervisors can use loaded readiness for process liveness.
- Interactive clients and benchmark runners should use `--require-warmup` when
  they want to avoid first-request cold-prefill latency.

Cold-start wrapper validation:

```bash
python3 benchmarks/python/process_cold_start_suite.py \
  --model /Volumes/StudioStackSSD4TB/Development/LLM/lmstudio/models/mlx-community/gpt-oss-20b-MXFP4-Q8 \
  --port 8768 \
  --tag process-cold-async-warmup \
  --warmup-mode async \
  --wait-warmup-before-suite \
  --requests 6 \
  --prefill-runs 5 \
  --prefix-repeats 24 \
  --max-tokens 8 \
  --prefill-max-tokens 4 \
  --generated-cache-long-max-tokens 32 \
  --generated-cache-stream-max-tokens 12 \
  --generated-cache-cancel-repeats 96 \
  --generated-cache-prefill-step-size 16
```

Passing evidence:

```text
process_cold_spawned 58751
process_cold_health_ready 8135.73 4442.99 {'metal_available': True, 'default_device': 'Device(gpu, 0)'} [64, 512]
process_cold_startup_breakdown 342.75 0.01 2966.59 4442.99 0.0 8139.15
process_cold_warmup_ready 1538.82 async 2
phase cache_hit resident-benchmark-sync-safe-process-cold-async-warmup-suite.jsonl 4 174.66 8.00 1.00
phase prefill_warm resident-prefill-isolation-sync-safe-process-cold-async-warmup-suite.jsonl 4 420.60 586.00 -
gate_result PASS
generated_prefix_cache_safety_result PASS
suite_result PASS resident-benchmark-sync-safe-process-cold-async-warmup-suite.jsonl resident-prefill-isolation-sync-safe-process-cold-async-warmup-suite.jsonl generated_cache_safety= True
process_cold_suite_done 0 6650.07
process_cold_exit 58751 -15
process_cold_result PASS resident-process-cold-start-process-cold-async-warmup.jsonl resident-process-cold-start-process-cold-async-warmup.log
```

Interpretation:

- HTTP readiness improved from the prior sync-warmup instrumented result
  `13154.25 ms` to `8139.15 ms`.
- Readiness improved by `5015.10 ms` without disabling warmup.
- Background warmup completed `1538.82 ms` after first health readiness.
- Full warmup completion was about `9678.86 ms` after parent spawn.
- The wrapper waited for warmup before the performance gate, and the full
  regression suite still passed.

## Warmup-Off Validation

`--warmup-mode off` is supported and was validated, but it is not the preferred
interactive default for this model.

Validation:

```bash
python3 benchmarks/python/process_cold_start_suite.py \
  --model /Volumes/StudioStackSSD4TB/Development/LLM/lmstudio/models/mlx-community/gpt-oss-20b-MXFP4-Q8 \
  --port 8769 \
  --tag process-cold-no-warmup \
  --warmup-mode off \
  --wait-warmup-before-suite \
  --requests 6 \
  --prefill-runs 5 \
  --prefix-repeats 24 \
  --max-tokens 8 \
  --prefill-max-tokens 4 \
  --generated-cache-long-max-tokens 32 \
  --generated-cache-stream-max-tokens 12 \
  --generated-cache-cancel-repeats 96 \
  --generated-cache-prefill-step-size 16
```

Passing evidence:

```text
process_cold_spawned 82264
process_cold_health_ready 8652.24 4972.17 {'metal_available': True, 'default_device': 'Device(gpu, 0)'} [64, 512]
process_cold_startup_breakdown 373.26 0.01 2955.78 4972.17 0.0 8654.98
process_cold_warmup_ready 0.83 off 0
phase full_prefill resident-benchmark-sync-safe-process-cold-no-warmup-suite.jsonl 1 2189.62 574.00 1.00
phase cache_hit resident-benchmark-sync-safe-process-cold-no-warmup-suite.jsonl 4 182.60 8.00 1.00
phase prefill_warm resident-prefill-isolation-sync-safe-process-cold-no-warmup-suite.jsonl 4 431.62 588.00 -
gate_result PASS
generated_prefix_cache_safety_result PASS
suite_result PASS resident-benchmark-sync-safe-process-cold-no-warmup-suite.jsonl resident-prefill-isolation-sync-safe-process-cold-no-warmup-suite.jsonl generated_cache_safety= True
process_cold_suite_done 0 8513.66
process_cold_exit 82264 -15
process_cold_result PASS resident-process-cold-start-process-cold-no-warmup.jsonl resident-process-cold-start-process-cold-no-warmup.log
```

Policy conclusion:

- `off` passed the steady regression gate after the first request warmed the
  runtime.
- `off` did not improve readiness versus async in this run:
  `8654.98 ms` off vs `8139.15 ms` async.
- `off` caused the first real full-prefill request to spike to `2189.62 ms`.
- `async` remains the preferred service mode because it reduces HTTP readiness
  by about `5 s` versus sync while still hiding the first-request cold prefill
  penalty once `warmup.completed=true`.

## M9.1 Generated-Cache Edge Hardening

M9.1 closes the highest-risk correctness gap in generated-prefix cache reuse:
generated text can diverge from generated token IDs when an API-level stop
string trims the returned text. Caching that trimmed continuation as if it were
the full generated token sequence would be unsafe.

Implementation:

- added `stop` request support for raw generation, OpenAI completions, OpenAI
  chat completions, and their streaming paths
- added a token-boundary guard in generated-prefix cache recording:
  `prompt + returned_text` must retokenize exactly to
  `prompt_token_ids + generated_token_ids`
- generated-prefix cache storage is skipped with
  `generated_prefix_cache_reason=token_boundary_mismatch` when that invariant
  fails
- added `benchmarks/python/generated_prefix_cache_edge_probe.py`
- integrated the edge probe into `benchmarks/python/run_resident_regression_suite.py`
  and `bin/mlx-engine suite`

Standalone edge validation against the patched server on `127.0.0.1:8773`:

```text
resident_ready True custom Device(gpu, 0) async True 2
health True Device(gpu, 0)
edge_max_token True length 1 True stored True
edge_max_token_followup True True 4 38
edge_stop_trim '\n\nTh' stop 2 False token_boundary_mismatch False 38 39
edge_stream_stop_trim stop 3 False token_boundary_mismatch False
generated_prefix_cache_edge_result PASS
```

Default integrated suite validation:

```text
gate_check PASS cache_hit.mean_service_request_ms 185.045 <= 250.0
gate_check PASS cache_hit.mean_actual_prefill_tokens 8.0 <= 16.0
gate_check PASS prefill_warm.mean_service_request_ms 425.834 <= 550.0
gate_check PASS prefill_warm.mean_actual_prefill_tokens 589.0 >= 500.0
gate_check PASS prefill_cold_to_warm_ratio 0.993 <= 8.0
gate_check PASS cache_hit_rows_reuse_suffix 4 / 4
gate_check PASS prefill_warm_rows_no_cache_full_prefill 4 / 4
gate_result PASS
generated_prefix_cache_safety_result PASS
generated_prefix_cache_edge_result PASS
suite_result PASS resident-benchmark-sync-safe-edge-integrated-suite.jsonl resident-prefill-isolation-sync-safe-edge-integrated-suite.jsonl generated_cache_safety= True generated_cache_edges= True
```

M9.1 result:

- max-token/EOS-style completions still record and reuse generated-prefix cache
  when the token-boundary invariant is safe
- stop-string-trimmed completions and streams do not record unsafe generated
  prefixes
- the default suite now protects this behavior

## M9.2 Concurrent Cancellation Pressure

M9.2 adds an explicit pressure gate for the combined scheduler/cancellation
failure mode: a long prefill stream is cancelled while other foreground clients
are queued behind it.

Implementation:

- added `benchmarks/python/concurrent_cancel_pressure_probe.py`
- integrated it into `benchmarks/python/run_resident_regression_suite.py`
- exposed `bin/mlx-engine suite --skip-concurrent-cancel-pressure` for explicit
  bypasses

The pressure probe verifies:

- one long raw `/generate` stream can be cancelled at prompt-progress time
- the cancelled stream emits no token events
- the request registry retains `status=cancelled`
- queued `/v1/completions` clients complete after cancellation
- scheduler active and queued counts return to zero
- cache entries do not change while cache population is intentionally off

Standalone validation:

```text
resident_ready True custom Device(gpu, 0) async True 2
health True Device(gpu, 0)
concurrent_cancel req_7e9edf0e922e427fba3067a21e1f55db 2 0 cancelling cancelled
concurrent_client 1 962.33 0.0 1183.93 8
concurrent_client 2 738.96 0.0 961.83 8
concurrent_client 3 519.26 0.0 739.13 8
concurrent_client 4 299.95 0.0 519.2 8
concurrent_scheduler 0 5 5 0 504.1 962.33
concurrent_cancel_pressure_result PASS
```

Default integrated suite validation:

```text
gate_check PASS cache_hit.mean_service_request_ms 178.238 <= 250.0
gate_check PASS cache_hit.mean_actual_prefill_tokens 8.0 <= 16.0
gate_check PASS prefill_warm.mean_service_request_ms 424.658 <= 550.0
gate_check PASS prefill_warm.mean_actual_prefill_tokens 587.0 >= 500.0
gate_check PASS prefill_cold_to_warm_ratio 0.981 <= 8.0
gate_check PASS cache_hit_rows_reuse_suffix 4 / 4
gate_check PASS prefill_warm_rows_no_cache_full_prefill 4 / 4
gate_result PASS
generated_prefix_cache_safety_result PASS
generated_prefix_cache_edge_result PASS
concurrent_cancel_pressure_result PASS
suite_result PASS resident-benchmark-sync-safe-concurrent-integrated-suite.jsonl resident-prefill-isolation-sync-safe-concurrent-integrated-suite.jsonl generated_cache_safety= True generated_cache_edges= True concurrent_cancel_pressure= True
```

M9.2 result:

- the safe default remains serialized model execution with bounded queuing
- cancellation under queued foreground pressure is now a default regression gate
- no cache pollution was observed during cancellation pressure with population
  disabled

## Launchd Operational Packaging

The launchd packaging slice now has a repeatable install/uninstall path rather
than only a static plist template.

Files:

- `packaging/launchd/com.jecruz.mlx-engine.plist.template`
- `packaging/launchd/install.sh`
- `packaging/launchd/uninstall.sh`
- `packaging/launchd/README.md`

Installer behavior:

- requires `--model`
- defaults repo root to the current checkout
- defaults label to `com.jecruz.mlx-engine`
- defaults host/port to `127.0.0.1:8765`
- defaults logs to `~/Library/Logs/mlx-engine`
- defaults plist output to `~/Library/LaunchAgents`
- renders `__REPO_ROOT__`, `__MODEL_PATH__`, `__LOG_DIR__`, `__LABEL__`,
  `__HOST__`, `__PORT__`, and `__WARMUP_MODE__`
- runs `plutil -lint` on the rendered plist
- optionally loads the LaunchAgent with `--load`

Uninstaller behavior:

- bootouts the user LaunchAgent if loaded
- removes the rendered plist by default
- keeps the rendered plist when `--keep-plist` is passed

Validation:

```text
packaging/launchd/com.jecruz.mlx-engine.plist.template: OK
/tmp/mlx-engine-launchagents/com.jecruz.mlx-engine.test.plist: OK
mlx_engine_launchd_plist /tmp/mlx-engine-launchagents/com.jecruz.mlx-engine.test.plist
mlx_engine_launchd_logs /tmp/mlx-engine-logs
mlx_engine_launchd_unloaded com.jecruz.mlx-engine.test
mlx_engine_launchd_plist_removed /tmp/mlx-engine-launchagents/com.jecruz.mlx-engine.test.plist
```

Rendered plist spot check:

- program: `bin/mlx-engine serve`
- model:
  `/Volumes/StudioStackSSD4TB/Development/LLM/lmstudio/models/mlx-community/gpt-oss-20b-MXFP4-Q8`
- bind: `127.0.0.1:8774`
- warmup: `async`
- GPU guard: `--require-gpu`

## M13 Profile-Prefill Warmup Latency

M13 tests whether profile-selected warmup improves the first real prompt after a
reload, independent of prefix-cache reuse.

Implementation:

- added `benchmarks/python/profile_prefill_warmup_latency_probe.py`
- reloads the resident engine with `warmup_profile_prefill=false`
- waits for configured async warmup to complete
- prunes prefix cache
- sends the first real prompt and records service/prefill metrics
- repeats the same sequence with `warmup_profile_prefill=true`
- writes JSONL evidence with per-case rows and a summary row

Short-prompt control:

```text
m13_case profile_prefill_off profile_prefill False warmup_results 2 prompt_tokens 1025 prefill_step None service_ms 587.76 actual_prefill 1025
m13_case profile_prefill_on profile_prefill True warmup_results 4 prompt_tokens 1025 prefill_step None service_ms 588.71 actual_prefill 1025
m13_summary delta_ms 0.95 ratio 1.002 profile-prefill-warmup-latency-m13.jsonl
```

Long-prompt profile-band test:

```text
m13_case profile_prefill_off profile_prefill False warmup_results 2 prompt_tokens 4102 prefill_step 2048 service_ms 2032.46 actual_prefill 4102
m13_case profile_prefill_on profile_prefill True warmup_results 4 prompt_tokens 4102 prefill_step 2048 service_ms 2048.37 actual_prefill 4102
m13_summary delta_ms 15.91 ratio 1.008 profile-prefill-warmup-latency-m13-long.jsonl
```

Interpretation:

- Profile-prefill warmup coverage works: the `on` case warmed configured
  targets plus profile-band targets, including the 4096-token band using
  `prefill_step_size=2048`.
- The first real long-prompt request still performed full prefill
  (`actual_prefill_tokens=4102`) and took about the same service time as the
  non-profile-prefill case.
- The measured delta was noise-level/slightly negative in this run:
  `2048.37 ms` on vs `2032.46 ms` off.

M13 result:

- Do not treat profile-selected warmup alone as a first-prompt latency
  optimization.
- Keep it as an operational correctness/readiness feature because it verifies
  profile-band execution paths before traffic.
- For the next performance milestone, focus on reusable compiled prefill graphs,
  prompt-cache construction/reuse, or batching/chunk scheduling rather than
  simply adding more warmup prompts.

## M14 Prefix-Cache Population Mode

M14 compares the current foreground cache-create path against async cache
population. This isolates the latency cost of building the reusable prefix
cache on the populate request.

Implementation:

- added `benchmarks/python/prefix_cache_population_mode_probe.py`
- runs the same repeated-prefix prompt sequence under `sync-safe`
- runs the same sequence under `async-experimental`
- writes per-request rows for baseline, populate, and cache-hit phases
- writes a summary comparing populate request latency and cache-prepare time

622-token validation:

```text
m14_request sync baseline service_ms 2425.78 cache_prepare_ms 0.0 actual_prefill 622 created False scheduled False hit False
m14_request sync populate service_ms 467.6 cache_prepare_ms 315.86 actual_prefill 8 created True scheduled False hit False
m14_request sync hit service_ms 149.25 cache_prepare_ms 0.16 actual_prefill 10 created False scheduled False hit True
m14_request async baseline service_ms 439.93 cache_prepare_ms 0.0 actual_prefill 622 created False scheduled False hit False
m14_request async populate service_ms 444.45 cache_prepare_ms 0.07 actual_prefill 625 created False scheduled True hit False
m14_request async hit service_ms 167.49 cache_prepare_ms 0.18 actual_prefill 10 created False scheduled False hit True
m14_summary populate_improvement_ms 23.15 async_to_sync_ratio 0.95 prefix-cache-population-mode-m14.jsonl
```

Longer 1520-token validation:

```text
m14_request sync baseline service_ms 2898.72 cache_prepare_ms 0.0 actual_prefill 1522 created False scheduled False hit False
m14_request sync populate service_ms 854.33 cache_prepare_ms 699.92 actual_prefill 8 created True scheduled False hit False
m14_request sync hit service_ms 153.82 cache_prepare_ms 0.17 actual_prefill 10 created False scheduled False hit True
m14_request async baseline service_ms 824.95 cache_prepare_ms 0.0 actual_prefill 1521 created False scheduled False hit False
m14_request async populate service_ms 842.08 cache_prepare_ms 0.09 actual_prefill 1524 created False scheduled True hit False
m14_request async hit service_ms 156.47 cache_prepare_ms 0.21 actual_prefill 10 created False scheduled False hit True
m14_summary populate_improvement_ms 12.24 async_to_sync_ratio 0.986 prefix-cache-population-mode-m14-long.jsonl
```

Interpretation:

- Sync cache population gives the populate request suffix-only prefill, but only
  after doing a foreground prefix-cache build.
- Async cache population removes that foreground cache-build stall: cache
  prepare drops from `699.92 ms` to `0.09 ms` in the longer run.
- The async populate request still performs full prefill while the cache is
  scheduled for background construction, so end-to-end populate latency is
  roughly neutral.
- The follow-up request hits the cache in both modes and returns to the fast
  suffix-only path.

M14 result:

- Async cache population should be preferred for interactive throughput modes
  when foreground latency is more important than making the populate request
  itself suffix-only.
- The next real speedup opportunity is to avoid a second prefix prefill during
  cache creation by reusing or slicing the populate request's own prompt-cache
  state safely.

## M15 Request-Derived Prefix Cache

M15 adds an explicit experimental population mode for the next cache
optimization boundary:

- `prefix_cache_population_mode=request`
- deep-copy the request-owned prompt cache after generation
- trim generated tokens plus the non-shared suffix from that copy
- store the remaining matched-prefix cache for the next related request
- fall back to async population when the active `mlx-lm` cache stack is not
  safely trimmable

This keeps the safe default unchanged while giving the engine a concrete
runtime path for future zero-extra-prefill cache population on models whose MLX
cache classes support trimming.

Validation probe:

- `benchmarks/python/request_prefix_cache_probe.py`
- compares `async-experimental` against `request`
- verifies populate behavior and follow-up cache hit behavior
- fails if request mode neither stores from the request-owned prompt cache nor
  uses the explicit safe fallback

Live validation against:

```text
/Volumes/StudioStackSSD4TB/Development/LLM/lmstudio/models/mlx-community/gpt-oss-20b-MXFP4-Q8
```

Result:

```text
m15_request async baseline service_ms 1148.17 cache_prepare_ms 0.0 actual_prefill 1520 stored_from_request False scheduled False hit False
m15_request async populate service_ms 827.14 cache_prepare_ms 0.1 actual_prefill 1523 stored_from_request False scheduled True hit False
m15_request async hit service_ms 162.66 cache_prepare_ms 0.22 actual_prefill 7 stored_from_request False scheduled False hit True
m15_request request baseline service_ms 833.58 cache_prepare_ms 0.0 actual_prefill 1523 stored_from_request False scheduled False hit False
m15_request request populate service_ms 832.39 cache_prepare_ms 0.1 actual_prefill 1526 stored_from_request False scheduled True hit False
m15_request request hit service_ms 151.76 cache_prepare_ms 0.2 actual_prefill 7 stored_from_request False scheduled False hit True
m15_summary populate_improvement_ms -5.25 request_populate_ms 832.39 async_populate_ms 827.14 request-prefix-cache-m15.jsonl
```

Interpretation:

- `gpt-oss-20b-MXFP4-Q8` does not currently allow safe request-cache trimming;
  `mlx-lm` reports at least one prompt-cache component as non-trimmable.
- Request mode therefore recorded
  `cache_request_store_reason=not_trimmable_fallback_async`.
- The fallback preserved correctness: the populate request scheduled background
  cache creation and the next request hit the prefix cache with suffix-only
  prefill.
- There is no speedup for this model in M15 because the zero-extra-prefill path
  is correctly disabled by the cache-class guard.

M15 result:

- The engine now has a safe experimental request-derived prefix-cache mode.
- For non-trimmable cache stacks, it degrades to async population instead of
  pretending request slicing is valid.
- The next performance milestone should validate this mode on a Qwen MLX model
  with trimmable KV cache classes, then compare request-derived population
  against async rebuild on 1.5k, 4k, and 8k repeated-prefix prompts.

## M16 Qwen Request-Cache Validation

M16 applies the M15 request-cache guardrail to a local Qwen MLX package and
hardens model loading/observability around that path.

Implementation:

- backend detection now treats text generation architectures such as
  `Qwen3_5ForConditionalGeneration` and `Qwen3_5MoeForConditionalGeneration`
  as text models even when the converted config includes `vision_config`
- resident loading still attempts normal strict `mlx-lm` loading first
- if strict loading fails only because the package includes extra
  `language_model.vision_tower.*` tensors, the engine retries text loading with
  `strict=False`
- `/health` and `/engine` expose:
  - `load_strict`
  - `load_fallback_reason`
  - `prompt_cache_capabilities.entry_count`
  - `prompt_cache_capabilities.all_trimmable`
  - `prompt_cache_capabilities.classes`

Validated model:

```text
/Volumes/StudioStackSSD4TB/Development/LLM/lmstudio/models/unsloth/Qwen3.6-35B-A3B-UD-MLX-4bit
```

Health evidence:

```text
m16_health True False extra_vision_tower_weights_ignored False ['ArraysCache', 'KVCache'] Device(gpu, 0)
```

Request-cache probe:

```text
m15_capabilities async entries 40 all_trimmable False classes ArraysCache,KVCache
m15_request async baseline service_ms 1013.8 cache_prepare_ms 0.0 actual_prefill 628 stored_from_request False scheduled False hit False
m15_request async populate service_ms 519.63 cache_prepare_ms 0.05 actual_prefill 631 stored_from_request False scheduled True hit False
m15_request async hit service_ms 225.97 cache_prepare_ms 0.21 actual_prefill 7 stored_from_request False scheduled False hit True
m15_capabilities request entries 40 all_trimmable False classes ArraysCache,KVCache
m15_request request baseline service_ms 489.48 cache_prepare_ms 0.0 actual_prefill 624 stored_from_request False scheduled False hit False
m15_request request populate service_ms 487.47 cache_prepare_ms 0.05 actual_prefill 627 stored_from_request False scheduled True hit False
m15_request request hit service_ms 205.3 cache_prepare_ms 0.2 actual_prefill 7 stored_from_request False scheduled False hit True
m15_summary populate_improvement_ms 32.16 request_populate_ms 487.47 async_populate_ms 519.63 request-prefix-cache-m16-qwen-a3b.jsonl
```

Interpretation:

- The local Qwen A3B package is now usable by the resident text engine despite
  extra vision-tower tensors in the checkpoint.
- The model's prompt cache is not wholly trimmable because its cache stack
  includes `ArraysCache`.
- Request-derived prefix-cache storage is therefore correctly disabled for this
  model and falls back to async population:
  `cache_request_store_reason=not_trimmable_fallback_async`.
- The follow-up request still reaches the fast cache-hit path with suffix-only
  prefill.

M16 result:

- Qwen local-package loading is more robust.
- Cache-class capability telemetry is now explicit.
- Request-derived prefix slicing remains gated off for Qwen A3B until
  `ArraysCache` can be trimmed safely or a fully trimmable Qwen text package is
  found.

## M17 Recurrent-Cache Slicing Safety

M17 resolves the open question from M16: whether `ArraysCache` should be made
trimmable for request-derived prefix-cache storage.

Source inspection:

- `mlx_lm.models.qwen3_5.TextModel.make_cache()` returns
  `ArraysCache(size=2)` for linear layers and `KVCache()` for full-attention
  layers.
- Qwen3.5 linear layers store:
  - `cache[0]`: convolution state
  - `cache[1]`: gated-delta recurrent state
- That state is the result after processing the sequence. It is not an
  append-only KV tensor with a suffix time dimension that can be removed to
  recover an earlier prefix state.

Implementation:

- added explicit trim-blocker classification for prompt-cache entries
- `ArraysCache` is classified as
  `array_or_recurrent_state_not_suffix_trimmable`
- `CacheList` blockers include child blocker reasons
- `/health` and `/engine` now expose:
  - `prompt_cache_capabilities.trimmable_entries`
  - `prompt_cache_capabilities.non_trimmable_entries`
  - `prompt_cache_capabilities.non_trimmable_classes`
  - `prompt_cache_capabilities.trim_blocker_reasons`
- `benchmarks/python/request_prefix_cache_probe.py` now fails if request mode
  stores from a non-trimmable cache stack, and specifically enforces the
  `ArraysCache` fallback path

Live Qwen validation:

```text
m15_capabilities async entries 40 all_trimmable False non_trimmable 30 blockers array_or_recurrent_state_not_suffix_trimmable classes ArraysCache,KVCache
m15_request async populate service_ms 491.42 cache_prepare_ms 0.05 actual_prefill 629 stored_from_request False scheduled True hit False
m15_request async hit service_ms 207.61 cache_prepare_ms 0.21 actual_prefill 7 stored_from_request False scheduled False hit True
m15_capabilities request entries 40 all_trimmable False non_trimmable 30 blockers array_or_recurrent_state_not_suffix_trimmable classes ArraysCache,KVCache
m15_request request populate service_ms 490.71 cache_prepare_ms 0.05 actual_prefill 630 stored_from_request False scheduled True hit False
m15_request request hit service_ms 204.07 cache_prepare_ms 0.2 actual_prefill 7 stored_from_request False scheduled False hit True
m15_summary populate_improvement_ms 0.71 request_populate_ms 490.71 async_populate_ms 491.42 request-prefix-cache-m17-qwen-a3b-safety.jsonl
```

M17 result:

- `ArraysCache` is intentionally not made trimmable.
- Request-derived prefix-cache slicing is correctly blocked for Qwen3.5
  recurrent/linear-attention layers.
- The safe next optimization is split-prefill population: prefill the matched
  prefix into a cache, store/copy that prefix cache, then continue the same
  request through the suffix. That avoids suffix trimming and avoids an
  additional background rebuild.

## M18 Split-Prefill Request Population

M18 implements the safe follow-up to M17 for recurrent Qwen cache stacks.

Before M18, `prefix_cache_population_mode=request` behaved this way for
non-trimmable cache stacks:

- full-prefill the populate request
- discover that request-owned cache trimming is unsafe
- schedule an async background prefix-cache build
- next related request gets the cache hit after the background build

M18 changes that path to split-prefill:

- when request mode sees a non-trimmable prompt-cache stack, it builds the
  matched prefix cache synchronously
- stores that prefix cache immediately
- passes a copy of that prefix cache into the current request
- runs only the uncached suffix tokens for the populate request
- does not schedule an async rebuild

New request metrics:

- `cache_split_prefill`
- `cache_split_prefill_reason`

Live Qwen validation:

```text
m15_capabilities async entries 40 all_trimmable False non_trimmable 30 blockers array_or_recurrent_state_not_suffix_trimmable classes ArraysCache,KVCache
m15_request async populate service_ms 493.64 cache_prepare_ms 0.05 actual_prefill 630 stored_from_request False split_prefill False scheduled True hit False
m15_request async hit service_ms 204.0 cache_prepare_ms 0.21 actual_prefill 7 stored_from_request False split_prefill False scheduled False hit True
m15_capabilities request entries 40 all_trimmable False non_trimmable 30 blockers array_or_recurrent_state_not_suffix_trimmable classes ArraysCache,KVCache
m15_request request populate service_ms 531.53 cache_prepare_ms 321.0 actual_prefill 9 stored_from_request False split_prefill True scheduled False hit False
m15_request request hit service_ms 211.41 cache_prepare_ms 0.21 actual_prefill 7 stored_from_request False split_prefill False scheduled False hit True
m15_summary populate_improvement_ms -37.89 request_populate_ms 531.53 async_populate_ms 493.64 request-prefix-cache-m18-qwen-a3b-split.jsonl
```

M18 result:

- Request mode no longer does full-prefill-plus-background-rebuild for
  non-trimmable Qwen recurrent cache stacks.
- Populate request prefill work drops from the full prompt (`630` tokens in the
  async case) to suffix-only (`9` tokens) after foreground prefix preparation.
- The foreground prefix preparation cost is visible as `cache_prepare_ms`
  (`321.00 ms` in the short validation).
- At ~630 prompt tokens, async remains slightly faster end-to-end because the
  rebuild runs outside the populate request path. Split-prefill should be
  retested at 1.5k, 4k, and 8k contexts where avoiding full populate prefill and
  avoiding a background rebuild should have more value.

## M19 Split-Prefill Length Sweep

M19 adds a repeatable length sweep for the request split-prefill path:

- `benchmarks/python/request_prefix_cache_length_sweep.py`
- runs async and request modes at multiple repeated-prefix sizes
- writes per-request rows plus a per-length summary
- reports actual populate prefill tokens, populate latency, and cache-hit
  latency

Live Qwen A3B sweep:

```text
m19_length 24 async_populate_ms 492.09 request_populate_ms 530.38 delta_ms -38.29 async_prefill 628 request_prefill 9
m19_length 60 async_populate_ms 832.92 request_populate_ms 869.1 delta_ms -36.18 async_prefill 1531 request_prefill 9
m19_length 120 async_populate_ms 1497.13 request_populate_ms 1546.66 delta_ms -49.52 async_prefill 3031 request_prefill 9
m19_summary best_repeats 60 best_delta_ms -36.18 request-prefix-cache-length-sweep-m19-qwen-a3b.jsonl
```

Interpretation:

- Split-prefill is doing the intended work-shape change: populate-request
  `actual_prefill_tokens` stays at `9` while async full-prefills `628`, `1531`,
  and `3031` tokens.
- Cache-hit latency remains good and comparable after either population mode.
- Split-prefill still does not win end-to-end through ~3k prompt tokens because
  foreground prefix preparation costs nearly as much as the async path's full
  populate prefill.
- Async remains better for interactive populate latency, while split-prefill is
  useful as a correctness and scheduling primitive because it avoids duplicate
  background cache construction.

M19 result:

- No positive latency crossover was found through the tested Qwen A3B prompt
  range.
- The next performance target should be prefix-build amortization, not more
  suffix trimming:
  - share an in-flight prefix build across queued requests
  - schedule prefix builds admission-aware so foreground requests do not absorb
    the build cost
  - investigate lower-level MLX cache continuation APIs that can store the
    matched prefix without replaying it in foreground request handling

## M20 Async Prefix-Build Amortization

M20 makes duplicate async prefix-build sharing observable and testable.

Before M20, the engine already avoided adding the same key to
`prefix_cache_pending_builds` twice, but that behavior was implicit. The service
did not expose whether a related request arrived while a matching async prefix
build was already pending, so the scheduler could not reason about amortization.

M20 adds:

- prefix-cache policy counters:
  - `existing_build_reuses`
  - `pending_build_deduplications`
- per-request metrics:
  - `cache_build_deduplicated`
  - `cache_build_dedup_reason`
- `benchmarks/python/async_prefix_build_amortization_probe.py`

Live Qwen A3B validation:

```text
m20_health True custom 0 0 0
m20_request baseline service_ms 1285.07 scheduled False pending False dedup False hit False actual_prefill 1343
m20_request schedule service_ms 771.2 scheduled True pending False dedup False hit False actual_prefill 1346
m20_request duplicate_pending service_ms 772.63 scheduled False pending True dedup True hit False actual_prefill 1350
m20_request hit service_ms 217.74 scheduled False pending False dedup False hit True actual_prefill 9
m20_summary started_delta 1 completed_delta 1 dedup_delta 1 async-prefix-build-amortization-m20-qwen-a3b.jsonl
```

Interpretation:

- The first related request schedules exactly one async prefix build.
- The duplicate related request sees `cache_pending=True` and
  `cache_build_deduplicated=True` with reason `pending_async_build`.
- The policy counter `pending_build_deduplications` increments by `1`.
- The async build starts once and completes once.
- The follow-up request hits the completed prefix cache and drops actual prefill
  to `9` tokens.

M20 result:

- In-flight prefix builds are now a measured resource rather than an implicit
  side effect.
- Duplicate async background rebuilds are prevented and observable.
- The duplicate foreground request still performs full prefill because M20 only
  deduplicates the background build. M21 should use these counters and pending
  state to add admission-aware scheduling: if a matching prefix build is pending
  and likely near completion, a foreground request can wait briefly and convert
  into a cache hit instead of doing full prefill.

## M21 Admission-Aware Pending-Build Wait

M21 converts the M20 pending-build signal into a request-path scheduling
decision.

The key scheduler issue is that an admitted foreground request counts as active.
Async prefix builders intentionally wait until the scheduler is idle before
building, so a foreground request cannot simply block inside cache preparation
and wait for the builder: that would keep the scheduler non-idle and prevent the
builder from running. M21 handles this by temporarily releasing the scheduler
active slot while the request waits for the matching pending prefix build, then
reacquiring the slot before generation continues.

M21 adds:

- runtime config:
  - `prefix_cache_pending_wait_ms`
- prefix-cache policy counters:
  - `pending_waits`
  - `pending_wait_hits`
  - `pending_wait_timeouts`
  - `pending_wait_misses`
  - `pending_wait_total_ms`
- per-request metrics:
  - `cache_pending_wait_ms`
  - `cache_pending_wait_result`
- `benchmarks/python/async_prefix_pending_wait_probe.py`

Live Qwen A3B validation:

```text
m21_health True custom 0 0 0
m21_request baseline service_ms 1185.13 scheduled False pending False wait_result None hit False actual_prefill 1222
m21_request schedule service_ms 717.99 scheduled True pending False wait_result None hit False actual_prefill 1226
m21_request wait_hit service_ms 1267.09 scheduled False pending True wait_result hit hit True actual_prefill 10
m21_summary started_delta 1 completed_delta 1 waits_delta 1 wait_hits_delta 1 async-prefix-pending-wait-m21-qwen-a3b.jsonl
```

Interpretation:

- The schedule request starts exactly one async prefix build.
- The duplicate request sees the matching build pending and waits
  `1053.43 ms`.
- While waiting, it releases its scheduler active slot so the background build
  can pass the idle gate.
- The duplicate request resumes with `cache_hit=True` and only `10` actual
  prefill tokens instead of full-prefilling the `1229` token prompt.

M21 result:

- Pending async prefix construction can now improve foreground duplicate-request
  prefill shape when the caller enables `prefix_cache_pending_wait_ms`.
- The wait remains opt-in so default async behavior keeps low-latency
  foreground execution unless a product/profile explicitly trades wait time for
  reduced prefill work.
- M22 should move below request-level scheduling and investigate lower-level
  MLX cache continuation or cache materialization hooks so the engine can avoid
  replaying the matched prefix for both the scheduling request and follow-up
  requests.

## M22 Lower-Level MLX Cache Continuation Readiness

M22 audits whether the current `mlx-lm` cache stack can safely support a
generic replay-free prefix-store path below request scheduling.

The installed runtime is `mlx-lm 0.30.7`. Source inspection shows:

- `KVCache` exposes offset, update, state, and trim semantics.
- Qwen3.5/Next linear-attention layers use `ArraysCache`.
- `ArraysCache` stores recurrent array state, but does not expose offset or
  trim semantics. It can be copied and reused as a completed prefix state, but
  it cannot be generically suffix-trimmed or partially materialized without
  model-specific recurrent-state rules.

M22 adds runtime continuation reporting:

- `prompt_cache_continuation`
- `native_replay_free_prefix_store_supported`
- `replay_free_supported_entries`
- `blocked_entries`
- `blocked_classes`
- `blocker_reasons`
- `safe_request_prefix_store_strategy`
- `required_lower_level_work`
- `benchmarks/python/cache_continuation_capabilities_probe.py`

Live Qwen A3B validation:

```text
m22_continuation mlx_lm 0.30.7 entries 40 native_replay_free False supported 10 blocked 30 blocked_classes ArraysCache strategy split_prefill_or_async_build cache-continuation-capabilities-m22-qwen-a3b.json
```

Probe payload:

```json
{
  "blocked_classes": ["ArraysCache"],
  "blocked_entries": 30,
  "blocker_reasons": ["arrays_cache_has_recurrent_state_without_offset_or_trim"],
  "capability_classes": ["ArraysCache", "KVCache"],
  "entry_count": 40,
  "mlx_lm_version": "0.30.7",
  "native_replay_free_prefix_store_supported": false,
  "non_trimmable_entries": 30,
  "replay_free_supported_entries": 10,
  "required_lower_level_work": "model_specific_recurrent_state_continuation_for_arrays_cache",
  "safe_request_prefix_store_strategy": "split_prefill_or_async_build"
}
```

M22 result:

- A generic lower-level replay-free prefix-store optimization is unsafe for the
  Qwen3.5/Next cache stack because 30 of 40 cache entries are recurrent
  `ArraysCache` entries without offset/trim semantics.
- The safe engine strategy remains split-prefill, async build, and M21
  pending-build waiting until model-specific recurrent continuation is designed.
- M23 should package these controls into an operator-ready engine surface:
  presets, documented settings, probes, and a concise readiness checklist for
  the Mac local-inference product path.
