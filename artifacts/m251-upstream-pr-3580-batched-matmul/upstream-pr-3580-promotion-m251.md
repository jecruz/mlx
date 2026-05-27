# M251 PR 3580 Promotion Checkpoint

Timestamp: `2026-05-27T21:40:26Z`

Promoted branch: `prompt-processing-bench`

Promoted head: `4209b87e bench(m251): add large 1d tensordot microbenchmark`

Source branch: `upstream-pr-3580-batched-matmul`

## Promotion

The validated PR `#3580` intake branch was fast-forward merged into
`prompt-processing-bench`.

Included commits:

- `bf6f406c` Route large 1D dot products through batched matmul
- `8b58a1b6` Change chunk size
- `619aae8c` Remove operand level checking
- `f32e6a7a` Add M251 large GPU 1D tensordot regression coverage and intake
  artifacts
- `4209b87e` Add focused large 1D tensordot microbenchmark and evidence

## Post-Promotion Validation

- Release quality gate rerun on `prompt-processing-bench`.
- Verdict: `PASS`
- Gates: `15`
- Failures: `0`
- Artifacts:
  - `quality-preserving-release-gate-m251-promoted.json`
  - `quality-preserving-release-gate-m251-promoted.md`

## Promotion Decision

Promote. The branch has correctness coverage, release-gate coverage, and
microbenchmark evidence showing the targeted large 1D GPU `tensordot` path is
faster than the prior single-matmul lowering.
