# M261 Live Response-Quality Release Runner

Timestamp: `2026-05-27`

Branch: `prompt-processing-bench`

## Purpose

M261 validates the M260 runner in true live-capture mode. This proves the
one-command release path can capture current candidate response quality from the
resident MLX server, compare it against the accepted M258 baseline, and run the
release gate without manually supplying a candidate artifact.

## Runtime

- server session: `codex-mlx-server`
- endpoint: `http://127.0.0.1:8773`
- model:
  `/Volumes/StudioStackSSD4TB/Development/LLM/lmstudio/models/unsloth/Qwen3.6-35B-A3B-UD-MLX-4bit`
- backend: `text`
- device: `Device(gpu, 0)`
- engine preset: `memory-saver`
- warmup: complete
- model load: `6751.056 ms`
- startup total: `13705.191 ms`

The model loaded with `load_strict=false` because extra vision-tower weights
were ignored:

- `extra_vision_tower_weights_ignored`

## Command

```bash
python3 benchmarks/python/run_response_quality_release_gate.py \
  --base-url http://127.0.0.1:8773 \
  --output-dir artifacts/m261-live-response-quality-release-runner \
  --tag m261-live-response-quality-release-runner \
  --fail-on-fail
```

## Result

- runner verdict: `PASS`
- readiness: `response-quality-release-ready`
- candidate source: `live-capture`
- candidate cases: `13`
- candidate passed cases: `13`
- candidate quality points: `130/130`
- candidate max repetition score: `0.0`
- candidate mean service request: `346.028 ms`
- candidate-vs-baseline comparison: `PASS`
- release gate: `PASS`
- release gate count: `16`
- failures: `0`

## Artifacts

- `artifacts/m261-live-response-quality-release-runner/candidate-quality-capture-m261-live-response-quality-release-runner.json`
- `artifacts/m261-live-response-quality-release-runner/candidate-vs-baseline-m261-live-response-quality-release-runner.json`
- `artifacts/m261-live-response-quality-release-runner/quality-preserving-release-gate-m261-live-response-quality-release-runner.json`
- `artifacts/m261-live-response-quality-release-runner/response-quality-release-runner-m261-live-response-quality-release-runner.json`
- `artifacts/m261-live-response-quality-release-runner/server-m261.log`

## Conclusion

M261 is complete. The response-quality release path is now proven in live
capture mode and can be used as the default promotion gate for future
optimization branches.
