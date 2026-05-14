# GitHub MLX Project Research

Date: 2026-05-12

## Context

Claude Code was requested for this research pass, but the launch was blocked by
the approval reviewer because the original prompt included local workspace
details that would have been sent to an external service. This note uses public
web research only.

Current local engine state:

- resident `mlx_lm` service prototype exists
- OpenAI-compatible completions and chat endpoints exist
- streaming, metrics, reload, unload, and correctness smoke commands exist
- prompt prefill profiling exists for `gpt-oss-20b-MXFP4-Q8`
- Qwen3.6 IMROPE static parity and VLM processor static checks exist

## Ranked Projects To Study

### 1. `waybarrios/vllm-mlx`

URL: https://github.com/waybarrios/vllm-mlx

Why it matters:

- closest public match to the target engine shape
- OpenAI and Anthropic APIs in one process
- continuous batching
- paged KV cache
- prefix cache
- SSD-tiered cache
- warm prompts
- MCP/tool-calling parser support
- multimodal, audio, embeddings, reasoning parsers
- Prometheus metrics and benchmark tooling

Ideas to adapt:

- request scheduler and continuous batching design
- memory-aware cache budgeting
- prefix cache data model
- Anthropic Messages API support for Claude Code compatibility
- benchmark CLI shape for reproducible prompt/decode sweeps
- warm prompt/profile interface

Caveats:

- verify claims with local benchmarks before copying design choices
- inspect cache correctness for hybrid architectures before adopting behavior

Priority: high

### 2. `jundot/omlx`

URL: https://github.com/jundot/omlx

Why it matters:

- MLX inference server explicitly focused on coding agents
- continuous batching and SSD caching
- macOS menu bar app
- app bundle packaging path using `venvstacks`
- evolved from `vllm-mlx`

Ideas to adapt:

- macOS app/helper packaging architecture
- admin panel and local engine management
- tiered KV cache policy
- coding-agent-focused prompt-cache strategy
- model residency and app-level lifecycle controls

Caveats:

- this overlaps with the rebrand/product discussion; avoid copying UI/product
  identity blindly
- inspect licensing and attribution before reuse

Priority: high

### 3. `lmstudio-ai/mlx-engine`

URL: https://github.com/lmstudio-ai/mlx-engine

Why it matters:

- production-adjacent MLX engine used by LM Studio
- built on `mlx-lm`, `mlx-vlm`, and Outlines
- supports text, vision, and speculative decoding demos
- has tests for vision models

Ideas to adapt:

- model-family loader separation
- vision-model test structure
- speculative decoding integration shape
- structured output integration with Outlines
- Python runtime constraints around Python 3.11 packaging

Caveats:

- LM Studio app behavior may include wrapper behavior outside the public repo
- use it as implementation reference, not as final architecture

Priority: high

### 4. `mlx-lm`

URL: https://github.com/ml-explore/mlx-lm

Why it matters:

- canonical MLX LLM implementation
- includes HTTP model server
- latest public release observed: `v0.31.3` on 2026-04-22
- supports generation, quantization, fine-tuning, and distributed paths

Ideas to adapt:

- stay aligned with upstream cache and sampler APIs
- inspect server implementation before expanding our API
- track prefix-cache and hybrid-cache upstream issues
- upstream-compatible sampler controls

Caveats:

- upstream server is documented as not production-oriented
- prefix-cache behavior for hybrid architectures needs careful validation

Priority: high

### 5. `mlx-vlm`

URL: https://github.com/Blaizzy/mlx-vlm

Why it matters:

- practical MLX VLM path used by downstream engines
- relevant to Qwen3.6 VLM image prompt runtime validation
- model processors and image-token expansion are next correctness risks

Ideas to adapt:

- runtime VLM image tensor validation
- Qwen3-VL processor behavior
- multimodal chat message formatting
- model-family-specific visual token tests

Caveats:

- static config checks are not enough; runtime image layout tests are required

