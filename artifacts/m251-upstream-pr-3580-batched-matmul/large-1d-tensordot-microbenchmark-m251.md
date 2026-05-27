# M251 Large 1D Tensordot Microbenchmark

Timestamp: `2026-05-27T21:18:46Z`

Branch: `upstream-pr-3580-batched-matmul`

Benchmark target:
`/private/tmp/mlx-pr3580-batched-matmul-bench-build/benchmarks/cpp/large_1d_tensordot`

Build configuration:

- `CMAKE_BUILD_TYPE=Release`
- `MLX_BUILD_BENCHMARKS=ON`
- `MLX_DISABLE_NAX=ON`
- iterations per trial: `200`
- trials: `3`

## Compared Paths

- Prior path: explicit reshape to single `{1, n} x {n, 1}` GPU matmul.
- Optimized path: `mx::tensordot(a, b, {0}, {0}, Device::gpu)`, which now
  routes large 1D dot products through chunked batched matmul.

This compares against the old `tensordot` lowering rather than a generic
multiply+sum reference.

## Results

| Size | Avg Prior ms | Avg Optimized ms | Avg Speedup |
| ---: | ---: | ---: | ---: |
| 131089 | 0.349708 | 0.235376 | 1.49x |
| 262144 | 0.339352 | 0.202976 | 1.67x |
| 1048576 | 0.568831 | 0.195813 | 2.91x |

All trials produced matching scalar values between the prior and optimized
paths.

## Raw Data

See `large-1d-tensordot-microbenchmark-m251.csv`.

## Promotion Read

PR `#3580` gives a clear speedup on the exact large 1D GPU tensordot path it
targets, with larger benefits as vector length grows. The microbenchmark
supports promotion after the existing correctness and release-gate validation.
