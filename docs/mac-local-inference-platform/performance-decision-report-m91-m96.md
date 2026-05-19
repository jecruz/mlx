# Performance Decision Report: M91-M96

Date: 2026-05-18

Model:

- `/Volumes/StudioStackSSD4TB/Development/LLM/lmstudio/models/unsloth/Qwen3.6-35B-A3B-UD-MLX-4bit`

Resident endpoint:

- `http://127.0.0.1:8773`

## Executive Decision

The engine now has three distinct product routing modes for repeated
coding-agent context:

1. `agent-workspace-async`
   - Use when the product optimizes for steady-state repeated-context reuse.
   - Best for coding sessions where the same large workspace context repeats
     across many turns.
   - Mature-hit evidence remains the strongest latency path.

2. `agent-workspace-first-hit`
   - Use when the product optimizes for immediate second-turn latency.
   - Converts the first duplicate repeated-context turn instead of waiting for
     the third turn to benefit from a mature async cache.
   - Backed by request-derived cache behavior.

3. `agent-workspace-low-memory`
   - Use on smaller-memory Macs or when predictable bounded cache use matters
     more than maximum cache residency.
   - Uses request-derived behavior with a smaller bounded cache:
     `4` entries, `64 MB` cache memory limit, minimum `1` retained entry.

## Why This Changed

M91 showed that existing async/profile selection did not solve the first-hit
problem. The second repeated-context turn still performed full `2092` token
prefill before later turns could reuse the cache.

M92-M95 converted that finding into product controls:

- a named first-hit runtime profile
- a dedicated first-hit conversion gate
- a product-path first-hit regression gate
- resident suite integration for first-hit validation
- a lower-memory product profile and compatible validation path

## Evidence Summary

| Milestone | Verdict | Key Result |
| --- | --- | --- |
| M89 | PASS | Mature product-path reuse: `19.20x`, `2092 -> 18` prefill tokens |
| M90 | PASS | First-hit latency became separately gateable |
| M91 | PASS / target FAIL | Existing profiles did not convert the scheduled pre-hit turn |
| M92 | PASS | First duplicate turn converted to `18` actual prefill tokens |
| M93 | PASS | Product-path first-hit conversion gate passed |
| M94 | PASS | Resident suite can include first-hit product validation |
| M95 | PASS | Lower-memory profile path validated with bounded conversion |

## Detailed Metrics

### Mature Steady-State Reuse

Source:

- `artifacts/m89-dax-operator-product-run/dax-repeated-context-m89-qwen-a3b-dax-product.json`

Result:

- verdict: `PASS`
- cache-hit turns: `2`
- baseline service: `4362.02 ms`
- best-hit service: `227.23 ms`
- speedup: `19.20x`
- baseline prefill: `2092` tokens
- best-hit prefill: `18` tokens

Decision:

- This is the strongest steady-state path.
- It should remain the default for long-running coding-agent sessions.

### Existing Profile Sweep

Source:

- `artifacts/m91-first-hit-scheduling-sweep/dax-first-hit-scheduling-sweep-m91-qwen-a3b.json`

Result:

- sweep verdict: `PASS`
- target verdict: `FAIL`
- best observed variant: `agent-workspace`
- scheduled pre-hit service: `1375.97 ms`
- scheduled pre-hit ratio vs baseline: `0.971`
- scheduled pre-hit prefill: `2092` tokens

Decision:

- Existing async profile selection was not enough.
- The product needed an explicit first-hit conversion profile instead of only
  tuning async scheduling.

### First-Hit Conversion

Source:

- `artifacts/m92-first-hit-conversion/dax-first-hit-conversion-gate-m92-request-probe.json`

Result:

- verdict: `PASS`
- conversion turn: `2`
- conversion service: `1153.85 ms`
- conversion ratio vs baseline: `0.813`
- conversion prefill: `18` tokens
- mature hit service: `483.43 ms`
- mature hit speedup: `2.94x`
- mature hit prefill: `18` tokens

Decision:

- First-hit conversion is worthwhile when second-turn latency matters.
- It is not as fast as mature async reuse, but it prevents the second turn from
  doing full foreground prefill.

### Product-Path First-Hit Gate

Source:

- `artifacts/m93-product-first-hit-gate/dax-product-first-hit-summary-m93-qwen-a3b-request-profile.json`

Result:

- verdict: `PASS`
- profile used: `agent-workspace-request`
- conversion turn: `2`
- conversion service: `1168.87 ms`
- conversion ratio vs baseline: `0.843`
- conversion prefill: `18` tokens
- mature hit service: `462.64 ms`
- mature hit speedup: `3.00x`

Decision:

- Product-path validation can now catch the exact M91 failure mode.
- The gate should run before changing product profile defaults.

### Resident Suite First-Hit Integration

Source:

- `artifacts/m94-suite-first-hit-product/resident-regression-suite-m94-qwen-a3b-first-hit-product.json`

Result:

- suite verdict: `PASS`
- `dax_first_hit`: `PASS`
- profile used: `agent-workspace-request`
- conversion turn: `2`
- conversion ratio vs baseline: `0.837`
- conversion prefill: `18` tokens
- mature hit speedup: `3.052x`

Decision:

- First-hit validation is now part of the suite manifest and evidence package
  path.
- Product/tooling can consume a single manifest instead of ad hoc scripts.

### Lower-Memory Product Mode

Source:

- `artifacts/m95-lower-memory-product-profile/dax-product-first-hit-summary-m95-qwen-a3b-memory-saver.json`

Result:

- verdict: `PASS`
- compatibility profile used: `memory-saver`
- conversion turn: `2`
- baseline service: `2076.11 ms`
- conversion service: `1220.90 ms`
- conversion ratio vs baseline: `0.588`
- conversion prefill: `18` tokens
- mature hit service: `579.78 ms`
- mature hit speedup: `3.581x`
- mature hit prefill: `18` tokens

Decision:

- Lower-memory behavior can avoid full second-turn prefill.
- Use `agent-workspace-low-memory` for product routing after the resident
  server is restarted with the new profile catalog.

## Product Defaults

Recommended default routing:

| Product Scenario | Runtime Profile | Reason |
| --- | --- | --- |
| Interactive chat | `interactive` | Avoid waits and foreground cache work |
| Coding agent, repeated workspace, long session | `agent-workspace-async` | Best mature-cache latency |
| Coding agent, immediate second-turn responsiveness | `agent-workspace-first-hit` | Converts turn 2 instead of waiting for turn 3 |
| Smaller-memory Mac | `agent-workspace-low-memory` | Bounded cache residency |
| Diagnostics/readiness | `diagnostics` | Stable sync-safe behavior |

## Follow-Up Work

1. Restart the resident server on the new code and rerun M93/M94 using
   `agent-workspace-first-hit` instead of the compatibility
   `agent-workspace-request` profile.
2. Rerun M95 using `agent-workspace-low-memory` instead of compatibility
   `memory-saver`.
3. Wire Dax product UI or command presets to expose:
   - steady-state async
   - first-hit conversion
   - lower-memory mode
4. Compare end-to-end operator wall time, not just service latency, because Dax
   process startup and CLI overhead are visible in the row logs.
5. Keep async scheduling research open, but treat it as secondary to product
   routing because request-derived first-hit conversion already resolves the
   immediate second-turn full-prefill failure mode.
