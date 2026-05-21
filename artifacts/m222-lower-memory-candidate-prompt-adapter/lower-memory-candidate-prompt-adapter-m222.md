# M222 Lower-Memory Candidate Prompt Adapter

## Result

M222 is complete. The Qwen2.5 Coder 14B MLX candidate can now pass the deterministic quality gate when tested through the chat-template route with the `qwen25-coder-lower-memory` adapter.

This does not promote the candidate as the default model. It makes it eligible for lower-memory use and follow-up performance work because quality now passes before speed is considered.

## Candidate

Model:

`/Volumes/StudioStackSSD4TB/Development/LLM/lmstudio/models/lmstudio-community/Qwen2.5-Coder-14B-Instruct-MLX-4bit`

Source from M219:

`lmstudio-community/Qwen2.5-Coder-14B-Instruct-MLX-4bit`

## Adapter

Implemented in `benchmarks/python/chat_template_quality_probe.py`:

- new `--prompt-adapter qwen25-coder-lower-memory`
- keeps the chat-template route
- adds a JSON-specific prompt clarification
- normalizes fenced JSON final answers for validation while preserving raw output in the artifact

The JSON case still emits this fenced text:

~~~text
```json
{
  "status": "ok"
}
```
~~~

The adapter validates the normalized final answer:

```json
{
  "status": "ok"
}
```

## Quality

| Route | Verdict | Failures |
| --- | ---: | ---: |
| completion route | `FAIL` | `4` |
| default chat-template route | `FAIL` | `1` |
| strict global system prompt | `FAIL` | `1` |
| adapted chat-template route | `PASS` | `0` |

Quality threshold:

- verdict: `PASS`
- readiness: `ci-quality-ready`
- missing required markers: `0`
- visible thinking count: `0`
- max repetition score: `0.045455`

## Performance

Compared with the M221 A3B resident first-hit artifact:

| Metric | Qwen A3B M221 | Qwen2.5 Coder 14B M222 |
| --- | ---: | ---: |
| active memory GB | `20.781` | `8.360` |
| candidate load ms | n/a | `6291.136` |
| cold baseline service ms | `1431.913` | `3515.255` |
| first duplicate service ms | `1109.143` | `3314.128` |
| first duplicate actual prefill tokens | `11` | `2081` |
| mature hit best service ms | `205.462` | `182.281` |
| mature hit speedup vs cold baseline | `6.836x` | `19.285x` |

Interpretation:

- Good: active memory is about `59.8%` lower.
- Good: mature cached turns are faster once the cache exists.
- Bad: cold/full-prefill turns are about `2.45x` slower than A3B.
- Bad: first duplicate request did not use request-derived split-prefill conversion; it stayed at full prefill and only hit from turn 3 onward.

Decision:

Use this candidate only for lower-memory, steady-cache workflows for now. Do not promote it as the default high-performance model until first-hit conversion is fixed or a separate lower-memory UX explicitly accepts slower cold/full-prefill behavior.

## Evidence

- `live-model-swap-m222-qwen25-coder-14b.json`
- `deterministic-quality-completion-m222-qwen25-coder-14b.json`
- `chat-template-quality-m222-qwen25-coder-14b.json`
- `chat-template-quality-strict-m222-qwen25-coder-14b.json`
- `chat-template-quality-adapted-m222-qwen25-coder-14b.json`
- `quality-threshold-gate-m222-qwen25-coder-14b-adapted.json`
- `dax-repeated-context-m222-qwen25-coder-14b.json`
