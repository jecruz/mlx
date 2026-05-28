# M262 CLI Response-Quality Release Command

Timestamp: `2026-05-27`

Branch: `prompt-processing-bench`

## Purpose

M262 promotes the response-quality release runner from a benchmark script to a
stable operator command:

```bash
bin/mlx-engine response-quality-release
```

This gives automation and human operators one consistent entrypoint for
candidate quality capture, baseline comparison, and release-gate validation.

## Implementation

Added `response-quality-release` to `bin/mlx-engine`.

Default behavior:

- base URL: `http://127.0.0.1:8773`
- baseline:
  `artifacts/m258-live-response-quality-baseline/live-baseline-m258-qwen-a3b.json`
- output directory: `artifacts/response-quality-release`
- model: `local-mlx`
- runtime profile: `interactive`
- deterministic settings: `temperature=0.0`, `top_p=1.0`, `seed=260`

The command also accepts `--candidate-json` for CI/offline reuse of an existing
candidate capture.

## Validation

Unit tests:

```bash
python3 -m unittest \
  benchmarks/python/test_mlx_engine_cli.py \
  benchmarks/python/test_response_quality_release_runner.py \
  benchmarks/python/test_release_quality_performance_gate.py \
  benchmarks/python/test_response_quality_regression_harness.py
```

Result:

- `13` tests passed

Compile check:

```bash
python3 -m py_compile \
  bin/mlx-engine \
  benchmarks/python/test_mlx_engine_cli.py \
  benchmarks/python/run_response_quality_release_gate.py \
  benchmarks/python/test_response_quality_release_runner.py
```

Result:

- `PASS`

CLI command:

```bash
bin/mlx-engine response-quality-release \
  --candidate-json artifacts/m259-release-gate-response-quality/current-candidate-quality-capture-m259-qwen-a3b.json \
  --output-dir artifacts/m262-cli-response-quality-release \
  --tag m262-cli-response-quality-release \
  --fail-on-fail
```

Result:

- runner verdict: `PASS`
- readiness: `response-quality-release-ready`
- candidate source: `existing-artifact`
- candidate-vs-baseline comparison: `PASS`
- release gate: `PASS`
- release gate count: `16`
- failures: `0`

## Artifacts

- `artifacts/m262-cli-response-quality-release/response-quality-release-runner-m262-cli-response-quality-release.json`
- `artifacts/m262-cli-response-quality-release/candidate-vs-baseline-m262-cli-response-quality-release.json`
- `artifacts/m262-cli-response-quality-release/quality-preserving-release-gate-m262-cli-response-quality-release.json`

## Conclusion

M262 is complete. Automation can now use `bin/mlx-engine
response-quality-release` as the stable promotion-quality command.
