# M170 Model Quality Comparison

Verdict: `PASS`

Speed work is blocked unless every compared model keeps the quality gates passing.

## Models

### qwen35b-a3b-ud-4bit

- Model: `/Volumes/StudioStackSSD4TB/Development/LLM/lmstudio/models/unsloth/Qwen3.6-35B-A3B-UD-MLX-4bit`
- Verdict: `PASS`
- Failures: `0`

| Artifact | Verdict | Rows | Failures | Mean Service ms |
| --- | --- | ---: | ---: | ---: |
| `cache-quality-m170-current-a3b` | `PASS` | 3 | 0 | 314.334 |
| `deterministic-quality-m170-current-a3b` | `PASS` | 8 | 0 | 283.354 |
| `long-context-quality-m170-current-a3b` | `PASS` | 1 | 0 | 481.828 |
| `loop-quality-m170-current-a3b` | `PASS` | 9 | 0 | 275.734 |

### qwen27b-ud-4bit

- Model: `/Volumes/StudioStackSSD4TB/Development/LLM/lmstudio/models/unsloth/Qwen3.6-27B-UD-MLX-4bit`
- Verdict: `PASS`
- Failures: `0`

| Artifact | Verdict | Rows | Failures | Mean Service ms |
| --- | --- | ---: | ---: | ---: |
| `cache-quality-m170-qwen27b-ud-4bit` | `PASS` | 3 | 0 | 2691.897 |
| `deterministic-quality-m170-qwen27b-ud-4bit` | `PASS` | 8 | 0 | 649.049 |
| `long-context-quality-m170-qwen27b-ud-4bit` | `PASS` | 1 | 0 | 6792.323 |
| `loop-quality-m170-qwen27b-ud-4bit` | `PASS` | 9 | 0 | 3377.165 |

## Failures

- none
