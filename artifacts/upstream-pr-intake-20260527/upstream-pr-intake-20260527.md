# Upstream PR Intake - 2026-05-27

Branch: `upstream-pr-intake-20260527`

Base: `prompt-processing-bench` at `918e11d5`

## Applied PRs

- `#3593` - Add `MLX_DISABLE_NAX` option to skip Metal-4 nax kernels at build time.
- `#3523` - Catch error in CommandBuffer and poison the events.
- `#3434` - Avoid clearing in-flight pipeline states in custom kernel cache.

## Rationale

These PRs were selected because they are Mac/Metal-relevant, apply cleanly, and improve correctness or runtime stability without bringing in large experimental API surfaces.

`#3593` is especially relevant for local inference quality because it provides an explicit build flag for avoiding Metal-4 NAX kernels when the macOS 26 Metal toolchain miscompiles those paths.

## Validation

Configured with:

```bash
cmake -S /Users/jeffreycruz/Development/LLM_INFERENCE/mlx/.worktrees/prompt-processing-bench \
  -B /private/tmp/mlx-pr-intake-20260527-build3 \
  -DCMAKE_BUILD_TYPE=Release \
  -DMLX_BUILD_TESTS=ON \
  -DMLX_DISABLE_NAX=ON
```

Built targets:

- `mlx`
- `mlx-metallib`
- `tests`

Targeted tests:

```bash
ctest --test-dir /private/tmp/mlx-pr-intake-20260527-build3 \
  -R 'test (scheduler races|custom kernel|gpu|metal|stream|compile)' \
  --output-on-failure
```

Result: `33/33` tests passed.

## Notes

The first sandboxed CMake attempts failed because the Metal compiler tried to write to `~/.cache/clang/ModuleCache`. Running configure/build outside the sandbox resolved that environment issue.

The post-commit hook reported permission errors writing `/Users/jeffreycruz/.hooks/logs/code-review-post-commit.log`, but the cherry-pick commits completed successfully.
