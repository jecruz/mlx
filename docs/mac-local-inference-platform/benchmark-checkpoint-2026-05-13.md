# MLX Engine Benchmark Checkpoint - 2026-05-13

## Scope

This checkpoint summarizes the measured differences from the initial
`gpt-oss-20b-MXFP4-Q8` prompt-processing benchmarks to the current resident MLX
engine work.

Model:

```text
/Volumes/StudioStackSSD4TB/Development/LLM/lmstudio/models/mlx-community/gpt-oss-20b-MXFP4-Q8
```

Worktree:

```text
/Users/jeffreycruz/Development/LLM_INFERENCE/mlx/.worktrees/prompt-processing-bench
```

## Initial Cold Prompt Tests

The first one-shot GPU prompt sweep included cold load, compile, and
measurement-shape noise.

Artifact:

```text
gpu-prompt-sweep.jsonl
```

| Prompt tokens | Initial run ms | Initial prompt tok/s | Load ms |
| ---: | ---: | ---: | ---: |
| 8 | 2872.15 | 2.89 | 3376.49 |
| 16 | 2164.04 | 7.74 | 3415.11 |
| 32 | 460.71 | 88.67 | 1601.93 |
| 64 | 420.38 | 198.98 | 1516.14 |

## Warmed Resident Baseline

Once the model stayed loaded and the prompt shapes were warmed, prompt
processing was materially faster.

Artifact:

```text
gpu-prompt-sweep-steady.jsonl
```

| Prompt tokens | Warmed run ms | Warmed prompt tok/s | Runtime improvement vs initial |
| ---: | ---: | ---: | ---: |
| 8 | 145.34 | 202.38 | 19.8x |
| 16 | 147.08 | 319.82 | 14.7x |
| 32 | 167.81 | 434.94 | 2.7x |
| 64 | 195.79 | 654.57 | 2.1x |

Conclusion:

- The early "prompt processing is slow" result was mostly cold-start and
  measurement-shape noise.
- Resident serving and warm-up are the first required performance baseline.

## Long Prompt Warmed Baseline

Artifact:

```text
gpu-prompt-sweep-long.jsonl
```

| Prompt tokens | Run ms | Prompt tok/s |
| ---: | ---: | ---: |
| 512 | 386.14 | 1822.94 |
| 1024 | 703.46 | 1691.95 |
| 2048 | 1069.81 | 2114.49 |
| 4096 | 2158.82 | 1988.47 |

Conclusion:

- Warmed MLX prompt processing sustains roughly `1.7k-2.1k tok/s` in these
  measured prompt shapes.
- The next large gains come from avoiding repeated prefill, not only from raw
  kernel speed.

## Sync Prefix Cache Impact

Artifact:

```text
prefix-latency-sweep.jsonl
```

Approximate prompt shape: `930` tokens with repeated coding-agent context.

| Phase | Service ms | Actual prefill tokens |
| --- | ---: | ---: |
| Full prefill | 600.18 | 930.67 |
| Cache create | 631.11 | 10.00 |
| Cache hit | 183.63 | 9.50 |

Cache-hit speedup:

```text
600.18 / 183.63 = 3.27x
```

Conclusion:

- Real prefix-cache hits reduce repeated-prefix request time from about
  `600 ms` to about `184 ms`.
- Cache creation is not a latency win for the creating request because it pays
  the cache-build cost.

## Larger Context Prefix Cache Wins

Artifacts:

```text
prefix-latency-sweep-2k.jsonl
prefix-latency-sweep-4k.jsonl
prefix-latency-sweep-8k.jsonl
```

| Shape | Full prefill ms | Cache-hit ms | Speedup |
| --- | ---: | ---: | ---: |
| ~2k tokens | 2783.02 | 186.41 | 14.9x |
| ~4k tokens | 2021.29 | 248.66 | 8.1x |
| ~7.4k tokens | 3718.98 | 211.40 | 17.6x |

Conclusion:

- Prefix reuse matters most for local agentic coding workloads where system
  prompts, tool schemas, repo instructions, and active task context are
  repeatedly sent.
- Larger repeated contexts produce the biggest practical win.

## Eviction And Memory Policy

Artifact:

```text
prefix-latency-sweep-eviction.jsonl
```

| Phase | Service ms | Actual prefill tokens |
| --- | ---: | ---: |
| Full prefill | 659.16 | 929.25 |
| Cache create | 597.75 | 10.00 |
| Cache hit | 157.83 | 11.00 |

Validated:

- Prefix cache entry cap.
- Eviction counters.
- MLX memory telemetry.
- Memory-pressure pruning.
- Manual prune endpoint.

Forced memory-pressure evidence:

```text
memory_probe 2 65 True False True True 1 236.11
memory_after_requests entries=0 evictions=1 prunes=1
MLX cache memory: 3577334 bytes -> 0 bytes
```

## Async Prefix Cache Findings

Artifact:

```text
prefix-latency-sweep-async-idle.jsonl
```

Queue-aware async mode:

| Phase | Service ms | Cache prepare ms | Actual prefill tokens |
| --- | ---: | ---: | ---: |
| Full prefill | 866.20 | 0.04 | 931.33 |
| Cache scheduled | 601.03 | 0.09 | 931.33 |
| Cache hit | 184.55 | 0.17 | 9.00 |

Async health:

```text
started=3 completed=3 failed=0 skipped=0
```

Conclusion:

- Async mode removes synchronous cache-build preparation from the scheduling
  request.
- Later cache hits remain fast.
- Async is still not ready as the default because a background builder can race
  with foreground inference after the scheduler becomes idle.
- Current decision: keep `sync` as the default and keep `async` opt-in until a
  foreground-priority lock or idle-grace/debounce policy is implemented.

## Overall Delta

We moved from:

- one-shot cold prompt runs as low as `2.89 tok/s` at 8 tokens,
- to warmed resident prefill around `1.7k-2.1k tok/s`,
- to repeated-prefix cache hits reducing ~930-token repeated prompts from
  about `600 ms` to about `184 ms`,
- to larger repeated prompts dropping from multi-second full-prefill latency to
  about `186-249 ms` cache-hit latency.

The largest validated gains so far come from:

1. Keeping the model resident.
2. Warming representative prompt shapes.
3. Choosing measured prefill policy.
4. Reusing repeated prefix KV state.
5. Bounding and pruning prefix-cache memory.

The next milestone should be foreground-priority background cache building, then
a decision on whether async population can become the default.
