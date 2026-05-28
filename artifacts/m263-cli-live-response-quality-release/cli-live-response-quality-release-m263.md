# M263 CLI Live Response-Quality Release

Timestamp: `2026-05-27`

Branch: `prompt-processing-bench`

## Purpose

M263 validates the final operator-facing response-quality release command in
live-capture mode:

```bash
bin/mlx-engine response-quality-release
```

Unlike M262, this run does not supply `--candidate-json`. The command captures
candidate response quality from the live resident MLX server, compares it
against the M258 baseline, and runs the release gate.

## Runtime

- server session: `codex-mlx-server`
- endpoint: `http://127.0.0.1:8773`
- model:
  `/Volumes/StudioStackSSD4TB/Development/LLM/lmstudio/models/unsloth/Qwen3.6-35B-A3B-UD-MLX-4bit`
- backend: `text`
- device: `Device(gpu, 0)`
- engine preset: `memory-saver`
- warmup: complete
- model load: `6230.795 ms`
- startup total: `12720.985 ms`

The model loaded with `load_strict=false` because extra vision-tower weights
were ignored:

- `extra_vision_tower_weights_ignored`

## Command

```bash
bin/mlx-engine response-quality-release \
  --base-url http://127.0.0.1:8773 \
  --output-dir artifacts/m263-cli-live-response-quality-release \
  --tag m263-cli-live-response-quality-release \
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
- candidate mean service request: `342.235 ms`
- candidate-vs-baseline comparison: `PASS`
- release gate: `PASS`
- release gate count: `16`
- failures: `0`

## Artifacts

- `artifacts/m263-cli-live-response-quality-release/candidate-quality-capture-m263-cli-live-response-quality-release.json`
- `artifacts/m263-cli-live-response-quality-release/candidate-vs-baseline-m263-cli-live-response-quality-release.json`
- `artifacts/m263-cli-live-response-quality-release/quality-preserving-release-gate-m263-cli-live-response-quality-release.json`
- `artifacts/m263-cli-live-response-quality-release/response-quality-release-runner-m263-cli-live-response-quality-release.json`
- `artifacts/m263-cli-live-response-quality-release/server-m263.log`

## Conclusion

M263 is complete. The stable `bin/mlx-engine response-quality-release` command
is proven end-to-end against a live resident MLX server without manually
supplying a candidate artifact.
