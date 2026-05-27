# M256 Post-Intake Attention And Prompt Sweep

Timestamp: `2026-05-27T22:13:09Z`

Branch: `prompt-processing-bench`

Base: `6f686057 docs(m255): recheck conflicting upstream prs`

## Scope

M256 validates the branch after completing M252-M255:

- M252: PR `#3385` SDPA vmap GQA/MQA fix
- M253: PR `#3552` sliding-window SDPA path
- M254: PR `#3485` GatherQMM shapeless compile output-shape fix
- M255: conflicting PR recheck

The goal is to verify attention correctness, compile/GPU/vmap coverage, and the
existing prompt-processing release gates after the upstream intake batch.

## Validation

### Release Quality And Prompt-Processing Gate

- Command:
  `python3 benchmarks/python/release_quality_performance_gate.py --output-json artifacts/m256-post-intake-attention-prompt-sweep/quality-preserving-release-gate-m256.json --output-md artifacts/m256-post-intake-attention-prompt-sweep/quality-preserving-release-gate-m256.md --tag m256-post-intake-attention-prompt-sweep --fail-on-fail`
- Verdict: `PASS`
- Gates: `15`
- Failures: `0`

### C++ Compile/GPU/Vmap Sweep

- Build dir: `/private/tmp/mlx-pr3485-gather-qmm-build`
- Command:
  `ctest --test-dir /private/tmp/mlx-pr3485-gather-qmm-build -R 'test (compile|gpu|vmap)' --output-on-failure`
- Result: `42/42` tests passed.

### Local-Built Python Attention And Compile Tests

- Local extension:
  `/private/tmp/mlx-pr3485-gather-qmm-build/mlx/core.cpython-314-darwin.so`
- Command:
  `python3 -m unittest python.tests.test_fast_sdpa python.tests.test_compile.TestCompile.test_shapeless_compile_gather_qmm`
- Result: `20` tests run, `1` skipped, `0` failures.

## Conclusion

The post-intake branch preserves release quality and prompt-processing gates
while passing targeted Metal/GPU/vmap, SDPA, and GatherQMM shapeless compile
validation. M252-M256 are complete.
