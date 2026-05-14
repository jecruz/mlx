# Pi MiniMax MLX Project Research

Date: 2026-05-12

Command shape:

```bash
pi -p "$(cat /private/tmp/gemini_mlx_short_research_prompt.md)" \
  --no-session \
  --mode text
```

Runtime notes:

- Ran Pi with its default model, tools, extensions, and skills.
- Pi selected/used `MiniMax-M2.7-highspeed`.
- Search-capable/default extensions were available.
- The interaction completed in `83.5s`, `3480` tokens, `41.7 TPS`.

## Implementation Takeaways

Treat this output as a strong idea source, but verify repository URLs and claims
before using them as implementation evidence. Some entries are likely aliases,
forks, or search-derived summaries that need confirmation against real GitHub
repos.

Most useful ideas for the resident MLX engine:

- implement block/prefix KV cache instrumentation before full KV reuse
- study `mlx-lm` `cache_history` and `BatchGenerator` behavior
- study `mlx-vlm` vision feature caching and VLM processor/runtime paths
- study LM Studio `mlx-engine` VisionAddOn-style split between text model and
  vision add-on
- study `vllm-mlx` / `oMLX` style continuous batching, paged KV, and SSD tiering
- investigate a persistent Metal/GPU worker thread with a job queue
- consider OpenAI + Anthropic API compatibility as a product-level requirement
- defer DFlash/speculative decoding until cache and scheduler foundations are
  stable

## Raw Output

