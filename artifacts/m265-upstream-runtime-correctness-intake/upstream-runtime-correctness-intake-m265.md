# M265 Upstream Runtime-Correctness Intake

Timestamp: `2026-06-03`

Branch: `upstream-intake-m265-runtime-correctness`

Base branch: `prompt-processing-bench`

## Purpose

Review and begin cherry-picking upstream runtime-correctness candidates 1-6 for
the resident MLX engine branch.

## Refreshed Upstream State

`origin/main` was refreshed before intake and had advanced to:

- `e9e20fa6` `Fix HDRS_LIST building when paths in header inclusion tree include spaces (#3607)`

## Requested Candidates

| Candidate | Upstream commit | Result | Local equivalent |
| --- | --- | --- | --- |
| 1 | `cc3ef8d9` `Detect int32 shape-product overflow at MLX compute-shape boundaries (#3524)` | already applied | `8bb5db7e` |
| 2 | `cd32966c` `Catch error in CommandBuffer and poison the events` | already applied | `2a2ca8bc` |
| 3 | `e0163f3a` `Synchronize no-GPU cache eviction with CPU streams (#3566)` | already applied | `7b5a6374` |
| 4 | `f831bdfc` `Add buffer caching to no_gpu CPU allocator (#3554)` | already applied | `f17617ad` |
| 5 | `4f5b3ff3` `Fix singleton lifetime issues at process exit (#3555)` | already applied | `1679ffc9` |
| 6 | `933a4a77` `Improve DLPack-compatible array imports (#3495)` | already applied | `6446b95c` |

## Conflict Note

Candidate 4 produced a transient conflict in:

- `mlx/backend/no_gpu/allocator.cpp`
- `tests/allocator_tests.cpp`

The resolution preserved both pieces of behavior:

- existing buffer-cache support from the local equivalent of `f831bdfc`
- later CPU-stream synchronization guards from the local equivalent of
  `e0163f3a`

After resolving, the cherry-pick still reduced to an empty patch and was
skipped.

## Validation

```bash
git log --all --oneline --grep="Detect int32 shape-product overflow"
git log --all --oneline --grep="Catch error in CommandBuffer"
git log --all --oneline --grep="Synchronize no-GPU cache eviction"
git log --all --oneline --grep="Add buffer caching to no_gpu CPU allocator"
git log --all --oneline --grep="Fix singleton lifetime issues"
git log --all --oneline --grep="Improve DLPack-compatible array imports"
git status --short --branch
git diff --check
```

## Conclusion

The requested upstream candidates 1-6 are already represented on the MLX engine
branch. No duplicate runtime code commit was needed for this intake session.
