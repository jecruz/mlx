# M249 Release Evidence Bundle Refresh

Status: PASS

## Acceptance

Refresh the release evidence bundle and quality/performance gate artifacts after first-duplicate regression recovery.

## Single Command

```bash
python3 benchmarks/python/package_release_evidence_bundle.py \
  --output-dir artifacts/m249-release-evidence-bundle/release-evidence-bundle \
  --fail-on-fail
```

## Result

```text
release_evidence_bundle PASS copied 20 required 20 failures 0 artifacts/m249-release-evidence-bundle/release-evidence-bundle/release-evidence-index.json
```

## Bundle Index

- Index:
  `artifacts/m249-release-evidence-bundle/release-evidence-bundle/release-evidence-index.json`
- Verdict: `PASS`
- Readiness: `release-evidence-ready`
- Required evidence items: `20`
- Copied evidence items: `20`
- Failures: `0`

## Refreshed Evidence Coverage

The refreshed release bundle now packages the original release inputs plus the recovered first-hit evidence:

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
- first-hit regression recovery report:
  `artifacts/m247-first-hit-regression-recovery/first-hit-regression-recovery-m247.md`
- first-hit regression recovery audit:
  `artifacts/m247-first-hit-regression-recovery/milestone-completion-audit-m247.json`
- first-hit regression recovery benchmark:
  `artifacts/m247-first-hit-regression-recovery/dax-first-hit-m247-qwen25-coder-14b.json`
- first-hit regression recovery conversion gate:
  `artifacts/m247-first-hit-regression-recovery/dax-first-hit-conversion-gate-m247-qwen25-coder-14b.json`
- first-duplicate budget release gate:
  `artifacts/m248-first-duplicate-budget-release-gate/quality-preserving-release-gate-m248.json`
- first-duplicate budget release audit:
  `artifacts/m248-first-duplicate-budget-release-gate/milestone-completion-audit-m248.json`

## Performance Report

M249 is a release evidence refresh milestone and does not change the inference hot path.

The refreshed evidence package now preserves:

- M247 first duplicate service: `185.660 ms`
- M247 best hit service: `179.281 ms`
- M247 best-hit speedup: `25.753x`
- M247 first-hit conversion gate: `PASS`
- M248 first-duplicate budget check: `185.660 ms <= 250 ms`
- M248 release gate count: `15`

## Conclusion

M249 passes. The refreshed release evidence bundle now includes the recovered first-hit artifacts and the first-duplicate release gate, and it packages them with one documented command.
