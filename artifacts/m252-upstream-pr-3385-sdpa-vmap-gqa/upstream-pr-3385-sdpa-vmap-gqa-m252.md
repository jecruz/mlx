# M252 Upstream PR 3385 SDPA Vmap GQA/MQA Intake

Timestamp: `2026-05-27T21:51:19Z`

Branch: `upstream-pr-3385-sdpa-vmap-gqa`

Base: `2c2593b8 docs(m251): record pr3580 promotion`

Upstream PR: `#3385`

Title: `Fix SDPA vmap with GQA/MQA shapes (n_heads != n_kv_heads)`

## Scope

M252 applies upstream PR `#3385`, which fixes SDPA under `vmap` when query head
count differs from key/value head count. This is a correctness and stability
intake for GQA/MQA attention shapes.

## Applied Commit

- upstream `14700f3a`: `Fix SDPA vmap with GQA/MQA shapes (n_heads != n_kv_heads)`
- local `0c5cb227`: same patch after cherry-pick

Changed files:

- `mlx/fast.cpp`
- `mlx/fast_primitives.h`
- `python/tests/test_fast_sdpa.py`

## Crash Evidence

The user-provided crash report from `2026-05-27 17:49:38 -0400` showed a
Python process importing the installed wheel:

- `/Library/Frameworks/Python.framework/Versions/3.14/lib/python3.14/site-packages/mlx/core.cpython-314-darwin.so`
- `/Library/Frameworks/Python.framework/Versions/3.14/lib/python3.14/site-packages/mlx/lib/libmlx.dylib`

The crashing stack includes:

- `mlx::core::broadcast_shapes`
- `mlx::core::Broadcast::vmap`
- `mlx::core::detail::vmap_replace`
- `mlx::core::fast::Custom::vmap`

That stack matches the failure class PR `#3385` addresses: SDPA vmap falling
back through the generic `Custom::vmap` path and mishandling shape/broadcast
state for GQA/MQA style inputs.

## Validation

- CMake configure passed with `-DMLX_DISABLE_NAX=ON`.
- Native targets built successfully:
  - `mlx`
  - `mlx-metallib`
  - `tests`
- Targeted CTest passed:
  - `ctest --test-dir /private/tmp/mlx-pr3385-sdpa-vmap-build -R 'test (gpu|compile|vmap)' --output-on-failure`
  - result: `42/42` tests passed.
- Python bindings were built for the local branch:
  - build dir: `/private/tmp/mlx-pr3385-sdpa-vmap-pybuild`
  - local extension import verified:
    `/private/tmp/mlx-pr3385-sdpa-vmap-pybuild/mlx/core.cpython-314-darwin.so`
- Focused Python PR test passed:
  - `python3 -m unittest python.tests.test_fast_sdpa.TestFastSDPA.test_sdpa_vmap_uses_fused_kernel`
  - result: `1` test passed.
- Full Python fast SDPA test file passed:
  - `python3 -m unittest python.tests.test_fast_sdpa`
  - result: `17` tests run, `1` skipped.
- Quality-preserving release gate passed:
  - artifact:
    `artifacts/m252-upstream-pr-3385-sdpa-vmap-gqa/quality-preserving-release-gate-m252.json`
  - verdict: `PASS`
  - gates: `15`
  - failures: `0`

## Notes

- The first Python unittest attempt imported the installed MLX wheel rather
  than the local branch. The validation path was corrected by staging the local
  built extension under `/private/tmp/mlx-pr3385-sdpa-vmap-pybuild/mlx/` and
  verifying `mx.__file__` before running tests.
- Native build emitted the pre-existing `UINT32_MAX` implicit integer-to-float
  warning in `tests/random_tests.cpp`; unrelated to this PR.

## Conclusion

PR `#3385` applies cleanly and directly addresses the SDPA vmap crash class
shown by the installed-wheel crash report. The local branch passes native
GPU/compile/vmap tests, local-built Python fast SDPA tests, and the release
quality gate. M252 is ready for promotion into `prompt-processing-bench`.
