# M240 Release Evidence Bundle Command

Status: PASS

## Acceptance

Provide a single documented release command that runs/collects quality, swap,
lifecycle, memory-guard, routing, and Prowl visibility artifacts.

## Single Command

```bash
python3 benchmarks/python/package_release_evidence_bundle.py \
  --output-dir artifacts/m240-release-evidence-bundle/release-evidence-bundle \
  --fail-on-fail
```

## Result

```text
release_evidence_bundle PASS copied 14 required 14 failures 0 artifacts/m240-release-evidence-bundle/release-evidence-bundle/release-evidence-index.json
```

## Bundle Index

- Index:
  `artifacts/m240-release-evidence-bundle/release-evidence-bundle/release-evidence-index.json`
- Verdict: `PASS`
- Readiness: `release-evidence-ready`
- Required evidence items: `14`
- Copied evidence items: `14`
- Failures: `0`

## Required Evidence Coverage

The release command packages and validates:

- quality threshold:
  `artifacts/m231-model-swap-artifact-freshness-refresh/quality-threshold-gate-m231-qwen25-coder-14b-adapted.json`
- model-swap acceptance:
  `artifacts/m231-model-swap-artifact-freshness-refresh/model-swap-acceptance-m231-qwen25-coder-14b.json`
- lifecycle gate:
  `artifacts/m232-resident-lifecycle-regression-gate/resident-lifecycle-regression-gate-m232.json`
- memory guard:
  `artifacts/m233-proactive-cache-memory-pressure-guard/proactive-cache-memory-pressure-guard-m233.json`
- routing policy:
  `artifacts/m234-lower-memory-default-routing-policy/lower-memory-default-routing-policy-gate-m234.json`
- resident-suite evidence package:
  `artifacts/m236-lifecycle-gate-ci-packaging/resident-suite-evidence-package/resident-suite-evidence-index.json`
- bounded first-hit benchmark:
  `artifacts/m237-bounded-first-hit-live-revalidation/dax-bounded-first-hit-m237-qwen25-coder-14b.json`
- bounded first-hit conversion gate:
  `artifacts/m237-bounded-first-hit-live-revalidation/dax-first-hit-conversion-gate-m237-qwen25-coder-14b.json`
- product-mode routing probe:
  `artifacts/m238-lower-memory-route-product-smoke/product-mode-metadata-probe-m238.json`
- live request profile probe:
  `artifacts/m238-lower-memory-route-product-smoke/live-request-profile-metadata-m238.json`
- Prowl installed-app health:
  `artifacts/m239-prowl-promotion-visibility-installed-app-smoke/prowl-app-health-m239.json`
- Prowl direct health:
  `artifacts/m239-prowl-promotion-visibility-installed-app-smoke/prowl-direct-health-m239.json`
- Prowl model catalog:
  `artifacts/m239-prowl-promotion-visibility-installed-app-smoke/prowl-models-m239.json`
- Prowl promotion visibility smoke:
  `artifacts/m239-prowl-promotion-visibility-installed-app-smoke/prowl-promotion-visibility-installed-app-smoke-m239.md`

## Performance Report

M240 is a release evidence packaging milestone and does not change the inference
hot path.

The packaged performance evidence preserves:

- M231 first duplicate service: `193.098 ms`
- M231 mature-hit speedup: `23.445x`
- M231 max peak memory: `11.048 GB`
- M237 bounded first-hit baseline service: `4310.493 ms`
- M237 first duplicate service: `186.185 ms`
- M237 best hit service: `183.017 ms`
- M237 mature-hit speedup: `23.152x`
- M237 cache memory: `0.022 GB`
- M238 low-memory routed service: `243.735 ms`

## Conclusion

M240 passes. Release evidence can now be collected with one command, and that
command fails if required quality, model-swap, lifecycle, memory-guard, routing,
first-hit, or Prowl visibility evidence is missing or not green.
