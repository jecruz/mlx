# M254 Upstream PR 3485 GatherQMM Output Shapes Evaluation

Timestamp: `2026-05-27T22:06:42Z`

Branch: `upstream-pr-3485-gather-qmm-output-shapes`

Base: `7dc60dcf docs(m253): record pr3552 promotion`

Upstream PR: `#3485`

Title: `fix(compile): GatherQMM implements output_shapes for shapeless compile`

## Scope

M254 evaluates upstream PR `#3485`. The PR still reports
`CHANGES_REQUESTED`, but the requested CustomKernel portion was reverted
upstream. The current net patch is narrow:

- add `GatherQMM::output_shapes()`
- add a shapeless compile regression test for `mx.gather_qmm`

## Intake Decision

Apply the final net patch locally rather than cherry-picking the full upstream
commit history. The upstream branch includes reverted CustomKernel commits that
are not part of the current effective fix.

## Applied Local Patch

- `mlx/primitives.h`
  - implements `GatherQMM::output_shapes()`
  - derives output shape from `lhs_indices.shape()`, `x.shape(-2)`, and
    quantized weight outer dimension
- `python/tests/test_compile.py`
  - adds `test_shapeless_compile_gather_qmm`

## Validation

- CMake configure passed with:
  - `MLX_BUILD_TESTS=ON`
  - `MLX_BUILD_PYTHON_BINDINGS=ON`
  - `MLX_BUILD_PYTHON_STUBS=OFF`
  - `MLX_DISABLE_NAX=ON`
- Native targets built successfully:
  - `core`
  - `mlx-metallib`
  - `tests`
- Targeted CTest passed:
  - `ctest --test-dir /private/tmp/mlx-pr3485-gather-qmm-build -R 'test (compile|gpu|vmap)' --output-on-failure`
  - result: `42/42` tests passed.
- Local Python extension import verified:
  - `/private/tmp/mlx-pr3485-gather-qmm-build/mlx/core.cpython-314-darwin.so`
- Focused Python regression test passed:
  - `python3 -m unittest python.tests.test_compile.TestCompile.test_shapeless_compile_gather_qmm`
  - result: `1` test passed.
- Quality-preserving release gate passed:
  - artifact:
    `artifacts/m254-upstream-pr-3485-gather-qmm-output-shapes/quality-preserving-release-gate-m254.json`
  - verdict: `PASS`
  - gates: `15`
  - failures: `0`

## Notes

- The upstream `CHANGES_REQUESTED` review was for stale CustomKernel shape
  behavior. That code is no longer present in the current net diff.
- Native build emitted the pre-existing `UINT32_MAX` implicit integer-to-float
  warning in `tests/random_tests.cpp`; unrelated to this patch.

## Conclusion

The current effective PR `#3485` GatherQMM patch is valid for local intake. It
passes native compile/GPU/vmap coverage, the focused local-built Python
regression test, and the release quality gate. M254 is ready for promotion.
