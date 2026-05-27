# M252 PR 3385 Promotion Checkpoint

Timestamp: `2026-05-27T21:53:08Z`

Promoted branch: `prompt-processing-bench`

Promoted head: `e6dc4556 docs(m252): record sdpa vmap gqa intake`

Source branch: `upstream-pr-3385-sdpa-vmap-gqa`

## Promotion

The validated PR `#3385` intake branch was fast-forward merged into
`prompt-processing-bench`.

Included commits:

- `0c5cb227` Fix SDPA vmap with GQA/MQA shapes
- `e6dc4556` Record M252 validation and crash evidence

## Post-Promotion Validation

- Release quality gate rerun on `prompt-processing-bench`.
- Verdict: `PASS`
- Gates: `15`
- Failures: `0`
- Artifacts:
  - `quality-preserving-release-gate-m252-promoted.json`
  - `quality-preserving-release-gate-m252-promoted.md`

## Promotion Decision

Promote. The patch directly addresses the installed-wheel SDPA vmap crash
class, and the promoted branch retains release-gate readiness.
