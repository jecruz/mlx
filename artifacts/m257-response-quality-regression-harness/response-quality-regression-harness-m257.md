# M257 Response Quality Regression Harness

Timestamp: `2026-05-27`

Branch: `prompt-processing-bench`

## Purpose

M257 adds the missing response-quality regression layer. Existing gates protect
runtime correctness and performance evidence, but this harness directly answers
whether a candidate optimization preserves user-facing answer quality.

## Implementation

- Added `benchmarks/python/response_quality_regression_harness.py`.
- Added `capture` mode for deterministic live endpoint quality artifacts.
- Added `compare` mode for baseline-versus-candidate quality regression checks.
- Added unit coverage in
  `benchmarks/python/test_response_quality_regression_harness.py`.

The comparison blocks promotion when the candidate:

- loses required task markers
- introduces case failures
- drops quality points beyond threshold
- increases repetition beyond threshold
- shows large completion-length drift coupled with lower quality

Latency is summarized next to quality, but latency improvement does not override
quality failure.

## Validation

- Unit tests:
  `python3 -m unittest benchmarks/python/test_response_quality_regression_harness.py`
  - result: `PASS`, `3` tests
- Compile:
  `python3 -m py_compile benchmarks/python/response_quality_regression_harness.py benchmarks/python/test_response_quality_regression_harness.py`
  - result: `PASS`
- Fixture comparison:
  `python3 benchmarks/python/response_quality_regression_harness.py compare ... --fail-on-fail`
  - result: `PASS`
  - failures: `0`

## Artifacts

- `artifacts/m257-response-quality-regression-harness/m257-fixture-baseline.json`
- `artifacts/m257-response-quality-regression-harness/m257-fixture-candidate.json`
- `artifacts/m257-response-quality-regression-harness/response-quality-regression-comparison-m257.json`
- `artifacts/m257-response-quality-regression-harness/response-quality-regression-comparison-m257.md`

## Live Follow-Up

Capture the accepted engine as the baseline:

```bash
python3 benchmarks/python/response_quality_regression_harness.py capture \
  --base-url http://127.0.0.1:8773 \
  --model local-mlx \
  --runtime-profile interactive \
  --temperature 0.0 \
  --top-p 1.0 \
  --seed 257 \
  --output-json artifacts/m257-response-quality-regression-harness/live-baseline.json \
  --output-md artifacts/m257-response-quality-regression-harness/live-baseline.md \
  --fail-on-fail
```

Then compare each candidate optimization branch:

```bash
python3 benchmarks/python/response_quality_regression_harness.py compare \
  --baseline-json artifacts/m257-response-quality-regression-harness/live-baseline.json \
  --candidate-json artifacts/m257-response-quality-regression-harness/live-candidate.json \
  --output-json artifacts/m257-response-quality-regression-harness/live-comparison.json \
  --output-md artifacts/m257-response-quality-regression-harness/live-comparison.md \
  --fail-on-fail
```

M257 is complete as a harness milestone. M258 should produce the first live
baseline artifact and wire it into the promotion checklist.