Priority: high

### 6. `ppmlx`

URL: https://ppmlx.dev/

Why it matters:

- product-level MLX-native local engine with OpenAI, Anthropic Messages, and
  Responses API support
- model picker, launchers for Claude Code/Codex/OpenCode/Pi
- hot-swap models without restarting
- LRU model cache and SQLite logging
- vision and embeddings in one server

Ideas to adapt:

- local developer-product ergonomics
- model registry aliases
- Pi launcher workflow
- LRU resident model cache
- request logging for reproducibility
- Responses API support

Caveats:

- research found project site details; inspect source repo before treating any
  implementation claim as verified

Priority: medium-high

### 7. `SharpAI/SwiftLM`

URL: https://github.com/SharpAI/SwiftLM

Why it matters:

- native Swift MLX inference server
- no Python runtime or GIL
- single-binary distribution with `mlx.metallib`
- OpenAI-compatible API
- claims SSD streaming for very large MoE models and KV compression

Ideas to adapt:

- long-term native Swift engine path
- single-binary packaging
- app-helper integration
- bundled Metal library distribution
- memory-copy minimization

Caveats:

- newer project; validate model coverage, correctness, and performance locally
- likely not a short-term replacement for the current Python prototype

Priority: medium-high

### 8. `bstnxbt/dflash-mlx`

URL: https://github.com/bstnxbt/dflash-mlx

Why it matters:

- speculative decoding on MLX with block-diffusion drafts
- custom Metal kernels for verify-specialized paths
- prefix snapshot cache with RAM and SSD tiers
- family-specific cache layout and parity tests

Ideas to adapt:

- add speculative decoding as a later milestone
- define model-family adapter contracts before optimizing kernels
- copy the principle of parity tests before enabling optimized decode paths
- add structured diagnostics artifacts

Caveats:

- advanced optimization, not the next immediate step
- requires architecture-specific correctness work

Priority: medium

### 9. `humanrouter/ddtree-mlx`

URL: https://github.com/humanrouter/ddtree-mlx

Why it matters:

- tree-based speculative decoding for MLX
- focuses on hybrid model constraints
- documents what did and did not work

Ideas to adapt:

- study negative findings before investing in speculative decoding
- add acceptance-density metrics if we test speculative paths
- avoid premature generalized tree verification without family-specific tests

Caveats:

- speculative decoding should wait until baseline serving/caching is stable

Priority: medium

### 10. `ml-explore/mlx-swift` and `ml-explore/mlx-swift-lm`

URLs:

- https://github.com/ml-explore/mlx-swift
- https://github.com/ml-explore/mlx-swift-lm

Why they matter:

- official Swift surface for MLX
- LLM and VLM implementations for Swift apps
- direct path to native macOS/iOS integration

Ideas to adapt:

- future native app-helper engine
- Swift concurrency around streaming
- model loading and generation examples
- compare Swift versus Python overhead for resident serving

Caveats:

- short-term Python prototype is moving faster
- native Swift path should be evaluated with a contained spike, not a rewrite

Priority: medium

## Other Projects Worth Tracking

### `mlx-openai-server`

URL: https://github.com/cubist38/mlx-openai-server

Relevant for:

- multi-model config
- OpenAI-compatible text, vision, image, embedding, and Whisper endpoints
- reasoning/tool-call parser ideas
- long-context and Metal OOM handling

Priority: medium

### `mlx-serve`

URL: https://github.com/raspoli/mlx-serve

Relevant for:

- hot-swapping one model at a time under unified-memory limits
- subprocess isolation
- multi-modal routing

Priority: medium

### `plllm-mlx`

URL: https://pypi.org/project/plllm-mlx/

Relevant for:

- process-isolated multi-model serving
- prefix caching
- incremental prefill optimization
- standalone operation without Redis/database

Priority: medium

### `argmaxinc/DiffusionKit`

URL: https://github.com/argmaxinc/DiffusionKit

