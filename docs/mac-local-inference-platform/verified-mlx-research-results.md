# Verified MLX Research Results

Date: 2026-05-12

This note reconciles the web research, Pi/MiniMax output, and direct source
verification. Treat it as the decision input for the next MLX engine milestone.

## Verified High-Value Repos

### `ml-explore/mlx`

URL: https://github.com/ml-explore/mlx

Use as the ground truth for MLX runtime behavior.

Verified relevance:

- official MLX array framework
- Python, C++, C, and Swift APIs
- lazy computation and dynamic graph execution
- Metal-backed Apple Silicon target

Engine implication:

- stay close to upstream APIs; avoid depending on custom forks until we have a
  measured reason
- native Swift/C++ paths are real, but the Python prototype remains the fastest
  path to product learning

### `ml-explore/mlx-lm`

URL: https://github.com/ml-explore/mlx-lm

Use as the canonical text-generation stack.

Verified relevance:

- official package for generating and fine-tuning LLMs on Apple Silicon
- includes HTTP model server with OpenAI-like chat endpoint
- supports draft model parameter for speculative decoding in the server API
- upstream server documentation says it is not recommended for production and
  only implements basic security checks

Engine implication:

- our resident service should continue wrapping `mlx-lm`
- do not copy `mlx_lm.server` as a production server
- prioritize memory limits, KV lifecycle, and error handling because upstream
  server issues show long-context/Metal OOM risks

### `Blaizzy/mlx-vlm`

URL: https://github.com/Blaizzy/mlx-vlm

Use as the VLM and multimodal correctness reference.

Verified relevance:

- supports VLM and omni models on MLX
- ships FastAPI server
- includes continuous batching
- includes Automatic Prefix Caching
- includes KV cache quantization and TurboQuant
- includes `VisionFeatureCache` for repeated image turns

Engine implication:

- next VLM milestone should move from static processor checks to runtime image
  feature checks
- implement or adapt a `VisionFeatureCache` abstraction before adding broad VLM
  support
- study APC/TurboQuant as later memory optimizations after baseline lifecycle is
  stable

### `lmstudio-ai/mlx-engine`

URL: https://github.com/lmstudio-ai/mlx-engine

Use as the production-adjacent MLX integration reference.

Verified relevance:

- used by LM Studio on Mac
- built with `mlx-lm`, `mlx-vlm`, and Outlines
- supports vision model demo and speculative decoding demo
- LM Studio documents a unified architecture where `mlx-lm` text models are
  always used and `mlx-vlm` vision add-ons provide image embeddings

Engine implication:

- adopt the separation of text model residency from optional vision add-ons
- avoid duplicating model-family text logic in a separate VLM path
- evaluate Outlines/structured output only after chat/completion and cache
  foundations are stable

### `waybarrios/vllm-mlx`

URL: https://github.com/waybarrios/vllm-mlx

Use as a serving architecture reference.

Verified relevance:

- OpenAI and Anthropic compatible server for Apple Silicon
- continuous batching
- paged KV cache
- prefix caching
- SSD-tiered cache
- MCP/tool-calling support
- multimodal, audio, embeddings

Engine implication:

- do not jump directly to full continuous batching
- first measure repeated-prefix opportunities in our resident service
- then implement prefix-cache instrumentation and only later block KV reuse

### `jundot/omlx`

URL: https://github.com/jundot/omlx

Use as the closest product/architecture reference for coding-agent local MLX.

Verified relevance:

- MLX inference server with continuous batching and tiered KV caching
- macOS menu bar app
- OpenAI and Anthropic API compatibility
- multi-model serving with LRU eviction, manual load/unload, pinning, TTL
- admin panel, model downloader, benchmark tooling
- explicit Codex/Pi/OpenClaw integration story
- Apache 2.0 license

Engine implication:

- our roadmap should not ignore oMLX; it already implements several planned
  features
- decide whether to extend/rebrand oMLX, fork targeted ideas, or keep our MLX
  work as a smaller engine kernel
- product differentiation should be around Pi/ComfyUI workflow integration,
  correctness validation, and Mac ecosystem polish

### `SharpAI/SwiftLM`

URL: https://github.com/SharpAI/SwiftLM

Use as the native Swift/high-performance moonshot reference.

Verified relevance:

- native Swift MLX inference server
- OpenAI-compatible API
- VLM and ALM support
- TurboQuant KV cache compression
- SSD expert streaming for large MoE models
- relies on custom `SharpAI/mlx` and `SharpAI/mlx-c` forks for SSD streaming

Engine implication:

- native Swift is a credible long-term path
- do not migrate the prototype wholesale yet
- use SwiftLM to guide a packaging/native-spike milestone, not the immediate
  cache instrumentation work

