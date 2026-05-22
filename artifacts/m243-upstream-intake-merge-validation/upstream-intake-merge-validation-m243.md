# M243 Upstream Intake Merge Validation

Status: PASS

## Acceptance

Fast-forward `prompt-processing-bench` to the validated upstream intake branch,
push the merged branch, and verify native C++/Metal plus Python/Metal import
health.

## Merge

- Source branch: `upstream-intake-20260522`
- Target branch: `prompt-processing-bench`
- Merge mode: fast-forward
- Previous target head: `b227899d`
- New target head: `d9077d8d`
- Push: `jecruz/prompt-processing-bench`

## Upstream Commits Integrated

Integrated `16` upstream commits:

- `f7f50408` win: fix cuda build (#3532)
- `933a4a77` Improve DLPack-compatible array imports (#3495)
- `3ab748b7` Apply the same thread-local approach to the CPU (#3537)
- `046217bc` Removed automatic prepending python in mlx launch (#3536)
- `7b7c1240` ci: Show stack trace on crash (#3538)
- `a5f4672d` Handle non-multiple-of-8 spatial dims in depthwise conv2d Metal path (#3446)
- `ff381c3b` Remove reference to groups in Conv3D extra_repr (#3559)
- `f831bdfc` Add buffer caching to no_gpu CPU allocator (#3554)
- `2414e5df` Fix steel GEMM safe load offset (#3560)
- `4f5b3ff3` Fix singleton lifetime issues at process exit (#3555)
- `b226aaf7` Fix doubled-word typos in docstrings (#3561)
- `e0163f3a` Synchronize no-GPU cache eviction with CPU streams (#3566)
- `5d1c0e4c` Add JIT compiler support for Windows (#3556)
- `14500605` [Metal] Reject tensor-scale nvfp4 in qqmm (#3551)
- `cc3ef8d9` Detect int32 shape-product overflow at MLX compute-shape boundaries (#3524)
- `2d2d59e7` Add `copy` keyword to `mx.asarray` (#3510)

Skipped upstream commit:

- `423b5149` Fix off_x/off_y typo in steel BaseMMAFrag::load_safe (#3565)

Reason: cherry-pick was empty after prior upstream commits were applied.

## Validation

Static:

```bash
git diff --check HEAD~16..HEAD
```

Result: `PASS`

CMake configure:

```bash
cmake -S . -B /private/tmp/mlx-upstream-intake-build -DCMAKE_BUILD_TYPE=Release -DMLX_BUILD_TESTS=ON
```

Result: `PASS`

Native build:

```bash
cmake --build /private/tmp/mlx-upstream-intake-build --target mlx mlx-metallib tests
```

Result: `PASS`

Targeted C++ tests:

```bash
/private/tmp/mlx-upstream-intake-build/tests/tests --test-case="test cached allocation keeps capacity"
/private/tmp/mlx-upstream-intake-build/tests/tests --test-case="test clear cache synchronizes cpu streams"
/private/tmp/mlx-upstream-intake-build/tests/tests --test-case="test gpu int32 shape overflow errors"
/private/tmp/mlx-upstream-intake-build/tests/tests --test-case="test gpu depthwise conv2d non-mod-8 spatial"
/private/tmp/mlx-upstream-intake-build/tests/tests --test-case="test scheduler races"
```

Result: `PASS`

Python/Metal validation via tmux pane `codex-gpt5_5-panthro_cpp:1.2`:

```bash
git branch --show-current
git rev-parse --short HEAD
python3 -c "import mlx; print(mlx.__file__)"
python3 -c "import mlx.core as mx; print(mx.metal.is_available(), mx.default_device())"
env -i HOME="$HOME" PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin" python3 -c "import mlx.core as mx; print(mx.metal.is_available(), mx.default_device())"
```

Observed:

- branch: `prompt-processing-bench`
- head: `d9077d8d`
- `import mlx`: `None`
- normal Metal import: `True Device(gpu, 0)`
- minimal-env Metal import: `True Device(gpu, 0)`

## Performance Impact

M243 is an upstream intake and validation milestone. It does not rerun the live
Qwen2.5 performance suite, so the current live performance baseline remains
M241 until M246 reruns the full post-upstream comparison.

Current preserved baseline:

- M241 low-memory baseline service: `4565.484 ms`
- M241 first duplicate service: `187.867 ms`
- M241 best hit service: `185.230 ms`
- M241 best-hit speedup: `24.648x`
- M241 max active memory: `9.669 GB`
- M241 max peak memory: `9.689 GB`
- M241 adapted quality threshold: `PASS`

## Conclusion

M243 passes. The upstream intake is now merged into `prompt-processing-bench`,
the branch is pushed, native C++/Metal validation is green, and Python/Metal
import validation is green through the tmux execution path.
