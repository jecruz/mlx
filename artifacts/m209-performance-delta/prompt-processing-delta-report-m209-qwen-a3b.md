# M209 Prompt Processing Delta Report

Verdict: `PASS`
Readiness: `prompt-processing-delta-reported`

## Repeated Context

- baseline service request: `1411.08045889996` -> `3267.741832882166` ms
- best-hit service request: `204.03116615489125` -> `206.4703330397606` ms
- best-hit service delta: `2.439` ms
- speedup: `6.91600447859388` -> `15.826689407494138` x

## Operator Overhead

- mean overhead: `4.099721942717831` -> `4.1426667012274265` ms
- p95 overhead: `4.481458105146885` -> `4.81424992904067` ms

## M194 Target

- M194 mature-hit latency: `204.03116615489125` ms
- M206 mature-hit latency: `206.4703330397606` ms
- target mature-hit latency: `175.0` ms
- target gap: `31.47` ms

## Quality

- quality threshold: `PASS`
- live suite: `PASS`

## Warnings

- `current mature-hit latency is 206.470ms; target is 175.000ms`
- `mature repeated-context latency regressed by 2.439ms vs M180`

## Failures

- none
