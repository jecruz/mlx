# Lower-Memory Default-Routing Policy

This policy defines when MLX should route local coding-agent work to the
lower-memory profile by default.

## Default To Lower-Memory

Use `agent-workspace-low-memory` when any of these signals are present:

- request has `low_memory=true`
- `memory_class_gb` is `16`, `24`, or `32`
- workload intent is `low-memory`
- workload intent is `coding-agent-low-memory`

## Do Not Default To Lower-Memory

Do not override these higher-priority signals:

- manual profile override
- non-agentic interactive foreground work
- diagnostics workload
- 64 GB or larger agentic work without an explicit low-memory signal
- immediate second-turn work without an explicit low-memory signal

## Current Evidence

The lower-memory route is allowed because the current evidence is green:

- M231 model-swap decision: `ACCEPT`
- M231 quality threshold: `PASS`
- M233 proactive-cache memory guard: `PASS`
- M230 first duplicate service: `193.098 ms`
- M230 first duplicate prefill: `11` tokens
- M230 mature-hit speedup: `23.445x`
- M230 peak memory: `11.048 GB`

## Operator Contract

Product clients should send explicit request metadata instead of inferring from
model name alone:

- `low_memory=true` for operator-selected lower-memory mode
- `memory_class_gb=16`, `24`, or `32` for lower-memory Macs
- `workload_intent=low-memory` for low-memory agentic workloads
- `workload_intent=coding-agent-low-memory` for coding-agent lower-memory mode

Manual profile selection remains authoritative. If the operator chooses
`agent-workspace-first-hit`, `agent-workspace-async`, `interactive`, or
`diagnostics`, auto-selection must not override that choice.