Relevant for:

- long-term image-generation engine path
- Core ML plus MLX image generation
- Swift package direction for on-device diffusion

Priority: medium for image work, low for immediate text engine

### `mlx-community/speculative-decoding`

URL: https://github.com/mlx-community/speculative-decoding

Relevant for:

- simple MLX-Swift speculative decoding API
- draft/target pair benchmark structure

Priority: low-medium

## Concrete Next Implementation Plan

### M6: Cache And Scheduler Design Spike

Goal: decide whether our next engine milestone should be prefix caching,
continuous batching, or native packaging.

Tasks:

1. Inspect `vllm-mlx` scheduler, prefix cache, and benchmark implementation.
2. Inspect `oMLX` tiered cache and packaging implementation.
3. Inspect LM Studio `mlx-engine` vision tests and speculative decode demo.
4. Write a local design note comparing:
   - simple resident single-request server
   - prefix-cache server
   - continuous-batching server
   - process-isolated multi-model server
5. Choose one next vertical slice.

Recommended choice:

- implement prefix-cache instrumentation first, not continuous batching.

Reason:

- our current target is local agentic workflows with repeated system/tool
  prompts
- repeated-prefix reuse improves single-user coding-agent latency
- continuous batching is valuable later for multiple concurrent clients
- prefix-cache metrics will tell us whether more complex paged/SSD cache work is
  worth it

### M7: Prefix Cache Instrumentation

Add to `benchmarks/python/resident_mlx_service.py`:

- request prompt hash
- rendered chat-template hash
- longest common prefix token count versus recent requests
- measured prefill tokens
- estimated reusable prefix tokens
- cache eligibility verdict
- metrics fields for prefix reuse opportunities

This can be implemented before actual KV reuse. The first goal is to measure how
much reuse Pi/Codex/Claude-style traffic would have.

### M8: Runtime VLM Validation

Add a real image-prompt test for Qwen3.6 VLM checkpoints:

- load image
- apply processor
- verify image-token expansion
- verify position IDs / multimodal layout
- run short generation
- assert non-empty output and no processor mismatch

Relevant files:

- `benchmarks/python/vlm_processor_static_probe.py`
- `benchmarks/python/vlm_prompt_decode_bench.py`
- `docs/mac-local-inference-platform/qwen-imrope-parity.md`

### M9: Packaging Spike

Compare:

- Python app helper with launchd template
- `venvstacks` style app bundle
- native Swift wrapper calling Python service
- native Swift engine spike using `mlx-swift-lm`

Relevant current file:

- `packaging/launchd/com.jecruz.mlx-engine.plist.template`

## Immediate File Targets

Likely next local edits:

- `benchmarks/python/resident_mlx_service.py`
  - add prefix-reuse metrics and request prompt hashing
- `benchmarks/python/smoke_resident_service.py`
  - validate new metrics fields
- `docs/mac-local-inference-platform/engine-plan.md`
  - add M6/M7 cache direction
- `docs/mac-local-inference-platform/progress.md`
  - record this research pass

## Sources

- https://github.com/waybarrios/vllm-mlx
- https://github.com/jundot/omlx
- https://github.com/lmstudio-ai/mlx-engine
- https://github.com/ml-explore/mlx-lm
- https://github.com/ml-explore/mlx
- https://github.com/ml-explore/mlx-examples
- https://github.com/ml-explore/mlx-swift
- https://github.com/ml-explore/mlx-swift-lm
- https://ppmlx.dev/
- https://github.com/SharpAI/SwiftLM
- https://github.com/bstnxbt/dflash-mlx
- https://github.com/humanrouter/ddtree-mlx
- https://github.com/cubist38/mlx-openai-server
- https://github.com/raspoli/mlx-serve
- https://pypi.org/project/plllm-mlx/
- https://github.com/argmaxinc/DiffusionKit
- https://github.com/mlx-community/speculative-decoding
