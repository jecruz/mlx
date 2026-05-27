# M251 Upstream PR 3580 Batched Matmul Intake

Timestamp: `2026-05-27T21:18:46Z`

Branch: `upstream-pr-3580-batched-matmul`

Base: `95d7fbe0 docs(m250): record nax-safe upstream intake`

## Scope

M251 starts the intake of upstream PR `#3580`, "Implement batched matmul for
large 1D dot products". The PR routes large GPU 1D `tensordot`/inner-product
work through chunked batched matmul once the contracted size reaches
`32 * 4096`.

## Applied Commits

- `fb488bce` / local `bf6f406c`: Route large 1D dot products through batched
  matmul.
- `24d639d4` / local `8b58a1b6`: Change chunk size.
- `0d2e6209` / local `619aae8c`: Remove operand-level checking.

The PR's merge-from-main commit was intentionally not cherry-picked.

## Local Hardening

- Added `test gpu large 1d tensordot` in `tests/gpu_tests.cpp`.
- The test exercises the thresholded GPU path with length `32 * 4096 + 17`,
  which covers both full chunks and tail handling.

## Validation

- CMake configure passed with `-DMLX_DISABLE_NAX=ON`.
- Native targets built successfully:
  - `mlx`
  - `mlx-metallib`
  - `tests`
- Focused regression test passed:
  - `/private/tmp/mlx-pr3580-batched-matmul-build/tests/tests -tc="test gpu large 1d tensordot"`
  - result: `1` test case passed, `1` assertion passed.
- Targeted CTest passed:
  - `ctest --test-dir /private/tmp/mlx-pr3580-batched-matmul-build -R 'test (ops|blas|gpu|compile)' --output-on-failure`
  - result: `31/31` tests passed.
- Quality-preserving release gate passed:
  - artifact:
    `artifacts/m251-upstream-pr-3580-batched-matmul/quality-preserving-release-gate-m251.json`
  - verdict: `PASS`
  - gates: `15`
  - failures: `0`
- Focused microbenchmark passed:
  - target:
    `/private/tmp/mlx-pr3580-batched-matmul-bench-build/benchmarks/cpp/large_1d_tensordot`
  - compared the prior single-matmul lowering against the optimized large 1D
    `tensordot` path
  - average speedups across three `200`-iteration trials:
    - length `131089`: `1.49x`
    - length `262144`: `1.67x`
    - length `1048576`: `2.91x`
  - raw data:
    `artifacts/m251-upstream-pr-3580-batched-matmul/large-1d-tensordot-microbenchmark-m251.csv`

## Notes

- The first CTest attempt from inside the sandbox failed because Metal was not
  accessible. The rerun outside the sandbox passed all targeted tests.
- The build emitted the pre-existing `UINT32_MAX` implicit integer-to-float
  conversion warning in `tests/random_tests.cpp`; this is unrelated to PR
  `#3580`.

## Conclusion

PR `#3580` applies cleanly on top of M250 and passes native build/test
validation plus the release quality gate. The focused microbenchmark shows a
clear speedup on the exact large 1D GPU tensordot path changed by the PR, so the
branch is ready for review and promotion.
