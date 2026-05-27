# M255 Conflicting PR Recheck

Timestamp: `2026-05-27T22:11:23Z`

Branch: `prompt-processing-bench`

Base: `3f95f162 docs(m254): record pr3485 promotion`

## Scope

M255 re-checks previously conflicting upstream PR candidates after M252-M254
changed the attention, compile, and shape-inference surfaces.

## Method

Fetched current PR heads and ran:

```bash
git merge-tree --write-tree HEAD refs/remotes/origin/pr/<number>
```

This checks whether each PR can merge cleanly without modifying the worktree.

## Results

| PR | Status | Conflict Files | Decision |
| --- | --- | --- | --- |
| `#3578` new thread-unsafe stream API | Conflicts | `mlx/backend/cpu/encoder.cpp`, `mlx/backend/cpu/encoder.h`, `mlx/backend/cpu/eval.cpp`, `mlx/backend/cpu/eval.h`, `mlx/backend/metal/eval.cpp`, `mlx/stream.cpp` | Defer or manual adaptation only |
| `#3563` CPU GatherMM one-row NaNs | Conflicts | `mlx/backend/no_gpu/allocator.cpp`, `tests/allocator_tests.cpp` | Manual adaptation candidate |
| `#3562` SwiftPM metallib lookup | Conflicts | `mlx/backend/no_gpu/allocator.cpp`, `tests/allocator_tests.cpp` | Defer unless packaging need becomes urgent |
| `#3192` command-buffer byte accounting | Conflicts | `mlx/backend/metal/device.cpp`, `mlx/backend/metal/device.h` | Manual adaptation candidate, but high-risk after M250 Metal safety changes |
| `#3002` attention mask edge | Conflicts | `mlx/backend/metal/kernels/steel/attn/kernels/steel_attention_nax.h` | Defer until NAX path is re-enabled/tested broadly |

## Read

- `#3563` is the most plausible next manual-adaptation candidate because it is
  correctness-oriented and scoped to GatherMM/no-GPU allocator test conflicts.
- `#3192` is performance/observability-relevant, but it conflicts with Metal
  device changes from the M250 safety intake and needs careful manual review.
- `#3002` conflicts directly in `steel_attention_nax.h`; because this branch
  currently validates with `MLX_DISABLE_NAX=ON`, adapting NAX-only behavior is
  lower immediate value.
- `#3578` has broad stream/eval conflicts and should not be mixed into the
  current performance-stability intake without a dedicated milestone.
- `#3562` looks packaging/runtime useful but not directly performance-critical.

## Conclusion

No previously conflicting PR became clean after M252-M254. M255 is complete as a
recheck and triage milestone. Recommended next manual-adaptation order:

1. `#3563`
2. `#3192`
3. `#3562`
4. `#3002`
5. `#3578`
