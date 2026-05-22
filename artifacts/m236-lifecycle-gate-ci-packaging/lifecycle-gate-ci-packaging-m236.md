# M236 Lifecycle Gate CI Packaging

M236 is complete. `package_resident_suite_evidence.py` can now package the M232
resident lifecycle regression gate alongside a resident regression suite evidence
bundle with one command.

## Code Change

`benchmarks/python/package_resident_suite_evidence.py` now accepts:

```bash
--lifecycle-gate-json artifacts/m232-resident-lifecycle-regression-gate/resident-lifecycle-regression-gate-m232.json
```

The generated `resident-suite-evidence-index.json` now includes a
`lifecycle_gate` summary with:

- verdict
- readiness
- check count
- failure count
- shutdown probe verdict
- startup preflight verdict

Disabled suite artifacts are no longer reported as missing. Only enabled
artifacts that are absent are counted as missing.

## Validation

Command:

```bash
python3 benchmarks/python/package_resident_suite_evidence.py \
  artifacts/m98-suite-low-memory-direct-evidence-package/resident-regression-suite-m98-qwen-a3b-low-memory-suite-direct.json \
  --output-dir artifacts/m236-lifecycle-gate-ci-packaging/resident-suite-evidence-package \
  --lifecycle-gate-json artifacts/m232-resident-lifecycle-regression-gate/resident-lifecycle-regression-gate-m232.json
```

Result:

- suite verdict: `PASS`
- lifecycle gate verdict: `PASS`
- copied artifacts: `6`
- missing enabled artifacts: `0`
- dax first-hit: `PASS`

## Performance

M236 is packaging-only. It does not change inference behavior.

Current carried-forward performance evidence remains:

- first duplicate service: `193.098 ms`
- first duplicate prefill: `11` tokens
- mature-hit speedup: `23.445x`
- max peak memory: `11.048 GB`

## Conclusion

M236 makes the lifecycle gate release/CI-packagable. The same evidence package
can now carry resident suite proof and the M232 lifecycle safety proof together.
