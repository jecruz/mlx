# M170 Model Quality Comparison

Verdict: `FAIL`

Speed work is blocked unless every compared model keeps the quality gates passing.

## Models

### qwen-a3b

- Model: `/Volumes/StudioStackSSD4TB/Development/LLM/lmstudio/models/unsloth/Qwen3.6-35B-A3B-UD-MLX-4bit`
- Verdict: `PASS`
- Failures: `0`

| Artifact | Verdict | Rows | Failures | Mean Service ms |
| --- | --- | ---: | ---: | ---: |
| `quality-checkpoint-m206-qwen-a3b` | `PASS` | 0 | 0 |  |

### gpt-oss-chat-template-low-reasoning

- Model: `/Volumes/StudioStackSSD4TB/Development/LLM/lmstudio/models/mlx-community/gpt-oss-20b-MXFP4-Q8`
- Verdict: `FAIL`
- Failures: `1`

| Artifact | Verdict | Rows | Failures | Mean Service ms |
| --- | --- | ---: | ---: | ---: |
| `chat-template-quality-low-reasoning-m216-gpt-oss` | `FAIL` | 12 | 4 | 471.351 |

## Failures

- `gpt-oss-chat-template-low-reasoning:chat-template-quality-low-reasoning-m216-gpt-oss: FAIL failures=4`
