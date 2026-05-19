# M176 Model Swap Acceptance Gate

Verdict: `PASS`
Swap decision: `REJECT`

## Models

- Current: `qwen35b-a3b-ud-4bit`
- Candidate: `qwen27b-ud-4bit`
- Current mean quality gate ms: `338.812`
- Candidate mean quality gate ms: `3377.609`
- Candidate slowdown ratio: `9.968977`

## Checks

| Check | Verdict | Detail |
| --- | --- | --- |
| `model_comparison` | `PASS` | `verdict='PASS'` |
| `quality_threshold` | `PASS` | `verdict='PASS'` |
| `current_quality` | `PASS` | `verdict='PASS'` |
| `candidate_quality` | `PASS` | `verdict='PASS'` |
| `candidate_speed` | `FAIL` | `slowdown_ratio=9.968977, threshold=1.0` |

## Blockers

- `candidate_speed: slowdown_ratio=9.968977, threshold=1.0`
