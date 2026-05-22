# M235 Prowl Lower-Memory Promotion Visibility

M235 is complete. Prowl now surfaces the lower-memory promotion evidence from
the MLX model-swap artifact instead of only showing quality/swap PASS states.

## Prowl Change

Prowl commit: `7eb2f51 Show MLX lower-memory promotion evidence`

Changed files:

- `apps/prowl-macos/Sources/ProwlMac/Features/Engine/MLXOperatorReadinessCard.swift`
- `apps/prowl-macos/Sources/ProwlMac/Features/Settings/SettingsModelSourcesCard.swift`
- `apps/prowl-macos/Tests/ProwlTests/MLXOperatorArtifactClientTests.swift`

## Visible Evidence

Prowl now decodes and displays:

- swap decision
- swap readiness
- candidate model
- candidate runtime profile
- first duplicate service latency
- mature-hit speedup
- max peak memory

The readiness card swap row now includes:

- profile
- first duplicate latency
- mature-hit speedup
- peak memory
- source artifact

The settings model-sources card now includes a promotion summary:

- decision
- profile
- first duplicate latency
- speedup
- peak memory

## Validation

Prowl validation:

- command: `swift test --package-path apps/prowl-macos -c release`
- result: `PASS`
- tests: `16`
- failures: `0`

MLX evidence carried into the UI:

- model-swap decision: `ACCEPT`
- swap readiness: `swap-acceptable`
- candidate profile: `agent-workspace-first-hit`
- first duplicate service: `193.098 ms`
- mature-hit speedup: `23.445x`
- peak memory: `11.048 GB`

## Conclusion

M235 makes the lower-memory promotion state operator-visible in Prowl. The UI can
now show not just that the artifact root is `PASS`, but why the promotion is
acceptable and which profile/performance evidence supports it.
