# M253 PR 3552 Promotion Checkpoint

Timestamp: `2026-05-27T22:00:36Z`

Promoted branch: `prompt-processing-bench`

Promoted head: `7582ce3c fix(m253): integrate sliding sdpa with vmap path`

Source branch: `upstream-pr-3552-sliding-window-sdpa`

## Promotion

The validated PR `#3552` intake branch was fast-forward merged into
`prompt-processing-bench`.

Included commits:

- `f223ee61` Add sliding-window SDPA kernel path
- `dca094f5` Tighten sliding-window SDPA semantics
- `7582ce3c` Integrate sliding-window SDPA with the M252 vmap path

## Post-Promotion Validation

- Release quality gate rerun on `prompt-processing-bench`.
- Verdict: `PASS`
- Gates: `15`
- Failures: `0`
- Artifacts:
  - `quality-preserving-release-gate-m253-promoted.json`
  - `quality-preserving-release-gate-m253-promoted.md`

## Promotion Decision

Promote. The patch passed native build/test validation, local-built Python SDPA
validation, and the promoted release gate after resolving the M252/M253
signature integration issue.
