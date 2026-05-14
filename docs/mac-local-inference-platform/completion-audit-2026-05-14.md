# MLX Engine Completion Audit - 2026-05-14

## Objective

Execute the current MLX resident-engine plan to completion for the local Mac
inference milestone.

This audit treats completion as a concrete artifact checklist, not as effort
spent. The milestone is complete when the resident engine has a stable command
surface, correctness and performance gates, cache/cancellation safety coverage,
operational packaging, documented evidence, and a clear boundary for work
deferred to the next milestone.

## Checklist

| Requirement | Artifact | Evidence | Status |
| --- | --- | --- | --- |
| Resident engine package boundary | `mlx_engine/resident_service.py`, `mlx_engine/__init__.py`, `mlx_engine/README.md` | Stable service code moved out of benchmark-only path; compatibility wrapper retained at `benchmarks/python/resident_mlx_service.py` | Complete |
| CLI command surface | `bin/mlx-engine` | Provides `serve`, `ready`, `smoke`, `suite`, and `correctness`; `serve` defaults to async warmup; Ctrl-C exits cleanly with code `130` instead of wrapper traceback | Complete |
| Readiness gates | `benchmarks/python/wait_resident_ready.py`, `bin/mlx-engine ready` | Validated loaded/GPU readiness and warm readiness; supports legacy `warmup_results` and new `warmup` health shape | Complete |
| Regression suite | `benchmarks/python/run_resident_regression_suite.py`, `bin/mlx-engine suite` | Runs benchmark harness, comparison, regression gate, generated-cache safety, generated-cache edge, and concurrent-cancel pressure probes by default | Complete |
| Prefix-cache performance gate | `benchmarks/python/resident_regression_gate.py` | Latest default suite: cache-hit mean `178.238 ms`, actual prefill `8.0` tokens, warm-prefill mean `424.658 ms`, warm-prefill tokens `587.0`, `gate_result PASS` | Complete |
| Generated-prefix cache safety | `benchmarks/python/generated_prefix_cache_safety_probe.py` | Latest default suite: long generated continuation, streaming continuation, and cancelled-prefill non-pollution passed | Complete |
| Stop-string/token-boundary cache correctness | `benchmarks/python/generated_prefix_cache_edge_probe.py` | Latest default suite: max-token cache path recorded safely; stop-trimmed non-streaming and streaming paths returned `token_boundary_mismatch`; `generated_prefix_cache_edge_result PASS` | Complete |
| Concurrent cancellation pressure | `benchmarks/python/concurrent_cancel_pressure_probe.py` | Latest default suite: cancellable stream emitted no tokens, four queued clients completed, scheduler returned idle, `concurrent_cancel_pressure_result PASS` | Complete |
| Startup policy | `benchmarks/python/process_cold_start_suite.py`, `docs/mac-local-inference-platform/engine-plan.md` | Async warmup reduced HTTP readiness from `13154.25 ms` to `8139.15 ms`; warmup-off was worse for interactive use and caused first-request spike | Complete for this milestone |
| Launchd operational packaging | `packaging/launchd/com.jecruz.mlx-engine.plist.template`, `install.sh`, `uninstall.sh`, `README.md` | Template lint passed; rendered plist lint passed; temporary install/uninstall validated; renderer XML-escapes substituted values | Complete |
| Run artifact hygiene | `.gitignore` | `*.jsonl`, `resident-*.log`, and `resident-service-*.log` ignored; generated run artifacts are not visible in normal status | Complete |
| Documentation | `docs/mac-local-inference-platform/engine-plan.md`, `progress.md`, this audit | M9.1, M9.2, startup policy, packaging, validation outputs, and next boundary documented | Complete |

## Latest Integrated Gate

Fresh patched server target:

```text
http://127.0.0.1:8773
```

Command:

```bash
bin/mlx-engine suite \
  --base-url http://127.0.0.1:8773 \
  --tag concurrent-integrated-suite
```

Evidence:

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

## Packaging Validation

Template:

```text
packaging/launchd/com.jecruz.mlx-engine.plist.template: OK
```

Rendered temporary plist:

```text
/tmp/mlx-engine-launchagents/com.jecruz.mlx-engine.test.plist: OK
mlx_engine_launchd_plist /tmp/mlx-engine-launchagents/com.jecruz.mlx-engine.test.plist
mlx_engine_launchd_logs /tmp/mlx-engine-logs
mlx_engine_launchd_unloaded com.jecruz.mlx-engine.test
mlx_engine_launchd_plist_removed /tmp/mlx-engine-launchagents/com.jecruz.mlx-engine.test.plist
```

