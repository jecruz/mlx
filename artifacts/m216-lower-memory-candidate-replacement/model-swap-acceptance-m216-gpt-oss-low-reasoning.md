# M176 Model Swap Acceptance Gate

Verdict: `PASS`
Swap decision: `REJECT`

## Models

- Current: `qwen-a3b`
- Candidate: `gpt-oss-chat-template-low-reasoning`
- Current mean quality gate ms: `None`
- Candidate mean quality gate ms: `471.351`
- Candidate slowdown ratio: `None`

## Checks

| Check | Verdict | Detail |
| --- | --- | --- |
| `model_comparison` | `FAIL` | `verdict='FAIL'` |
| `quality_threshold` | `FAIL` | `verdict='FAIL'` |
| `current_quality` | `PASS` | `verdict='PASS'` |
| `candidate_quality` | `FAIL` | `verdict='FAIL'` |
| `candidate_speed` | `FAIL` | `missing comparable quality gate latency` |

## Blockers

- `model_comparison: verdict='FAIL'`
- `quality_threshold: verdict='FAIL'`
- `candidate_quality: verdict='FAIL'`
- `candidate_speed: missing comparable quality gate latency`
