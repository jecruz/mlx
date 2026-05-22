# M244 Python Package Validation via tmux Harness

Status: PASS

## Acceptance

Turn the tmux Python/Metal import workaround into a repeatable validation
harness for MLX package checks.

## Implementation

Added two scripts:

- `benchmarks/python/python_package_validation_probe.py`
- `benchmarks/python/tmux_python_package_validation.py`

The probe runs inside the tmux pane and validates:

- Python executable and version
- `import mlx`
- `import mlx.core as mx`
- `mx.metal.is_available()`
- `mx.default_device()`
- minimal-env Python/Metal import using `env -i`

The tmux harness validates:

- target pane exists
- probe script exists
- probe creates JSON before timeout
- tmux completion marker is observed
- probe verdict is `PASS`

## Command

```bash
python3 benchmarks/python/tmux_python_package_validation.py \
  --pane codex-gpt5_5-panthro_cpp:1.2 \
  --repo-root /Users/jeffreycruz/Development/LLM_INFERENCE/mlx/.worktrees/prompt-processing-bench \
  --output-json artifacts/m244-python-package-tmux-validation/python-package-validation-m244.json \
  --tag m244-python-package-tmux-validation \
  --require-gpu \
  --fail-on-fail
```

## Result

```text
tmux_python_package_validation PASS failures 0
```

Probe artifact:

- `artifacts/m244-python-package-tmux-validation/python-package-validation-m244.json`

Harness artifact:

- `artifacts/m244-python-package-tmux-validation/python-package-validation-m244-harness.json`

Observed probe output:

- Python executable:
  `/Library/Frameworks/Python.framework/Versions/3.14/bin/python3`
- Python version: `3.14.0`
- `mlx_file`: `null`
- Metal available: `true`
- default device: `Device(gpu, 0)`
- minimal-env output: `True Device(gpu, 0)`
- failures: `0`

## Performance Impact

M244 does not change inference code or rerun live model benchmarks. It makes
Python/Metal package validation repeatable from a known Metal-capable tmux
context, which closes the validation gap caused by direct Codex shell imports
crashing in `mlx::core::metal::Device::Device()`.

Current preserved live baseline remains M241:

- first duplicate service: `187.867 ms`
- best hit service: `185.230 ms`
- best-hit speedup: `24.648x`
- max peak memory: `9.689 GB`
- adapted quality threshold: `PASS`

## Conclusion

M244 passes. Python package validation can now be run through a repeatable tmux
harness instead of manual pane command injection.
