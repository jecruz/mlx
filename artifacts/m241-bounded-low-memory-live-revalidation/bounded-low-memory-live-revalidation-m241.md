# M241 Bounded Low-Memory Live Revalidation

Status: PASS

## Acceptance

Rerun lower-memory profile live on Qwen2.5 Coder 14B and prove
`agent-workspace-low-memory` remains within cache, memory, and first-hit
quality/performance gates.

## Live Server

- Model:
  `/Volumes/StudioStackSSD4TB/Development/LLM/lmstudio/models/lmstudio-community/Qwen2.5-Coder-14B-Instruct-MLX-4bit`
- Server: `http://127.0.0.1:8779`
- Device: `Device(gpu, 0)`
- Engine preset: `async-experimental`
- Warmup: off
- Cleanup: temporary server stopped after validation

## Performance Gate

Command:

```bash
python3 benchmarks/python/dax_repeated_context_bench.py \
  --base-url http://127.0.0.1:8779 \
  --client-mode resident \
  --dax-profile agent-workspace-low-memory \
  --output-jsonl artifacts/m241-bounded-low-memory-live-revalidation/dax-bounded-low-memory-m241-qwen25-coder-14b.jsonl \
  --output-json artifacts/m241-bounded-low-memory-live-revalidation/dax-bounded-low-memory-m241-qwen25-coder-14b.json \
  --turns 6 \
  --shared-repeats 64 \
  --max-tokens 4 \
  --max-hit-prefill-tokens 32 \
  --min-speedup 2 \
  --fail-on-fail
```

Result:

- verdict: `PASS`
- profile: `agent-workspace-low-memory`
- turns: `6`
- cache hits: `5`
- baseline service: `4565.484 ms`
- first duplicate service: `187.867 ms`
- first duplicate prefill: `11` tokens
- best hit service: `185.230 ms`
- best-hit speedup: `24.648x`

## Runtime Memory Gate

Command:

```bash
python3 benchmarks/python/lower_memory_runtime_gate.py \
  artifacts/m241-bounded-low-memory-live-revalidation/dax-bounded-low-memory-m241-qwen25-coder-14b.jsonl \
  --output-json artifacts/m241-bounded-low-memory-live-revalidation/lower-memory-runtime-gate-m241-qwen25-coder-14b.json \
  --tag m241-bounded-low-memory-live-revalidation \
  --base-url http://127.0.0.1:8779 \
  --max-active-memory-gb 16 \
  --max-peak-memory-gb 16 \
  --max-cache-memory-limit-mb 64 \
  --max-conversion-prefill-tokens 32 \
  --fail-on-fail
```

Result:

- verdict: `PASS`
- rows: `6`
- max active memory: `9.669 GB`
- max peak memory: `9.689 GB`
- max cache memory limit: `64.000 MB`
- conversion prefill: `11` tokens

## First-Hit Conversion Gate

Command:

```bash
python3 benchmarks/python/dax_first_hit_conversion_gate.py \
  artifacts/m241-bounded-low-memory-live-revalidation/dax-bounded-low-memory-m241-qwen25-coder-14b.json \
  --output-json artifacts/m241-bounded-low-memory-live-revalidation/dax-low-memory-first-hit-conversion-gate-m241-qwen25-coder-14b.json \
  --max-conversion-prefill-tokens 32 \
  --max-conversion-ratio 0.08 \
  --conversion-path any \
  --min-mature-hit-speedup 2 \
  --max-mature-hit-prefill-tokens 64 \
  --fail-on-fail
```

Result:

- verdict: `PASS`
- checks: `6`
- failures: `0`
- conversion prefill: `11` tokens
- conversion service ratio vs baseline: `0.041`
- mature-hit speedup: `24.302x`

## Quality Gate

The unadapted deterministic completion gate was intentionally retained as a
negative signal because it fails Qwen2.5 format compliance under this profile:

- artifact:
  `quality-deterministic-m241-qwen25-coder-14b-low-memory.json`
- verdict: `FAIL`
- failures: fenced JSON, missing `SUMMARY_OK`, and patch-plan format/repetition

The model-family-appropriate adapted chat-template quality route passed on the
same `agent-workspace-low-memory` profile.

Commands:

```bash
python3 benchmarks/python/chat_template_quality_probe.py \
  --base-url http://127.0.0.1:8779 \
  --runtime-profile agent-workspace-low-memory \
  --prompt-adapter qwen25-coder-lower-memory \
  --output-json artifacts/m241-bounded-low-memory-live-revalidation/chat-template-quality-adapted-m241-qwen25-coder-14b-low-memory.json \
  --tag m241-qwen25-coder-14b-low-memory-chat-template-adapted \
  --fail-on-fail

python3 benchmarks/python/quality_threshold_gate.py \
  --quality-artifact artifacts/m241-bounded-low-memory-live-revalidation/chat-template-quality-adapted-m241-qwen25-coder-14b-low-memory.json \
  --output-json artifacts/m241-bounded-low-memory-live-revalidation/quality-threshold-gate-m241-qwen25-coder-14b-low-memory.json \
  --tag m241-qwen25-coder-14b-low-memory \
  --fail-on-fail
```

Result:

- adapted chat-template quality verdict: `PASS`
- quality threshold verdict: `PASS`
- readiness: `ci-quality-ready`
- checks: `6`
- failures: `0`
- max repetition score: `0.045455`
- visible thinking count: `0`

## Harness Changes

- `quality_gate_runner.py` now accepts `--runtime-profile` for live completion
  quality gates.
- `chat_template_quality_probe.py` now accepts `--runtime-profile` for live
  chat-template quality probes.

These changes prevent quality probes from silently validating `interactive`
when the milestone under test is `agent-workspace-low-memory`.

## Conclusion

M241 passes with an important quality caveat: the unadapted completion route is
not sufficient for Qwen2.5 Coder low-memory release gating. The adapted
chat-template quality gate is the release-quality path for this model/profile,
and it passes while the profile remains inside memory, cache, and first-hit
performance budgets.