```text
## Top 10 MLX Repos for Building a Resident Inference Engine

---

## 1. `ml-explore/mlx-lm`
**URL:** https://github.com/ml-explore/mlx-lm
**Stars:** ~3,800 | **Lang:** Python (C++ core)

### Why it matters
The canonical MLX LLM library. `BatchGenerator` with `cache_history` for persistent KV across requests, LoRA/QLoRA fine-tuning, speculative decoding via `--draft-model`, and INT8 KV quantization. Every other server project either wraps or builds on this.

### Implementation idea to adapt
Port the `cache_history`-based prompt caching pattern to a resident server: prefill system prompt + conversation history once, then reuse cached KV states for all subsequent turns. On M3 Ultra this drops multi-turn TTFT from ~10s to ~0.1s.

### Caveat
Single-model, single-user design. No request queuing, no scheduler, no multi-model pool. Must build batching and concurrency on top.

---

## 2. `Blaizzy/mlx-vlm`
**URL:** https://github.com/Blaizzy/mlx-vlm
**Stars:** ~1,200 | **Lang:** Python

### Why it matters
The most complete VLM implementation in the MLX ecosystem. Supports Qwen-VL, Gemma 3/4, Pixtral, Idefics3, LLaVA, and video understanding. Ships a FastAPI server (`mlx_vlm.server`) with continuous batching, TurboQuant KV cache, vision feature caching (LRU, 8-entry), logprobs API, and OpenAI-compatible endpoints.

### Implementation idea to adapt
Steal the `VisionFeatureCache` LRU design for multi-turn VLM conversations — vision encoder runs once per unique image, subsequent turns reuse cached projections. Benchmarks show 11x+ speedup on repeated turns.

### Caveat
Vision tower is architecture-specific. Adding a new VLM family requires a new `apply_chat_template` path and `ModelWrapper` integration — not plug-and-play.

---

## 3. `lmstudio-ai/mlx-engine`
**URL:** https://github.com/lmstudio-ai/mlx-engine
**Stars:** ~982 | **Lang:** Python

### Why it matters
LM Studio's production MLX engine. Unified architecture: always loads the `mlx-lm` text model, then conditionally loads a `VisionAddOn` (Gemma3VisionAddOn, PixtralVisionAddOn) for image embeddings. This solves the forked-text-model problem and enables prompt caching on VLMs for the first time. Also integrates Outlines for structured JSON output.

### Implementation idea to adapt
Adopt the `VisionAddOn` pattern — separate text model loading from vision projection — to build a resident engine that handles text-only and VLM requests through the same serving path without duplicating text model logic.

### Caveat
No continuous batching or multi-model pool. Built as a Python module for LM Studio's Electron app — not a standalone server out of the box.

---

## 4. `waybarrios/vllm-mlx` + `swaylenhayes/vllm-mlx`
**URL:** https://github.com/waybarrios/vllm-mlx | fork: https://github.com/swaylenhayes/vllm-mlx
**Stars:** ~500+ | **Lang:** Python

### Why it matters
vLLM-inspired architecture for MLX: PagedAttention-style block KV cache, continuous batching, prefix caching, speculative decoding, and OpenAI + Anthropic API compatibility. The swaylenhayes fork adds +50% throughput vs upstream and evidence-backed validation against Goose, Open WebUI, and Claude Code.

### Implementation idea to adapt
Borrow the `BatchGenerator`-with-prefix-caching architecture: hash-based block KV cache with BLAKE2b identity, collision detection, min-heap LRU eviction, and optional SSD persistence tier. This is the production-grade serving skeleton.

### Caveat
Python-only, no GIL-free Metal thread, no multi-model pool. Designed for single-user local use — not hardened for adversarial multi-tenant workloads.

---

## 5. `SharpAI/SwiftLM`
**URL:** https://github.com/SharpAI/SwiftLM
**Stars:** ~632 | **Lang:** Swift/C++/Zig

### Why it matters
Fastest native-Metal MLX server. No Python, no GIL. Two flagship features: (a) **SSD Expert Streaming** — streams MoE expert weights directly from NVMe at QD=24, achieving 10x speedup on 122B+ models (0.58 → 5.91 tok/s); (b) **TurboQuant** — hybrid V2+V3 KV cache quantization (3-bit Lloyd-Max codebooks + QJL in fused Metal shaders) for 3.5x memory reduction with near-zero quality loss. Also has speculative decoding and a companion iOS app.

### Implementation idea to adapt
Steal the `SwitchGLU` cross-projection batching and speculative `pread` pipeline for MoE models — the pattern of batching expert I/O and overlapping SSD reads with GPU compute is transferable to any large-model resident engine.

### Caveat
Custom MLX forks required for SSD streaming (`SharpAI/mlx`, `SharpAI/mlx-c`). These forks lag behind `ml-explore/mlx` upstream. Each macOS update risks breaking the custom Metal kernels.

---

## 6. `jundot/omlx`
**URL:** https://github.com/jundot/omlx
**Stars:** ~10,000 | **Lang:** Python

### Why it matters
The most feature-complete open-source MLX inference server. Continuous batching, SSD tiered KV cache (RAM hot + SSD cold with safetensors persistence), hash-based prefix caching, DFlash speculative decoding (block-diffusion, 16 tokens/cycle), OpenAI-compatible API, and a macOS menu bar GUI. Well-documented with experimental feature flags for DFlash, KV quantization, and VLM routing.

### Implementation idea to adapt
Use the three-tier cache architecture (trie-based sequence cache → hash-block cache → SSD tier) as the foundation for a resident engine's memory management — it's production-tested and handles graceful fallback when RAM is exhausted.

### Caveat
DFlashEngine is single-request (no batching), and DFlash draft checkpoints only exist for Qwen3.5 family. SSD caching adds latency on small models. v0.4.0 is actively in development with engine parity changes.

---

## 7. `0xDaizz/mlx-lm-server`
**URL:** https://github.com/0xDaizz/mlx-lm-server
**Lang:** Python

### Why it matters
Clean fork of `mlx-lm` that adds a separable serving layer (`mlx_lm_server/`) with continuous batching, hash-based automatic prefix caching, multi-level KV cache (block → sequence → SSD), INT8 KV quantization, and FastAPI OpenAI API. 363 tests across 18 test files including adversarial, regression, and real-model E2E tests.

### Implementation idea to adapt
Use the `KVCacheManager` (hash-table block pool, BLAKE2b identity, min-heap LRU) as the caching backbone — it's the cleanest, best-tested block KV implementation in the MLX ecosystem.

### Caveat
Fork of a moving target (`mlx-lm` upstream). Maintenance burden to keep sync. No multi-model pool, no VLM support, no speculative decoding.

---

## 8. `ddalcu/mlx-serve`
**URL:** https://github.com/ddalcu/mlx-serve
**Stars:** ~22 | **Lang:** C++/Zig/Swift

### Why it matters
Native Zig server for MLX — no Python at all. JIT-compiles activations (GELU, GeGLU, softcap) via `mlx_compile`, uses fully-lazy async pipeline with reordered eval (submit-first pattern), and ships `MLX Core` macOS menu bar app. Supports Gemma 4, Qwen3/3.5/3.6, Nemotron-H, LFM2, Llama, Mistral with OpenAI + Anthropic API compatibility.

### Implementation idea to adapt
Adopt the "submit-first, eval reordered" pattern for the Metal pipeline — submit all layer work before blocking on `mx.eval()`, letting Metal overlap independent layer computations.

### Caveat
Small community (2 contributors), active development but gaps in model coverage (no MoE streaming, no VLM). Zig toolchain dependency adds build complexity.

---

## 9. `tumma72/mlx-manager`
**URL:** https://github.com/tumma72/mlx-manager
**Stars:** ~6 | **Lang:** Python/TypeScript/Svelte

### Why it matters
Web UI + embedded inference server. Two-phase model lifecycle (probe at load → discover capabilities, then serve with zero hot-path checks), multi-model pool with LRU eviction, persistent Metal GPU thread with job queue for thread affinity, list-buffer string assembly for O(1) streaming, and cloud routing fallback to OpenAI/Anthropic APIs.

### Implementation idea to adapt
Use the two-phase probe-then-serve pattern: at model load time, detect tool-calling format, thinking delimiters, and streaming support once; then in the hot path, run with zero capability checks.

### Caveat
Svelte 5 web UI adds frontend complexity. Multi-model pool is capped at 4 models. Cloud routing requires API keys — privacy tradeoff.

---

## 10. `LibraxisAI/mlx-batch-server`
**URL:** https://github.com/LibraxisAI/mlx-batch-server
**Lang:** Python

### Why it matters
Fork of `mlx-omni-server` with explicit batch coordinator (10+ concurrent requests), full OpenAI Responses API (`/v1/responses` with SSE streaming), Harmony parser for GPT-OSS channel parsing, and dual OpenAI + Anthropic SDK compatibility. Good reference for Responses API implementation.

### Implementation idea to adapt
Use the batch coordinator pattern: collect requests in a time window (configurable `MLX_BATCH_BATCH_WINDOW_MS`), then process them together in `BatchGenerator`. On M3 Ultra, 10 requests at once = ~350 tok/s total vs ~50 tok/s single.

### Caveat
Very new (created Jan 2026), 0 stars, small contributor base. No VLM, no SSD caching, no speculative decoding.

---

## 5 Concrete Next Engineering Tasks

### Task 1: Block KV Cache with Hash-Based Prefix Sharing
Implement `KVCacheManager` from `mlx-lm-server` with BLAKE2b-hashed blocks, min-heap LRU eviction, and optional SSD persistence. This is the single highest-leverage improvement — it enables multi-turn TTFT speedups of 10-30x and reduces redundant prefill across concurrent users.

**Key files to reference:** `mlx_lm_server/kv_cache_manager.py`, `mlx_lm_server/sequence_cache.py`, `mlx_lm_server/ssd_cache.py`

---

### Task 2: Persistent Metal GPU Thread with Job Queue
Adopt the `mlx-manager` pattern: dedicate one thread to Metal with an `asyncio` job queue, ensuring thread affinity across all requests. This eliminates GIL contention and Python overhead from the hot inference path. Start with `mlx_lm.generate` wrapped in a thread-executor, then move to direct `mx.eval` once stable.

---

### Task 3: Vision Feature Cache + VLM AddOn Architecture
Implement `VisionFeatureCache` from `mlx-vlm` (LRU, keyed by image path) for multi-turn VLM conversations. Simultaneously adopt the `VisionAddOn` pattern from `mlx-engine`: always load text model from `mlx-lm`, load vision projection conditionally. This unifies text and VLM serving paths and enables prompt caching on VLMs.

---

### Task 4: TurboQuant KV Cache Integration
Port the TurboQuant KV cache from `mlx-vlm` (`--kv-bits 3.5 --kv-quant-scheme turboquant`) and `SwiftLM` (hybrid V2+V3 Lloyd-Max codebooks in fused Metal). At 3.5-bit TurboQuant, KV memory reduces 76% on Qwen3.5-4B at 128K context — this is what enables truly long-context resident inference on 32-64GB machines.

---

### Task 5: Speculative Decoding with DFlash
Integrate DFlash from `omlx` (`jundot/dflash-mlx` fork) for short-context (<4K tokens) requests. DFlash proposes 16 tokens via block-diffusion draft in a single forward pass; the target model verifies all 16 in parallel. On Qwen3.5-4B this yields 2-3x throughput. Implement the fallback path: detect `len(prompt_tokens) >= DFLASH_MAX_CTX`, route to BatchedEngine for long contexts.

---

**Build priority:** Tasks 1 → 2 → 3 → 4 → 5. Tasks 1 and 2 give you a production-grade resident server. Task 3 adds VLM. Tasks 4 and 5 are performance multipliers that depend on a stable base.
```
