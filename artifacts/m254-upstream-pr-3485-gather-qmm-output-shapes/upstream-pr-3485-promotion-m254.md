# M254 PR 3485 Promotion Checkpoint

Timestamp: `2026-05-27T22:09:34Z`

Promoted branch: `prompt-processing-bench`

Promoted head: `ac517b5a fix(m254): add gather qmm shapeless output shapes`

Source branch: `upstream-pr-3485-gather-qmm-output-shapes`

## Promotion

The validated final-net PR `#3485` GatherQMM patch was fast-forward merged into
`prompt-processing-bench`.

Included commit:

- `ac517b5a` Add GatherQMM output shape inference and shapeless compile test

## Post-Promotion Validation

- Release quality gate rerun on `prompt-processing-bench`.
- Verdict: `PASS`
- Gates: `15`
- Failures: `0`
- Artifacts:
  - `quality-preserving-release-gate-m254-promoted.json`
  - `quality-preserving-release-gate-m254-promoted.md`

## Promotion Decision

Promote. The stale upstream `CHANGES_REQUESTED` status targeted a CustomKernel
implementation that was reverted upstream. The local promoted patch only carries
the validated GatherQMM output-shape fix.
