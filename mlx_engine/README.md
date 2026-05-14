# MLX Engine Package

This package contains the stable resident MLX inference service code.

## Entrypoints

- `resident_service.py`: FastAPI resident engine implementation.
- `../bin/mlx-engine`: CLI wrapper for serving, smoke testing, and correctness
  checks.
- `../benchmarks/python/resident_mlx_service.py`: compatibility wrapper for
  existing benchmark scripts.

## Runtime Defaults

- The packaged CLI defaults to async warmup for interactive readiness.
- Direct `resident_service.py` defaults to sync warmup for explicit benchmark
  compatibility.
- Use `wait_resident_ready.py --require-warmup` when callers need warmed prompt
  latency rather than only loaded HTTP readiness.

## Current Boundary

Benchmark harnesses, probes, and generated evidence remain under
`benchmarks/python` and `docs/mac-local-inference-platform`. Engine code should
move into this package as APIs stabilize.
