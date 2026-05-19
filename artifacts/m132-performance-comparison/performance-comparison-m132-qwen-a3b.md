# M132 Performance Comparison

This report compares the initial cold `gpt-oss-20b-MXFP4-Q8` prompt sweep, the warmed resident baseline, and the current Qwen A3B resident product artifacts.

## Initial To Warmed GPT-OSS

| Prompt tokens | Initial ms | Warmed ms | Latency speedup | Initial tok/s | Warmed tok/s | Tok/s ratio |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 8 | 2872.15 | 145.34 | 19.76x | 2.89 | 202.38 | 70.03x |
| 16 | 2164.04 | 147.08 | 14.71x | 7.74 | 319.82 | 41.32x |
| 32 | 460.71 | 167.81 | 2.75x | 88.67 | 434.94 | 4.91x |
| 64 | 420.38 | 195.79 | 2.15x | 198.98 | 654.57 | 3.29x |

## Current Qwen A3B Resident Prompt Transport

| Target tokens | Actual prefill | Service ms | Wall ms | Prompt tok/s | Peak memory GB |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 512 | 657 | 462.44 | 465.31 | 1908.79 | 22.73 |
| 1024 | 1333 | 722.78 | 729.72 | 2229.86 | 22.73 |
| 2048 | 2659 | 1632.97 | 1641.79 | 2240.92 | 23.35 |
| 4096 | 5311 | 3021.70 | 3033.64 | 2288.93 | 23.90 |

## Repeated Context Product Path

- m121: verdict `PASS`
- m121: baseline service `1493.63 ms`, best hit `208.42 ms`, speedup `7.17x`
- m121: baseline prefill `2082`, best-hit prefill `11`
- m124: verdict `PASS`
- m124: baseline service `1516.32 ms`, best hit `209.12 ms`, speedup `7.25x`
- m124: baseline prefill `2082`, best-hit prefill `11`

## Request Metadata Smoke

- verdict: `PASS`
- runtime profile: `agent-workspace-async`
- source: `request_metadata`

## Conclusion

- The initial short-prompt bottleneck was primarily cold-start and one-shot measurement noise; warmed resident serving improved short-prompt latency by up to roughly 20x.
- Current long-prompt Qwen A3B resident prefill remains in the same 1.8k-2.1k token/s class for the measured 512-4096 token prompts.
- Product-path wins now come mainly from repeated-context cache reuse and request-scoped routing rather than another raw prefill micro-optimization.
