# M258 Live Response Quality Baseline

Timestamp: `2026-05-27`

Branch: `prompt-processing-bench`

## Purpose

M258 turns the M257 response-quality harness into a real live baseline. This
baseline is the accepted-engine anchor future performance branches should
compare against before promotion.

## Runtime

- server session: `codex-mlx-server`
- endpoint: `http://127.0.0.1:8773`
- model:
  `/Volumes/StudioStackSSD4TB/Development/LLM/lmstudio/models/unsloth/Qwen3.6-35B-A3B-UD-MLX-4bit`
- backend: `text`
- device: `Device(gpu, 0)`
- engine preset: `memory-saver`
- warmup: complete
- model load: `10039.872 ms`
- startup total: `19279.315 ms`

The model loaded with `load_strict=false` because extra vision-tower weights
were ignored. The server reported this as:

- `extra_vision_tower_weights_ignored`

## Baseline Capture

Command:

```bash
python3 benchmarks/python/response_quality_regression_harness.py capture \
  --base-url http://127.0.0.1:8773 \
  --model local-mlx \
  --runtime-profile interactive \
  --temperature 0.0 \
  --top-p 1.0 \
  --seed 258 \
  --output-json artifacts/m258-live-response-quality-baseline/live-baseline-m258-qwen-a3b.json \
  --output-md artifacts/m258-live-response-quality-baseline/live-baseline-m258-qwen-a3b.md \
  --tag m258-live-response-quality-baseline-qwen-a3b \
  --fail-on-fail
```

Result:

- verdict: `PASS`
- cases: `13`
- passed cases: `13`
- quality points: `130/130`
- failures: `0`
- max repetition score: `0.0`
- mean service request: `370.487 ms`

## Baseline Self-Comparison

Command:

```bash
python3 benchmarks/python/response_quality_regression_harness.py compare \
  --baseline-json artifacts/m258-live-response-quality-baseline/live-baseline-m258-qwen-a3b.json \
  --candidate-json artifacts/m258-live-response-quality-baseline/live-baseline-m258-qwen-a3b.json \
  --output-json artifacts/m258-live-response-quality-baseline/live-baseline-self-comparison-m258-qwen-a3b.json \
  --output-md artifacts/m258-live-response-quality-baseline/live-baseline-self-comparison-m258-qwen-a3b.md \
  --tag m258-live-baseline-self-comparison-qwen-a3b \
  --fail-on-fail
```

Result:

- verdict: `PASS`
- failures: `0`
- baseline quality points: `130/130`
- candidate quality points: `130/130`

## Artifacts

- `artifacts/m258-live-response-quality-baseline/live-baseline-m258-qwen-a3b.json`
- `artifacts/m258-live-response-quality-baseline/live-baseline-m258-qwen-a3b.md`
- `artifacts/m258-live-response-quality-baseline/live-baseline-self-comparison-m258-qwen-a3b.json`
- `artifacts/m258-live-response-quality-baseline/live-baseline-self-comparison-m258-qwen-a3b.md`
- `artifacts/m258-live-response-quality-baseline/server-m258.log`

## Promotion Rule

Future optimization branches should produce a candidate capture using the same
model, prompts, deterministic settings, and runtime profile. Promotion should
then require:

```bash
python3 benchmarks/python/response_quality_regression_harness.py compare \
  --baseline-json artifacts/m258-live-response-quality-baseline/live-baseline-m258-qwen-a3b.json \
  --candidate-json <candidate-quality-capture.json> \
  --output-json <candidate-quality-comparison.json> \
  --output-md <candidate-quality-comparison.md> \
  --fail-on-fail
```

M258 is complete: the engine now has a live response-quality baseline that
blocks future speed work from silently degrading answer quality.
