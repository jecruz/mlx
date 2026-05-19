# M150 Performance Checkpoint

Model:

- `/Volumes/StudioStackSSD4TB/Development/LLM/lmstudio/models/unsloth/Qwen3.6-35B-A3B-UD-MLX-4bit`

Verdict:

- `PASS`

Covered milestones:

- `M143` streaming request-profile scope parity
- `M144` streaming metadata regression gate
- `M145` first reusable-turn latency reduction probe
- `M146` cache-admission threshold tuning
- `M147` Dax product-mode smoke commands
- `M148` live suite product-mode coverage
- `M149` request-scoped concurrency safety probe
- `M150` performance checkpoint

Evidence:

- `artifacts/m144-streaming-metadata-scope/streaming-request-metadata-scope-m144-qwen-a3b.json`
- `artifacts/m145-m146-cache-turn-gates/cache-threshold-and-turn-gates-m145-m146-qwen-a3b.json`
- `artifacts/m146-cache-threshold-tuning/request-scoped-cache-admission-m146-qwen-a3b.json`
- `artifacts/m148-dax-product-mode-smoke/dax-product-mode-smoke-m148-qwen-a3b.json`
- `artifacts/m148-live-product-mode-suite/live-product-regression-suite-m148-qwen-a3b.json`
- `artifacts/m149-request-scoped-concurrency/request-scoped-concurrency-m149-qwen-a3b.json`

Expanded live suite:

- verdict: `PASS`
- readiness: `live-regression-passing`
- artifacts: `15`
- failures: `0`

Decision:

- Continue into concurrency hardening and first reusable-turn latency reduction.
- Do not claim complete request-scoped runtime isolation yet. A first M149 run
  previously observed profile bleed before the passing rerun, so the next lane
  should convert that observation into a stronger repeated stress gate and lock
  discipline.