### `ddalcu/mlx-serve`

URL: https://github.com/ddalcu/mlx-serve

Use as a no-Python/native packaging reference.

Verified relevance:

- Zig server using MLX-C bindings
- OpenAI-compatible API
- menu bar app
- tool calling, embeddings, logprobs
- claims KV cache reuse across requests

Engine implication:

- useful for studying native server/API packaging and menu bar ergonomics
- not the next implementation dependency

### `ml-explore/mlx-swift` and `ml-explore/mlx-swift-lm`

URLs:

- https://github.com/ml-explore/mlx-swift
- https://github.com/ml-explore/mlx-swift-lm

Use as official native app integration references.

Verified relevance:

- official Swift API for MLX
- Swift package for LLMs and VLMs
- model loading, LoRA/full fine-tuning, quantized models
- LLM and VLM implementations for Swift apps

Engine implication:

- use these for a contained app-helper/native packaging spike
- keep current engine prototype Python until cache/scheduler assumptions are
  validated

### `argmaxinc/DiffusionKit`

URL: https://github.com/argmaxinc/DiffusionKit

Use as an MLX/CoreML image-generation reference, not as the immediate ComfyUI
path.

Verified relevance:

- Python package for MLX image generation
- Swift package direction for on-device diffusion
- supports Stable Diffusion 3 and FLUX-style workflows through model conversion
  and local inference

Engine implication:

- ComfyUI remains the practical image backend now
- DiffusionKit belongs in the later native image-generation engine comparison

## Unverified Or Suspect Entries From Agent Output

These may still exist, but the exact claims/URLs from agent output should not be
used without direct verification:

- `mlc-ai/mlx-llm`
- `macannon/mlx-lm-server`
- `multimodal-latency/oml`
- `p Luigi` / `ppmlx` URL from the agent output
- `dflash-ai/dflash-mlx`
- `0xDaizz/mlx-lm-server`
- `tumma72/mlx-manager`
- `LibraxisAI/mlx-batch-server`

Some of the ideas associated with those entries are still valid because the same
capabilities are verified in `mlx-vlm`, `oMLX`, `vllm-mlx`, and SwiftLM.

## Decision

The next milestone should not be full continuous batching. It should be prefix
and cache observability.

Rationale:

- Our current resident service is single-model and already passes basic smoke,
  streaming, reload, unload, and correctness gates.
- Coding-agent workloads repeat large system/tool/context prefixes.
- Prefix reuse metrics can be added safely before changing KV cache behavior.
- The verified external projects all converge on prefix caching, paged KV, and
  tiered cache as the real performance lever.

## Next Engineering Slice

### M6: Prefix Cache Instrumentation

Add to `benchmarks/python/resident_mlx_service.py`:

- canonical rendered prompt hash
- tokenized prompt hash
- per-request prefix signature
- longest common prefix token count versus recent requests
- estimated avoidable prefill tokens
- cache eligibility verdict
- request metrics fields:
  - `prompt_tokens`
  - `longest_prefix_match_tokens`
  - `prefix_reuse_ratio`
  - `estimated_recompute_tokens`
  - `cache_candidate`

Add to `benchmarks/python/smoke_resident_service.py`:

- two related chat requests with shared system/user prefix
- assertion that prefix metrics detect a shared prefix
- assertion that metrics endpoint exposes prefix opportunity counters

Add to docs:

- update `engine-plan.md`
- update `progress.md`

### M7: Runtime VLM Validation

After M6, validate real image prompt execution:

- load one Qwen3.6 VLM checkpoint
- encode one small local image
- verify image-token expansion
- verify multimodal position layout does not fail
- generate a short answer
- record timing and memory

### M8: Cache Implementation Decision

Only after measuring real prefix-reuse opportunities:

- compare simple `mlx-lm` cache reuse
- block-level prefix cache
- APC-like implementation
- oMLX/vllm-mlx inspired paged cache
- SSD tier

## Sources

- https://github.com/ml-explore/mlx
- https://github.com/ml-explore/mlx-lm
- https://github.com/Blaizzy/mlx-vlm
- https://github.com/lmstudio-ai/mlx-engine
- https://lmstudio.ai/blog/unified-mlx-engine
- https://github.com/waybarrios/vllm-mlx
- https://github.com/jundot/omlx
- https://omlx.ai/
- https://github.com/SharpAI/SwiftLM
- https://ddalcu.github.io/mlx-serve/
- https://github.com/ml-explore/mlx-swift
- https://github.com/ml-explore/mlx-swift-lm
- https://github.com/argmaxinc/DiffusionKit
