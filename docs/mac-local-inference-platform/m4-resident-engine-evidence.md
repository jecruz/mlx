# M4 Resident Engine Evidence

## Current M4 Slice

The resident MLX service has moved from a benchmark helper toward a reusable local engine surface.

Implemented in this slice:

- profile auto-discovery when `--profile` is omitted
- launcher support for explicit profile, discovered profile, or port-only invocation
- `/metrics` endpoint
- request IDs and created timestamps
- effective policy reporting
- stop reason reporting
- in-memory aggregate and recent-request metrics
- OpenAI-style `/v1/completions`
- OpenAI-style `/v1/chat/completions`
- streaming SSE for `/v1/completions`
- streaming SSE for `/v1/chat/completions`
- streaming JSONL for `/generate`
- `/engine` lifecycle metadata endpoint
- `/engine/reload` same-model/profile reload endpoint
- repeatable smoke client at `benchmarks/python/smoke_resident_service.py`
- packaged CLI wrapper at `bin/mlx-engine`
- packaged `smoke` and `correctness` gates

## Validation

The service was restarted in the Metal-capable tmux shell without an explicit profile argument:

```bash
MODEL="/Volumes/StudioStackSSD4TB/Development/LLM/lmstudio/models/mlx-community/gpt-oss-20b-MXFP4-Q8"
benchmarks/python/run_resident_service.sh "$MODEL" 8765
```

It discovered:

```text
/Users/jeffreycruz/Development/LLM_INFERENCE/mlx/.worktrees/prompt-processing-bench/gpt-oss-20b-MXFP4-Q8-prefill-profile.json
```

Smoke command:

```bash
python3 benchmarks/python/smoke_resident_service.py --base-url http://127.0.0.1:8765
```

Latest smoke output:

```text
health True Device(gpu, 0) /Users/jeffreycruz/Development/LLM_INFERENCE/mlx/.worktrees/prompt-processing-bench/gpt-oss-20b-MXFP4-Q8-prefill-profile.json 0
generate req_91229b1ccf67446f839469ab8383f374 memory_saver 512 9 8 length
completion text_completion length 13 memory_saver
chat chat.completion assistant 77 512
stream_completion 5 True
stream_chat 6 True
metrics 5 5 0 5
```

Latest lifecycle-inclusive smoke output:

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

```bash
bin/mlx-engine smoke --base-url http://127.0.0.1:8765
bin/mlx-engine correctness --base-url http://127.0.0.1:8765
```

Output:

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

## Acceptance Coverage

| M4 acceptance item | Status |
| --- | --- |
| service can run independently | Partial: script starts the resident service from model path and optional profile |
| repeated requests without reload | Pass: smoke run issued generate, completion, and chat requests against one resident process |
| expose metrics | Pass: `/metrics` and health-embedded metrics validated |
| select prompt policy from model profile | Pass: no-profile restart discovered the profile and selected `memory_saver` / `prefill_step_size=512` for short prompts |
| API compatibility layer | Partial: non-streaming OpenAI-style completion and chat endpoints are implemented |
| streaming responses | Pass: completion and chat SSE streams emitted chunks and `[DONE]`; raw `/generate` supports JSONL streaming |
| model unload/reload policy | Partial: `/engine/reload` can replace the resident engine after loading a replacement; explicit unload and memory-pressure policy remain |
| packaging | Pass: `bin/mlx-engine` provides `serve`, `smoke`, and `correctness` commands |
| deterministic correctness gates | Partial: `bin/mlx-engine correctness` validates profile/device/API/token contract; exact repeat-text assertion is available with `--expect-same-text` but not used as the default sampler gate |

## Next M4 Cut

M4 is ready to close for the current prototype-to-engine milestone. Remaining work should move into the next milestone as hardening:

- explicit unload and memory-pressure policy
- launchd/app-helper packaging
- full VLM processor validation
- exact deterministic-text parity once sampler controls are model-family-specific
