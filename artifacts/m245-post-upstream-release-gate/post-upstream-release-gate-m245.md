# M245 Post-Upstream Release Gate Rerun

Status: PASS

## Acceptance

Rerun the release quality/performance gate after upstream intake and prove all
release-blocking artifacts remain green.

## Gate Update

`benchmarks/python/release_quality_performance_gate.py` now includes the M244
Python package tmux validation harness as a required release gate:

- key: `python_package_tmux_validation`
- category: `python_package`
- artifact:
  `artifacts/m244-python-package-tmux-validation/python-package-validation-m244-harness.json`

The gate verifies:

- harness verdict is `PASS`
- failures list is empty
- probe reports `metal_available: true`
- probe reports `Device(gpu, 0)`
- minimal-env import returns `0`
- minimal-env import reports `Device(gpu, 0)`

## Command

```bash
python3 benchmarks/python/release_quality_performance_gate.py \
  --output-json artifacts/m245-post-upstream-release-gate/quality-preserving-release-gate-m245.json \
  --output-md artifacts/m245-post-upstream-release-gate/quality-preserving-release-gate-m245.md \
  --tag m245-post-upstream-release-gate \
  --fail-on-fail
```

## Result

```text
quality_preserving_release_gate PASS gates 14 failures 0
```

## Coverage

- Verdict: `PASS`
- Readiness: `quality-preserving-release-ready`
- Gates: `14`
- Failures: `0`

Categories:

- `quality`
- `model_swap`
- `routing`
- `first_hit`
- `lower_memory`
- `lifecycle`
- `release_packaging`
- `python_package`

Required gates:

- `deterministic_quality_adapted`: `PASS`
- `quality_threshold`: `PASS`
- `model_swap_acceptance`: `PASS`
- `routing_policy`: `PASS`
- `product_mode_routing`: `PASS`
- `live_request_profile_routing`: `PASS`
- `bounded_first_hit_benchmark`: `PASS`
- `bounded_first_hit_conversion`: `PASS`
- `lower_memory_benchmark`: `PASS`
- `lower_memory_runtime`: `PASS`
- `lower_memory_first_hit_conversion`: `PASS`
- `lifecycle_regression`: `PASS`
- `release_evidence_bundle`: `PASS`
- `python_package_tmux_validation`: `PASS`

## Performance Report

M245 reruns the release-blocking manifest but does not rerun live model
benchmarks. It verifies that the post-upstream branch still satisfies the
existing quality/performance artifacts.

Current preserved performance evidence:

- M237 first-hit best service: `183.017 ms`
- M237 first-hit speedup: `23.552x`
- M241 low-memory first duplicate service: `187.867 ms`
- M241 low-memory best hit service: `185.230 ms`
- M241 low-memory speedup: `24.648x`
- M241 max active memory: `9.669 GB`
- M241 max peak memory: `9.689 GB`
- M244 Python/Metal package validation: `PASS`

## Conclusion

M245 passes. The post-upstream release gate remains green and now blocks release
if Python package/Metal validation regresses.
