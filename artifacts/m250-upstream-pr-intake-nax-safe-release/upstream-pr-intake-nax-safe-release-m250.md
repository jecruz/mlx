# M250 Upstream PR Intake NAX-Safe Release Checkpoint

Timestamp: `2026-05-27T18:13:30Z`

Branch: `prompt-processing-bench`

Base before intake: `918e11d5 docs(m249): refresh release evidence bundle`

Merged head: `08dea127 docs: record upstream PR intake validation`

## Scope

M250 promotes the recommended upstream PR intake batch into
`prompt-processing-bench` after isolated branch validation. The batch is focused
on Mac/Metal release stability and explicit NAX fallback control rather than
new performance tuning.

## Promoted Upstream PRs

- PR `#3593`: `MLX_DISABLE_NAX`
  - Adds a CMake option to skip Metal 4 NAX kernels at build time.
  - This gives the Mac runtime an explicit safety lever when the Metal toolchain
    or OS combination miscompiles NAX kernels.
- PR `#3523`: command-buffer error poisoning
  - Catches Metal command-buffer failures and poisons dependent events.
  - This prevents dependent work from continuing after a failed GPU command.
- PR `#3434`: custom-kernel cache safety
  - Avoids clearing in-flight pipeline states in the custom kernel cache.
  - This reduces risk around concurrent custom-kernel compilation and execution.

## Validation

- CMake configure passed with `-DMLX_DISABLE_NAX=ON`.
- Native targets built successfully:
  - `mlx`
  - `mlx-metallib`
  - `tests`
- Targeted CTest passed:
  - command pattern:
    `ctest --test-dir /private/tmp/mlx-m250-nax-safe-build -R 'test (scheduler races|custom kernel|gpu|metal|stream|compile)' --output-on-failure`
  - result: `33/33` tests passed.
- Quality-preserving release gate passed:
  - artifact:
    `artifacts/m250-upstream-pr-intake-nax-safe-release/quality-preserving-release-gate-m250.json`
  - verdict: `PASS`
  - gates: `15`
  - failures: `0`

## Notes

- CMake configure required outside-sandbox execution because the Metal toolchain
  writes to `~/.cache/clang/ModuleCache`.
- The build emitted one pre-existing warning in `tests/random_tests.cpp` about
  implicit integer-to-float conversion of `UINT32_MAX`; this is unrelated to the
  PR intake.
- The next upstream PR candidates are intentionally left out of M250:
  - PR `#3580`: batched matmul for large 1D dot products.
  - PR `#3385`: SDPA vmap fixes for GQA/MQA shapes.
  - PR `#3552`: sliding-window SDPA kernel path.

## Conclusion

M250 is release-ready for the stability/control intake batch. The branch now has
an explicit NAX disable build path plus two Metal execution-safety fixes, with
native build/test evidence and the release quality gate still passing.
