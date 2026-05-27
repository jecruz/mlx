# M253 Upstream PR 3552 Sliding-Window SDPA Intake

Timestamp: `2026-05-27T21:58:47Z`

Branch: `upstream-pr-3552-sliding-window-sdpa`

Base: `7cc89e9f docs(m252): record pr3385 promotion`

Upstream PR: `#3552`

Title: `feat(fast): add sliding-window SDPA kernel path`

## Scope

M253 applies upstream PR `#3552`, adding a `window_size` option to scaled dot
product attention and routing eligible Metal SDPA calls through a
sliding-window kernel path.

## Applied Commits

- upstream `efc195b6` / local `f223ee61`: `feat(fast): add sliding-window SDPA kernel path`
- upstream `77eb21da` / local `dca094f5`: `fix(fast): tighten sliding-window SDPA semantics`

## Local Integration Fix

M252 introduced a dedicated SDPA `vmap` path before M253 was applied. PR `#3552`
adds `window_size` before the stream argument in `scaled_dot_product_attention`.
The combined branch initially failed to compile because the M252 vmap path still
passed `Stream` in the old argument position.

Fix applied:

- updated the M252 vmap re-invocation to pass `window_size=-1` before `s`

This preserves standard full-attention behavior for the vmap path while matching
the new M253 signature.

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
  - `ctest --test-dir /private/tmp/mlx-pr3552-sliding-sdpa-build -R 'test (gpu|compile|vmap)' --output-on-failure`
  - result: `42/42` tests passed.
- Local Python extension import verified:
  - `/private/tmp/mlx-pr3552-sliding-sdpa-build/mlx/core.cpython-314-darwin.so`
- Full local-built Python fast SDPA test file passed:
  - `python3 -m unittest python.tests.test_fast_sdpa`
  - result: `19` tests run, `1` skipped.
- Quality-preserving release gate passed:
  - artifact:
    `artifacts/m253-upstream-pr-3552-sliding-window-sdpa/quality-preserving-release-gate-m253.json`
  - verdict: `PASS`
  - gates: `15`
  - failures: `0`

## Notes

- Native build emitted the pre-existing `UINT32_MAX` implicit integer-to-float
  warning in `tests/random_tests.cpp`; unrelated to this PR.
- Validation used `MLX_DISABLE_NAX=ON`, consistent with the M250 safety path.

## Conclusion

PR `#3552` is integrated with M252, builds successfully after the local
signature fix, and passes native plus local-built Python SDPA validation. M253 is
ready for review and promotion.
