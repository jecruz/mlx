# M176 Model Swap Acceptance Gate

Verdict: `PASS`
Swap decision: `REJECT`

## Models

- Current: `qwen35b-a3b-ud-4bit`
- Candidate: `gpt-oss-20b-mxfp4-q8`
- Current mean quality gate ms: `245.595`
- Candidate mean quality gate ms: `541.66`
- Candidate slowdown ratio: `2.205501`

## Checks

| Check | Verdict | Detail |
| --- | --- | --- |
| `model_comparison` | `FAIL` | `verdict='FAIL'` |
| `quality_threshold` | `PASS` | `verdict='PASS'` |
| `current_quality` | `PASS` | `verdict='PASS'` |
| `candidate_quality` | `FAIL` | `verdict='FAIL'` |
| `candidate_speed` | `FAIL` | `slowdown_ratio=2.205501, threshold=1.0` |

## Blockers

- `model_comparison: verdict='FAIL'`
- `candidate_quality: verdict='FAIL'`
- `candidate_speed: slowdown_ratio=2.205501, threshold=1.0`
