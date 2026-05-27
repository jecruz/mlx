# M259 Release Gate Response-Quality Requirement

Timestamp: `2026-05-27`

Branch: `prompt-processing-bench`

## Purpose

M259 makes response quality release-blocking. The release gate now accepts an
explicit current candidate-vs-baseline response-quality comparison artifact.

## Implementation

Added release gate:

- key: `response_quality_regression_candidate`
- category: `response_quality`
- baseline artifact:
  `artifacts/m258-live-response-quality-baseline/live-baseline-m258-qwen-a3b.json`
- current candidate artifact:
  `artifacts/m259-release-gate-response-quality/current-candidate-quality-capture-m259-qwen-a3b.json`
- comparison artifact:
  `artifacts/m259-release-gate-response-quality/current-candidate-vs-baseline-m259-qwen-a3b.json`

The gate fails if:

- `--response-quality-comparison-json` is omitted from a release-gate run
- the comparison verdict is not `PASS`
- readiness is not `response-quality-regression-ready`
- baseline or candidate case count is not `13`
- baseline or candidate pass count is not `13`
- baseline or candidate quality points are not full
- baseline or candidate max repetition score is not `0.0`
- the comparison reuses the baseline artifact as the candidate artifact
- the comparison artifact reports failures

## Validation

Unit tests:

```bash
python3 -m unittest \
  benchmarks/python/test_release_quality_performance_gate.py \
  benchmarks/python/test_response_quality_regression_harness.py
```

Result:

- `7` tests passed
- omitted response-quality argument path fails by design

Compile check:

```bash
python3 -m py_compile \
  benchmarks/python/release_quality_performance_gate.py \
  benchmarks/python/test_release_quality_performance_gate.py \
  benchmarks/python/response_quality_regression_harness.py \
  benchmarks/python/test_response_quality_regression_harness.py
```

Result:

- `PASS`

Release gate:

```bash
python3 benchmarks/python/release_quality_performance_gate.py \
  --response-quality-comparison-json artifacts/m259-release-gate-response-quality/current-candidate-vs-baseline-m259-qwen-a3b.json \
  --output-json artifacts/m259-release-gate-response-quality/quality-preserving-release-gate-m259.json \
  --output-md artifacts/m259-release-gate-response-quality/quality-preserving-release-gate-m259.md \
  --tag m259-release-gate-response-quality \
  --fail-on-fail
```

Result:

- verdict: `PASS`
- gates: `16`
- failures: `0`
- categories include: `response_quality`
- current candidate quality points: `130/130`
- current candidate mean service request: `345.282 ms`

## Conclusion

M259 is complete. Future performance work now has a release-blocking
response-quality gate. Speed gains cannot be promoted unless the release gate is
given a current candidate-vs-baseline comparison artifact and that artifact
passes against the accepted Qwen A3B live baseline.
