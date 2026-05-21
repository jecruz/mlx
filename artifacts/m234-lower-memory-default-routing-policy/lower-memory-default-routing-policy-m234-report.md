# M234 Lower-Memory Default-Routing Policy

M234 is complete. The default-routing policy for lower-memory Macs is refreshed
against current M231/M233 evidence and documented for product clients.

## Artifacts

- `profile-auto-selection-runtime-gate-m234.json`
- `lower-memory-default-routing-policy-gate-m234.json`
- `lower-memory-default-routing-policy-gate-m234.md`

## Policy

Default to `agent-workspace-low-memory` when:

- `low_memory=true`
- `memory_class_gb` is `16`, `24`, or `32`
- workload intent is `low-memory`
- workload intent is `coding-agent-low-memory`

Do not default to lower-memory when:

- a manual profile override is present
- the workload is non-agentic interactive foreground work
- diagnostics is requested
- 64 GB or larger agentic work has no low-memory signal
- immediate second-turn work has no low-memory signal

## Gate Results

- auto-selection runtime gate: `PASS`
- lower-memory default-routing policy gate: `PASS`
- policy checks: `12`
- failures: `0`

## Performance And Quality Evidence

The policy is permitted because:

- M231 model-swap decision is `ACCEPT`
- M231 quality threshold is `PASS`
- M233 proactive-cache memory guard is `PASS`
- M230 first duplicate service is `193.098 ms`
- M230 first duplicate prefill is `11` tokens
- M230 first duplicate cache hit is `true`
- M230 mature-hit speedup is `23.445x`

## Conclusion

M234 makes lower-memory default routing explicit: it is default only for
lower-memory signals and smaller memory classes, while manual overrides,
interactive work, diagnostics, 64 GB+ steady-state agentic work, and immediate
second-turn work keep their more specific routes.
