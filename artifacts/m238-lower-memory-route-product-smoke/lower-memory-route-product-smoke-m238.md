# M238 Lower-Memory Route Product Smoke

M238 is complete. Product-mode metadata and live request metadata both route
lower-memory work to `agent-workspace-low-memory`.

## Runtime

- model:
  `/Volumes/StudioStackSSD4TB/Development/LLM/lmstudio/models/lmstudio-community/Qwen2.5-Coder-14B-Instruct-MLX-4bit`
- server: fresh updated-code resident process on `127.0.0.1:8779`
- temporary server stopped after smoke

## Static Product Metadata

Artifact: `product-mode-metadata-probe-m238.json`

- verdict: `PASS`
- cases: `7`
- failures: `0`

The probe validates product-mode request metadata for:

- chat
- coding-agent
- coding-agent with 32 GB memory class
- coding-agent-first-hit
- coding-agent-low-memory
- diagnostics
- manual override

## Live Request Metadata

Artifact: `live-request-profile-metadata-m238.json`

- verdict: `PASS`
- rows: `3`
- failures: `0`

Observed live routes:

| Case | Expected | Observed | Source | Applied | Service |
| --- | --- | --- | --- | --- | ---: |
| completion first-hit | `agent-workspace-first-hit` | `agent-workspace-first-hit` | `request_metadata` | `true` | `1415.660 ms` |
| chat coding-agent low-memory | `agent-workspace-low-memory` | `agent-workspace-low-memory` | `request_metadata` | `true` | `243.735 ms` |
| manual override | `interactive` | `interactive` | `request_metadata` | `true` | `183.407 ms` |

## Current Gates

The smoke is accepted against current green gates:

- M231 model-swap decision: `ACCEPT`
- M231 quality threshold: `PASS`
- M233 memory guard: `PASS`
- M234 lower-memory routing policy: `PASS`
- M237 bounded first-hit live revalidation: `PASS`

## Conclusion

M238 proves the product-facing metadata path can select the lower-memory route
live, while preserving manual override and first-hit intent behavior.
