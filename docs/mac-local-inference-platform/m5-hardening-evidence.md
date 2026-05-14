# M5 Engine Hardening and macOS Integration

## Scope

M5 covers the hardening work that was intentionally moved out of M4:

- explicit unload and memory/cache release policy
- launchd/app-helper packaging path
- VLM processor validation plan
- model-family-specific deterministic text parity

## Implemented Evidence

### Explicit Unload and Memory Policy

Implemented in `benchmarks/python/resident_mlx_service.py`:

- `POST /engine/unload`
- unloaded-state metadata from `GET /engine`
- unloaded health response with `loaded=false`
- inference endpoints reject requests when no model is loaded
- reload works from unloaded state using the last model path or a supplied model path
- unload and reload call `gc.collect()` and `mx.clear_cache()` when available

Validated through packaged CLI:

```bash
bin/mlx-engine smoke --base-url http://127.0.0.1:8765
bin/mlx-engine correctness --base-url http://127.0.0.1:8765
```

Observed output:

```text
health True Device(gpu, 0) /Users/jeffreycruz/Development/LLM_INFERENCE/mlx/.worktrees/prompt-processing-bench/gpt-oss-20b-MXFP4-Q8-prefill-profile.json 0
engine 0 True balanced,memory_saver,throughput_default
generate req_58ceefc7e23b4144ba25dc734f5bcb65 memory_saver 512 9 8 length
completion text_completion length 13 memory_saver
chat chat.completion assistant 77 512
stream_completion 5 True
stream_chat 6 True
metrics 5 5 0 5
unload False 1 /Volumes/StudioStackSSD4TB/Development/LLM/lmstudio/models/mlx-community/gpt-oss-20b-MXFP4-Q8
reload 1 Device(gpu, 0) True [64]
correctness ok Device(gpu, 0) True 2 0
```

### launchd / App-Helper Packaging Path

Added a launchd template:

```text
packaging/launchd/com.jecruz.mlx-engine.plist.template
```

The template runs:

```bash
bin/mlx-engine serve --model __MODEL_PATH__ --host 127.0.0.1 --port 8765 --require-gpu
```

This is intentionally a template, not an installed LaunchAgent. The model path, repo root, and log directory must be filled by the app/helper or install script.

### VLM Processor Validation

Added static VLM package probe:

```text
benchmarks/python/vlm_processor_static_probe.py
```

Report:

```text
qwen3_6-vlm-processor-static-report.json
```

The probe checks:

- required VLM package files
- `vision_config`
- image/video/vision special token IDs
- core vision config keys
- shard completeness
- chat template vision markers

This is a static compatibility gate. It does not yet validate real image tensor layout, image patch expansion, or multimodal position IDs at runtime.

Static probe result:

```text
Qwen3.6-27B-UD-MLX-4bit passes=true, processor_class=Qwen3VLProcessor, patch_size=16, spatial_merge_size=2, temporal_patch_size=2
Qwen3.6-35B-A3B-UD-MLX-4bit passes=true, processor_class=Qwen3VLProcessor, patch_size=16, spatial_merge_size=2, temporal_patch_size=2
```

## Remaining Hardening

- install script for the launchd template
- app-helper integration with a signed macOS bundle
- runtime VLM image tensor and position-ID parity tests
- deterministic sampler controls for exact repeat-text parity
