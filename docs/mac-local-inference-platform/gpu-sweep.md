# GPU Prompt Sweep

Run this from a shell where MLX reports `Device(gpu, 0)`.

```bash
cd /Users/jeffreycruz/Development/LLM_INFERENCE/mlx/.worktrees/prompt-processing-bench
python3 -c "import mlx.core as mx; print(mx.metal.is_available(), mx.default_device())"
MODEL="/Volumes/StudioStackSSD4TB/Development/LLM/lmstudio/models/mlx-community/gpt-oss-20b-MXFP4-Q8"
test -f "$MODEL/config.json"
benchmarks/python/run_prompt_sweep.sh "$MODEL" gpu-prompt-sweep.jsonl
python3 benchmarks/python/summarize_prompt_sweep.py gpu-prompt-sweep.jsonl
```

The sweep fails before model load if MLX is not on GPU.

The summarizer prints `verdict: invalid_gpu_sweep` when MLX falls back to CPU, so
CPU fallback numbers cannot be mistaken for real Metal results.

## Steady-State Sweep

The shell sweep above reloads the model for each prompt length, so it is useful
for sanity checks but not final prompt-processing analysis. Use the in-process
sweep to load once, warm once, and then measure prompt lengths without repeated
model-load noise:

```bash
cd /Users/jeffreycruz/Development/LLM_INFERENCE/mlx/.worktrees/prompt-processing-bench
MODEL="/Volumes/StudioStackSSD4TB/Development/LLM/lmstudio/models/mlx-community/gpt-oss-20b-MXFP4-Q8"
python3 benchmarks/python/inprocess_prompt_sweep.py \
  --model "$MODEL" \
  --prompt-token-lengths 8,16,32,64,128,256,512 \
  --warmup-prompt-tokens 64 \
  --warmup-runs 1 \
  --repeats 2 \
  --require-gpu \
  --output-jsonl gpu-prompt-sweep-steady.jsonl
python3 benchmarks/python/summarize_prompt_sweep.py gpu-prompt-sweep-steady.jsonl
```

Observed result on `gpt-oss-20b-MXFP4-Q8`: the warmed in-process sweep reached
about `1.7-1.8k` prompt tok/s at 512 prompt tokens, while the reload-per-length
shell sweep only reached about `199` prompt tok/s at 64 prompt tokens. Use the
in-process sweep for optimization decisions.

## Next Sweep

Use longer prompts to find where prefill scaling bends:

```bash
python3 benchmarks/python/inprocess_prompt_sweep.py \
  --model "$MODEL" \
  --prompt-token-lengths 512,1024,2048,4096 \
  --warmup-prompt-tokens 512 \
  --warmup-runs 1 \
  --repeats 1 \
  --require-gpu \
  --output-jsonl gpu-prompt-sweep-long.jsonl
python3 benchmarks/python/summarize_prompt_sweep.py gpu-prompt-sweep-long.jsonl
```

Observed result on `gpt-oss-20b-MXFP4-Q8`: 512-4096 token prefill stayed
around `1.7k-2.1k` prompt tok/s, with 4096 prompt tokens completing in about
`2.16 s`.

## Prefill Step Sweep

Use the 4096-token shape to compare chunk sizes:

```bash
for STEP in 512 1024 2048 4096; do
  python3 benchmarks/python/inprocess_prompt_sweep.py \
    --model "$MODEL" \
    --prompt-token-lengths 4096 \
    --warmup-prompt-tokens 512 \
    --warmup-runs 1 \
    --repeats 1 \
    --prefill-step-size "$STEP" \
    --require-gpu \
    --output-jsonl "gpu-prefill-step-${STEP}.jsonl"
done
```

Observed result on `gpt-oss-20b-MXFP4-Q8` at 4096 prompt tokens:

| prefill_step_size | run_ms | prompt_tps | peak_memory_gb |
| --- | ---: | ---: | ---: |
| 512 | 2354.99 | 1811.394 | 12.652 |
| 1024 | 2117.19 | 2025.305 | 12.777 |
| 2048 | 2070.56 | 2082.167 | 13.019 |
| 4096 | 2170.58 | 1976.961 | 13.364 |

For this model, `2048` is the best measured throughput point and `512` is the
lowest-memory point.

Create an engine-consumable profile from the candidate JSONL files:

```bash
python3 benchmarks/python/prefill_profile.py \
  --input-jsonl gpu-prefill-step-512.jsonl \
  --input-jsonl gpu-prefill-step-1024.jsonl \
  --input-jsonl gpu-prefill-step-2048.jsonl \
  --input-jsonl gpu-prefill-step-4096.jsonl \
  --output-json gpt-oss-20b-MXFP4-Q8-prefill-profile.json
```
