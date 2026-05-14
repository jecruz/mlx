# Qwen3.6 ROPE / IMROPE Parity

## Result

The tested MLX Qwen3.6 model configs and installed `mlx-vlm` Qwen3.5/Qwen3.6 rotary implementation match the IMROPE behavior now handled in `puma.cpp` and `panthro.cpp` for the tested dense and MoE checkpoints.

Validation artifact: `qwen3_6-imrope-parity-report.json`

Probe: `benchmarks/python/qwen_imrope_static_probe.py`

## Tested Models

| Model | Text model type | Architecture | Result |
| --- | --- | --- | --- |
| `/Volumes/StudioStackSSD4TB/Development/LLM/lmstudio/models/unsloth/Qwen3.6-27B-UD-MLX-4bit` | `qwen3_5_text` | `Qwen3_5ForConditionalGeneration` | Pass |
| `/Volumes/StudioStackSSD4TB/Development/LLM/lmstudio/models/unsloth/Qwen3.6-35B-A3B-UD-MLX-4bit` | `qwen3_5_moe_text` | `Qwen3_5MoeForConditionalGeneration` | Pass |

Both configs include:

```json
{
  "mrope_interleaved": true,
  "mrope_section": [11, 11, 10],
  "partial_rotary_factor": 0.25,
  "rope_theta": 10000000,
  "rope_type": "default"
}
```

Both configs also use `head_dim = 256`, so the rotary dimension is `256 * 0.25 = 64`, which yields `32` rotary frequency lanes.

## What Was Compared

The MLX path uses `mlx_vlm.models.qwen3_5.language.Qwen3_5RotaryEmbedding`:

- It builds three position streams: temporal, height, and width.
- It calls `apply_interleaved_mrope`.
- It assigns height lanes with `slice(1, mrope_section[1] * 3, 3)`.
- It assigns width lanes with `slice(2, mrope_section[2] * 3, 3)`.
- All remaining lanes retain the temporal stream.

The puma/panthro path marks Qwen3.5/Qwen3.6 architectures as IMROPE and routes them through `ggml_rope_multi` with `LLAMA_ROPE_TYPE_IMROPE`. In the CPU reference path, IMROPE selects lanes by sector:

- `sector % 3 == 0` maps to temporal.
- `sector % 3 == 1` maps to height.
- `sector % 3 == 2` maps to width.
- Any remaining sector maps to the extra stream.

For the tested Qwen3.6 section shape `[11, 11, 10]` over 32 frequency lanes, both implementations produce the same owner sequence:

```text
thwthwthwthwthwthwthwthwthwthwth
```

The probe found:

- Dense 27B mismatch count: `0`
- MoE 35B-A3B mismatch count: `0`
- Overall pass: `true`

## Interpretation

For these MLX checkpoints, the ROPE/IMROPE behavior is not the likely cause of hallucination, looping, or prompt-processing slowness.

The next correctness risks are higher in the stack:

- prompt template and chat-template fidelity
- stop-token and EOS handling
- sampler defaults and repetition control
- KV-cache position accounting under long context and multimodal prompts
- image-token layout and processor compatibility for full VLM paths

The parity result only covers the text-model rotary lane semantics. It does not prove full image preprocessor parity or full multimodal generation correctness.