Escaping check:

```text
/tmp/mlx-engine-launchagents/com.jecruz.mlx-engine.escape.plist: OK
mlx_engine_launchd_plist /tmp/mlx-engine-launchagents/com.jecruz.mlx-engine.escape.plist
mlx_engine_launchd_logs /tmp/mlx-engine-logs & special
mlx_engine_launchd_unloaded com.jecruz.mlx-engine.escape
mlx_engine_launchd_plist_removed /tmp/mlx-engine-launchagents/com.jecruz.mlx-engine.escape.plist
```

## Source Manifest

Core engine and CLI:

- `mlx_engine/resident_service.py`
- `mlx_engine/__init__.py`
- `mlx_engine/README.md`
- `bin/mlx-engine`

Regression and validation:

- `benchmarks/python/run_resident_regression_suite.py`
- `benchmarks/python/resident_benchmark_harness.py`
- `benchmarks/python/resident_regression_gate.py`
- `benchmarks/python/generated_prefix_cache_safety_probe.py`
- `benchmarks/python/generated_prefix_cache_edge_probe.py`
- `benchmarks/python/concurrent_cancel_pressure_probe.py`
- `benchmarks/python/wait_resident_ready.py`
- `benchmarks/python/process_cold_start_suite.py`
- `benchmarks/python/cancel_request_probe.py`
- `benchmarks/python/scheduler_admission_probe.py`
- `benchmarks/python/config_policy_probe.py`
- `benchmarks/python/memory_pressure_probe.py`
- `benchmarks/python/async_prefix_cache_probe.py`
- `benchmarks/python/exact_prefix_cache_probe.py`
- `benchmarks/python/generated_prefix_cache_probe.py`
- `benchmarks/python/openai_sse_progress_probe.py`
- `benchmarks/python/live_prompt_progress_probe.py`
- `benchmarks/python/prompt_progress_probe.py`
- `benchmarks/python/smoke_resident_service.py`

Model/static correctness and benchmark support:

- `benchmarks/python/qwen_imrope_static_probe.py`
- `benchmarks/python/vlm_processor_static_probe.py`
- `benchmarks/python/vlm_prompt_decode_bench.py`
- `benchmarks/python/inprocess_prompt_sweep.py`
- `benchmarks/python/prefill_profile.py`
- `benchmarks/python/prefix_latency_sweep.py`
- `benchmarks/python/prefix_opportunity_sweep.py`
- `benchmarks/python/compare_resident_benchmarks.py`
- `benchmarks/python/summarize_prompt_sweep.py`
- `benchmarks/python/run_prompt_sweep.sh`
- `benchmarks/python/run_resident_service.sh`

Packaging:

- `packaging/launchd/com.jecruz.mlx-engine.plist.template`
- `packaging/launchd/install.sh`
- `packaging/launchd/uninstall.sh`
- `packaging/launchd/README.md`

Documentation and evidence:

- `docs/mac-local-inference-platform/engine-plan.md`
- `docs/mac-local-inference-platform/progress.md`
- `docs/mac-local-inference-platform/findings.md`
- `docs/mac-local-inference-platform/qwen-imrope-parity.md`
- `docs/mac-local-inference-platform/inference-correctness-risks.md`
- `docs/mac-local-inference-platform/m4-resident-engine-evidence.md`
- `docs/mac-local-inference-platform/m5-hardening-evidence.md`
- `docs/mac-local-inference-platform/native-overlap-audit.md`
- `docs/mac-local-inference-platform/benchmark-checkpoint-2026-05-13.md`
- `docs/mac-local-inference-platform/verified-mlx-research-results.md`
- `docs/mac-local-inference-platform/github-mlx-project-research.md`
- `docs/mac-local-inference-platform/pi-minimax-mlx-project-research.md`
- `docs/mac-local-inference-platform/pi-mlx-project-research-raw.md`
- `docs/mac-local-inference-platform/gpu-sweep.md`
- `docs/mac-local-inference-platform/completion-audit-2026-05-14.md`

Model profile/static reports:

- `gpt-oss-20b-MXFP4-Q8-prefill-profile.json`
- `qwen3_6-imrope-parity-report.json`
- `qwen3_6-vlm-processor-static-report.json`

## Deferred Boundary

The following work is intentionally not part of this completed milestone:

- native C++/Metal kernel work
- true continuous batching
- speculative decoding
- image/VLM runtime serving
- deeper startup reduction beyond async warmup and documented warmup policy

Those should be planned as the next performance milestone after this resident
engine baseline is reviewed and committed.
