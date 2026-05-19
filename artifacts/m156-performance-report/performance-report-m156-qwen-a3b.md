# M156 Performance Report

Verdict: `PASS`

## Current Suite

- M148 live suite: `PASS`
- M148 artifacts: `15`
- M148 failures: `0`

## Prompt Processing

- repeated baseline service ms: `1488.0793748889118`
- repeated best-hit service ms: `214.1152499243617`
- repeated best-hit speedup: `6.949899063306281`
- repeated best-hit prefill tokens: `11`
- resident prompt transport wall ms: `474.661166081205`
- CLI prompt transport wall ms: `6038.545124931261`

## Concurrency

- stress iterations: `12`
- stress rows: `36`
- stress mean service ms: `428.3835810686772`

## Next Recommendation

- Continue with deeper repeated concurrency stress under higher queue depth.
- Optimize first reusable-turn latency and cache-admission thresholds using the current M148/M151 gates as acceptance criteria.
