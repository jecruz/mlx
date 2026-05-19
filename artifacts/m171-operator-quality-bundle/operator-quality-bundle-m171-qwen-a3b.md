# M171 Operator Quality Bundle

Verdict: `PASS`

## Status

- engine: `PASS`
- gpu: `PASS`
- warmup: `PASS`
- quality: `PASS`
- model_comparison: `PASS`

## Active Runtime

- model: `/Volumes/StudioStackSSD4TB/Development/LLM/lmstudio/models/unsloth/Qwen3.6-35B-A3B-UD-MLX-4bit`
- profile: `interactive`
- preset: `async-experimental`
- cache strategy: `split_prefill_or_async_build`
- can generate: `True`

## Model Comparison

| Label | Active | Verdict | Mean Quality Gate ms | Failures |
| --- | --- | --- | ---: | ---: |
| `qwen35b-a3b-ud-4bit` | `True` | `PASS` | 338.812 | 0 |
| `qwen27b-ud-4bit` | `False` | `PASS` | 3377.609 | 0 |

## Warnings

- `quality-compatible alternate model is slower than active model: qwen27b-ud-4bit`

## Failures

- none
