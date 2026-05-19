# M158 Performance Checkpoint

Verdict:

- `PASS`

Covered milestones:

- `M151` concurrency stress hardening
- `M152` request-profile scope lock audit
- `M153` streaming and non-stream route parity
- `M154` product-profile policy stabilization
- `M155` live suite lock regression
- `M156` performance report
- `M157` operator visibility contract
- `M158` checkpoint and next milestone list

Evidence:

- `artifacts/m151-concurrency-stress/request-scoped-concurrency-stress-m151-qwen-a3b.json`
- `artifacts/m152-runtime-profile-scope-audit/runtime-profile-scope-audit-m152-qwen-a3b.json`
- `artifacts/m153-route-parity/route-parity-m153-qwen-a3b.json`
- `artifacts/m154-product-profile-policy/product-profile-policy-m154-qwen-a3b.json`
- `artifacts/m155-live-suite-lock-regression/live-product-regression-suite-m155-qwen-a3b.json`
- `artifacts/m156-performance-report/performance-report-m156-qwen-a3b.md`
- `artifacts/m157-operator-visibility/operator-visibility-m157-qwen-a3b.json`

Performance summary:

- M155 live suite: `PASS`, 15 artifacts, 0 failures
- M151 stress: 12 iterations, 36 rows, 0 failures
- repeated best-hit speedup: `6.949899063306281`
- repeated best-hit service ms: `214.1152499243617`
- repeated best-hit prefill tokens: `11`
- resident prompt transport wall ms: `474.661166081205`
- CLI prompt transport wall ms: `6038.545124931261`

Next milestones:

- `M159` deeper concurrency stress under external observer load
- `M160` first reusable-turn latency tuning
- `M161` cache admission threshold sweep
- `M162` resident-vs-cli transport overhead reduction
- `M163` prompt-progress telemetry polish for operator UI
- `M164` Dax/TUI live metrics panel
- `M165` smaller-model prompt-processing baseline
- `M166` release candidate engine preset matrix
