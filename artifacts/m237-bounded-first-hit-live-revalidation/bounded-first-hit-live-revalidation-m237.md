# M237 Bounded First-Hit Live Revalidation

M237 is complete. The bounded `agent-workspace-first-hit` profile was revalidated
live with the Qwen2.5 Coder 14B MLX model after M233 added cache bounds.

## Runtime

- model:
  `/Volumes/StudioStackSSD4TB/Development/LLM/lmstudio/models/lmstudio-community/Qwen2.5-Coder-14B-Instruct-MLX-4bit`
- server: fresh updated-code resident process on `127.0.0.1:8779`
- profile: `agent-workspace-first-hit`
- profile policy: `8` max entries, `128 MB` memory limit, `5` min entries

The temporary server was stopped after the benchmark.

## Validation

Benchmark:

- artifact: `dax-bounded-first-hit-m237-qwen25-coder-14b.json`
- verdict: `PASS`
- hit count: `5`
- best hit speedup vs baseline: `23.552x`
- best hit service: `183.017 ms`

Conversion gate:

- artifact: `dax-first-hit-conversion-gate-m237-qwen25-coder-14b.json`
- verdict: `PASS`
- checks: `6`
- failures: `0`

## Performance

| Metric | M230 Promotion | M237 Bounded Live |
| --- | ---: | ---: |
| baseline service | `4527.224 ms` | `4310.493 ms` |
| first duplicate service | `193.098 ms` | `186.185 ms` |
| best hit service | `193.098 ms` | `183.017 ms` |
| first duplicate prefill | `11` | `11` |
| conversion ratio | `0.043` | `0.043` |
| mature speedup | `23.445x` | `23.152x` |

The bounded profile remains inside the M230 promotion budget:

- first duplicate service <= `250 ms`
- first duplicate prefill <= `16` tokens
- conversion ratio <= `0.05`
- mature speedup >= `5x`

## Conclusion

M237 proves the M233 memory bounds did not break the first-hit latency win. The
bounded first-hit route still converts the first duplicate request immediately
with 11 prefill tokens and sub-200 ms service time.
