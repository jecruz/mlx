# M260 Response-Quality Release Runner

Timestamp: `2026-05-27`

Branch: `prompt-processing-bench`

## Purpose

M260 removes the manual quality-artifact plumbing added by M259. Future
optimization branches can now run one command to capture candidate response
quality, compare against the accepted M258 baseline, and run the release gate.

## Implementation

Added:

- `benchmarks/python/run_response_quality_release_gate.py`
- `benchmarks/python/test_response_quality_release_runner.py`

The runner performs:

1. candidate quality capture from the live endpoint, unless `--candidate-json`
   is supplied
2. candidate-vs-baseline response-quality comparison
3. release gate execution with `--response-quality-comparison-json`
4. manifest JSON and Markdown output

## Validation

Unit tests:

```bash
python3 -m unittest \
  benchmarks/python/test_response_quality_release_runner.py \
  benchmarks/python/test_release_quality_performance_gate.py \
  benchmarks/python/test_response_quality_regression_harness.py
```

Result:

- `11` tests passed

Compile check:

```bash
python3 -m py_compile \
  benchmarks/python/run_response_quality_release_gate.py \
  benchmarks/python/test_response_quality_release_runner.py \
  benchmarks/python/release_quality_performance_gate.py \
  benchmarks/python/response_quality_regression_harness.py
```

Result:

- `PASS`

Runner command:

```bash
python3 benchmarks/python/run_response_quality_release_gate.py \
  --candidate-json artifacts/m259-release-gate-response-quality/current-candidate-quality-capture-m259-qwen-a3b.json \
  --output-dir artifacts/m260-response-quality-release-runner \
  --tag m260-response-quality-release-runner \
  --fail-on-fail
```

Result:

- verdict: `PASS`
- readiness: `response-quality-release-ready`
- candidate-vs-baseline comparison: `PASS`
- release gate: `PASS`
- release gate count: `16`
- failures: `0`

## Artifacts

- `artifacts/m260-response-quality-release-runner/response-quality-release-runner-m260-response-quality-release-runner.json`
- `artifacts/m260-response-quality-release-runner/response-quality-release-runner-m260-response-quality-release-runner.md`
- `artifacts/m260-response-quality-release-runner/candidate-vs-baseline-m260-response-quality-release-runner.json`
- `artifacts/m260-response-quality-release-runner/quality-preserving-release-gate-m260-response-quality-release-runner.json`

## Conclusion

M260 is complete. Candidate quality comparison and release-gate evidence are now
one-command reproducible.
