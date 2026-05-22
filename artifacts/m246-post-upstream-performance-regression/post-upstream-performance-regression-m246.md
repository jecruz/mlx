# M246 Post-Upstream Performance Regression Comparison

Status: PASS_WITH_WARNINGS

## Acceptance

Rerun Qwen2.5 first-hit and low-memory live benchmarks after upstream intake and
compare against M237/M241 baselines.

## Live Server

- Model:
  `/Volumes/StudioStackSSD4TB/Development/LLM/lmstudio/models/lmstudio-community/Qwen2.5-Coder-14B-Instruct-MLX-4bit`
- Server: `http://127.0.0.1:8779`
- Device: `Device(gpu, 0)`
- Engine preset: `async-experimental`
- Cleanup: temporary server stopped after validation

## First-Hit Profile

Command:

```bash
python3 benchmarks/python/dax_repeated_context_bench.py \
  --base-url http://127.0.0.1:8779 \
  --client-mode resident \
  --dax-profile agent-workspace-first-hit \
  --output-jsonl artifacts/m246-post-upstream-performance-regression/dax-first-hit-m246-qwen25-coder-14b.jsonl \
  --output-json artifacts/m246-post-upstream-performance-regression/dax-first-hit-m246-qwen25-coder-14b.json \
  --turns 6 \
  --shared-repeats 64 \
  --max-tokens 4 \
  --max-hit-prefill-tokens 16 \
  --min-speedup 5 \
  --fail-on-fail
```

Result:

- verdict: `PASS`
- baseline service: `4846.586 ms`
- first duplicate service: `265.968 ms`
- first duplicate prefill: `11` tokens
- best hit service: `183.477 ms`
- best-hit speedup: `26.415x`
- hit count: `5`

Comparison to M237:

- M237 first duplicate service: `186.185 ms`
- M246 first duplicate service: `265.968 ms`
- delta: `+79.782 ms` / `+42.851%`
- M237 best hit service: `183.017 ms`
- M246 best hit service: `183.477 ms`
- delta: `+0.460 ms` / `+0.251%`
- M237 speedup: `23.552x`
- M246 speedup: `26.415x`
- delta: `+12.154%`

First-hit conversion gate:

- artifact:
  `dax-first-hit-conversion-gate-m246-qwen25-coder-14b.json`
- verdict: `PASS`
- conversion prefill: `11` tokens
- conversion service ratio: `0.055`
- mature-hit speedup: `18.222x`

## Low-Memory Profile

Command:

```bash
python3 benchmarks/python/dax_repeated_context_bench.py \
  --base-url http://127.0.0.1:8779 \
  --client-mode resident \
  --dax-profile agent-workspace-low-memory \
  --output-jsonl artifacts/m246-post-upstream-performance-regression/dax-low-memory-m246-qwen25-coder-14b.jsonl \
  --output-json artifacts/m246-post-upstream-performance-regression/dax-low-memory-m246-qwen25-coder-14b.json \
  --turns 6 \
  --shared-repeats 64 \
  --max-tokens 4 \
  --max-hit-prefill-tokens 32 \
  --min-speedup 2 \
  --fail-on-fail
```

Result:

- verdict: `PASS`
- baseline service: `3493.725 ms`
- first duplicate service: `186.652 ms`
- first duplicate prefill: `11` tokens
- best hit service: `182.699 ms`
- best-hit speedup: `19.123x`
- hit count: `5`

Comparison to M241:

- M241 first duplicate service: `187.867 ms`
- M246 first duplicate service: `186.652 ms`
- delta: `-1.214 ms` / `-0.646%`
- M241 best hit service: `185.230 ms`
- M246 best hit service: `182.699 ms`
- delta: `-2.531 ms` / `-1.366%`
- M241 speedup: `24.648x`
- M246 speedup: `19.123x`
- delta: `-22.415%`

Low-memory gates:

- runtime gate verdict: `PASS`
- conversion gate verdict: `PASS`
- max active memory: `9.669 GB`
- max peak memory: `11.048 GB`
- cache limit: `64 MB`
- conversion prefill: `11` tokens

## Warnings

- First-hit first duplicate service regressed by more than 20%.
- First-hit first duplicate service exceeded the prior `250 ms` promotion budget.

The first-hit profile still passes the existing benchmark and conversion gates
because best-hit latency and mature speedup remain healthy. The first duplicate
regression is still real and should be addressed next because the first
duplicate is the user-visible second-turn case.

## Conclusion

M246 completes the post-upstream comparison. Low-memory remains healthy. The
first-hit path needs a follow-up milestone focused on restoring first duplicate
latency under the promotion budget.
