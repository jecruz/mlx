# Native Overlap Audit: MLX vs llama.cpp / puma.cpp / panthro.cpp

## Goal

Use prior llama.cpp-family fixes and optimizations to guide MLX performance work
without blindly porting incompatible code.

## Summary

MLX does not embed llama.cpp, ggml, or llama-server as its inference runtime.
The overlap is mostly semantic:

- GGUF format semantics
- RoPE, MROPE, and IMROPE correctness
- Metal kernel performance
- quantized weight handling
- KV-cache behavior
- scheduler and batching behavior
- benchmark shapes and acceptance criteria

## Audit Matrix

| Domain | Direct source overlap | Current MLX state | Prior puma/panthro relevance | M8 action |
| --- | --- | --- | --- | --- |
| GGUF parsing | No llama.cpp parser. MLX uses `gguf-tools` via `gguflib`. | `mlx/io/CMakeLists.txt` fetches `antirez/gguf-tools` and forces `-UNDEBUG` so malformed tensor header asserts stay live in release builds. | Useful as hardening comparison, but not a direct code port. | Keep as already-hardened item; compare malformed-file behavior only if GGUF import becomes product-critical. |
| GGUF quant support | No direct llama.cpp quant loader. | MLX core GGUF path handles `Q4_0`, `Q4_1`, and `Q8_0`; current MLX-format models usually use safetensors instead. | llama.cpp supports many more quant types. | Candidate only if MLX engine must directly load GGUF; otherwise not on critical path. |
| RoPE / IMROPE | No direct ggml RoPE code. | MLX core has a generic Metal RoPE kernel; Qwen3.6 IMROPE behavior is in MLX-VLM model code. | puma/panthro IMROPE sector rule was the correctness reference. | Already validated for tested Qwen3.6 dense and MoE checkpoints; no core MLX port needed yet. |
| Metal fused kernels | No direct source overlap. | MLX has independent Metal kernels for RoPE, attention, matmul, normalization, quantized ops, etc. | puma reports fused RMS_NORM/MUL/ROPE wins for Qwen3.x. | Candidate optimization: inspect whether MLX graph/JIT can fuse the same sequence or whether a custom fused op is worthwhile. |
| KV-cache reuse | No direct source overlap. | Resident service now reuses MLX prompt caches for repeated prefixes. | llama.cpp/puma/panthro KV-cache discipline is useful for acceptance criteria and cache safety. | M7 completed conservative prefix-cache reuse; M8 should add memory-pressure and eviction metrics. |
| Scheduler / batching | No direct source overlap. | M8 added admission control and queue metrics; no continuous batching yet. | llama.cpp server scheduling is a useful comparison point. | Continue M8 with queue policy, concurrency safety, and potential continuous batching study. |
| Prompt-processing benchmark shape | No direct source overlap. | MLX sweeps now measure full-prefill, cache-create, and cache-hit phases. | llama-bench/puma benchmark discipline informs pp/tg shapes. | Keep using pp-style 2k/4k/8k sweeps and compare against puma/panthro when model formats are comparable. |

## Already Validated

- Qwen3.6 dense and MoE MLX checkpoints match the puma/panthro IMROPE lane
  ownership rule.
- The MLX GGUF dependency already preserves malformed-header asserts in release
  builds with `-UNDEBUG`.
- Repeated-prefix prompt processing has measurable wins in the resident MLX
  engine without touching MLX C++ kernels.

## Candidate Performance Ports

1. Fused Metal sequence ideas from puma:
   RMS_NORM -> MUL -> ROPE and adjacent attention-prep operations.
2. Long-context KV memory and eviction policy from llama.cpp-family cache work.
3. Server-side queue and batching policy ideas from llama.cpp server.
4. Larger pp/tg benchmark discipline from llama-bench.

## Non-Goals

- Do not port ggml graph code into MLX.
- Do not prioritize GGUF quant support unless direct GGUF loading becomes a
  product requirement.
- Do not rework core MLX RoPE for Qwen3.6 unless runtime evidence contradicts
  the existing IMROPE parity results.
