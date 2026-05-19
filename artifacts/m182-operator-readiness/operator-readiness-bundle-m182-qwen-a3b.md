# M182 Operator Readiness Bundle

Verdict: `PASS`
Readiness: `operator-readiness-ready`

## Status Card

- runtime: `PASS`
- quality: `PASS`
- live_suite: `PASS`
- lower_memory: `PASS`
- memory_source: `PASS`
- live_model_swap: `PASS`
- candidate_swap: `WARN`

## Runtime

- model: `/Volumes/StudioStackSSD4TB/Development/LLM/lmstudio/models/unsloth/Qwen3.6-35B-A3B-UD-MLX-4bit`
- backend: `text`
- preset: `async-experimental`
- profile: `interactive`
- strategy: `split_prefill_or_async_build`
- can generate: `True`

## Model Decision

- active model: `/Volumes/StudioStackSSD4TB/Development/LLM/lmstudio/models/unsloth/Qwen3.6-35B-A3B-UD-MLX-4bit`
- candidate model: `/Volumes/StudioStackSSD4TB/Development/LLM/lmstudio/models/unsloth/Qwen3.6-27B-UD-MLX-4bit`
- swap decision: `REJECT`
- readiness: `swap-blocked`
- blockers: `1`

## Memory

- source: `request_metrics`
- max active GB: `21.02259841`
- max peak GB: `22.31961337`
- health fallback GB: `None`

## Evidence

- suite_json: `artifacts/m180-live-request-memory-suite/live-product-regression-suite-m180-qwen-a3b.json`
- operator_quality_json: `artifacts/m171-operator-quality-bundle/operator-quality-bundle-m171-qwen-a3b.json`
- model_swap_workflow_json: `artifacts/m179-model-swap-workflow/model-swap-workflow-m179-qwen27b.json`
- lower_memory_json: `artifacts/m180-live-request-memory-suite/lower-memory-live-gate-m180-qwen-a3b.json`
- live_model_swap_json: `artifacts/m181-live-model-swap/live-model-swap-m181-qwen-a3b.json`

## Warnings

- `model swap decision is REJECT`

## Failures

- none
