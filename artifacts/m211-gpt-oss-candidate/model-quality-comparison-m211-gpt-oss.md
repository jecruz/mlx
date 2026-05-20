# M170 Model Quality Comparison

Verdict: `FAIL`

Speed work is blocked unless every compared model keeps the quality gates passing.

## Models

### qwen35b-a3b-ud-4bit

- Model: `/Volumes/StudioStackSSD4TB/Development/LLM/lmstudio/models/unsloth/Qwen3.6-35B-A3B-UD-MLX-4bit`
- Verdict: `PASS`
- Failures: `0`

| Artifact | Verdict | Rows | Failures | Mean Service ms |
| --- | --- | ---: | ---: | ---: |
| `deterministic-quality-m206-qwen-a3b` | `PASS` | 12 | 0 | 245.595 |

### gpt-oss-20b-mxfp4-q8

- Model: `/Volumes/StudioStackSSD4TB/Development/LLM/lmstudio/models/mlx-community/gpt-oss-20b-MXFP4-Q8`
- Verdict: `FAIL`
- Failures: `1`

| Artifact | Verdict | Rows | Failures | Mean Service ms |
| --- | --- | ---: | ---: | ---: |
| `deterministic-quality-m211-gpt-oss` | `FAIL` | 12 | 7 | 541.66 |

## Failures

- `gpt-oss-20b-mxfp4-q8:deterministic-quality-m211-gpt-oss: FAIL failures=7`
