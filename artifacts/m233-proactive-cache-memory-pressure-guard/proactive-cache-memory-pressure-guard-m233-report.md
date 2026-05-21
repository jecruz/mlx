# M233 Proactive Cache Memory-Pressure Guard

M233 is complete. Proactive prefix-cache growth is now bounded for both
`agent-workspace-first-hit` and `agent-workspace-low-memory` while preserving
the M229/M230 first-duplicate latency win.

## Code Change

`agent-workspace-first-hit` now keeps the request-derived first-hit behavior but
adds explicit prefix-cache bounds:

- `prefix_cache_max_entries`: `8`
- `prefix_cache_memory_limit_mb`: `128.0`
- `prefix_cache_min_entries`: `5`

`agent-workspace-low-memory` remains more aggressive:

- `prefix_cache_max_entries`: `4`
- `prefix_cache_memory_limit_mb`: `64.0`
- `prefix_cache_min_entries`: `1`

The first-hit profile keeps at least 5 entries because M229's successful first
request created 5 proactive prefix caches. Setting the minimum lower than that
would risk preserving the memory cap by destroying the latency win.

## Gate Results

- proactive cache memory-pressure guard verdict: `PASS`
- readiness: `proactive-cache-memory-guard-ready`
- checks: `14`
- failures: `0`

## Performance Preservation

The guard carries forward the M230 promotion metrics:

- first duplicate service: `193.098 ms`
- first duplicate prefill: `11` tokens
- first duplicate cache hit: `true`
- mature-hit speedup: `23.445x`

Observed M229 proactive-cache first request:

- proactive prefixes created: `5`
- trim failures: `0`
- cache memory: about `20.82 MB`

## Conclusion

M233 prevents unbounded proactive-cache growth on the first-hit path without
lowering the cache floor below the number of proactive entries that made the
first duplicate request fast.
