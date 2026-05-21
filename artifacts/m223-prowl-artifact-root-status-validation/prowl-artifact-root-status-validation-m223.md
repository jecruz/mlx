# M223 Prowl Artifact-Root Status Validation

## Result

M223 is complete. Prowl now validates the configured MLX artifact root and reports explicit artifact status instead of collapsing every failure into `Artifact unavailable`.

Prowl commit:

`d06f1e0 feat(macos): validate MLX artifact root status`

## Product Behavior

Prowl now reports:

- `PASS` when the artifact root exists and latest quality/model-swap artifacts are current
- `MISSING` when the configured root or required artifact family is absent
- `STALE` when an artifact family exists but is older than the latest detected MLX milestone artifact
- `INVALID` when an artifact exists but cannot be decoded

Surfaces updated:

- MLX Operator Readiness card now includes artifact root status, quality artifact source, model-swap artifact source, and artifact issues.
- Settings > Model Sources now shows the configured MLX artifact root status immediately below the root picker.

## Implementation

Prowl files changed:

- `apps/prowl-macos/Sources/ProwlMac/Features/Engine/MLXOperatorReadinessCard.swift`
- `apps/prowl-macos/Sources/ProwlMac/Features/Settings/SettingsModelSourcesCard.swift`
- `apps/prowl-macos/Tests/ProwlTests/MLXOperatorArtifactClientTests.swift`

The artifact client now scans the configured `artifacts/` tree for latest milestone-numbered JSON artifacts instead of relying only on hardcoded M214/M216 paths.

## Validation

Command:

```sh
swift test --package-path apps/prowl-macos -c release
```

Result:

- build complete
- `MLXOperatorArtifactClientTests`: `3` passed
- full Prowl test suite: `16` passed, `0` failed

Covered artifact-root states:

- missing root reports `MISSING`
- current quality + current model-swap artifacts report `PASS`
- current quality + older model-swap artifact reports `STALE`

## Performance

This milestone is UI/status plumbing only. It does not change the MLX runtime, model loading, prompt processing, cache behavior, or generation path.

Current relevant performance evidence remains:

- M221 A3B mature hit best service: `205.462 ms`
- M221 A3B first duplicate conversion ratio: `0.775`
- M222 Qwen2.5 Coder 14B active memory: `8.360 GB`
- M222 Qwen2.5 Coder 14B mature hit best service: `182.281 ms`
- M222 Qwen2.5 Coder 14B cold/full-prefill remains slower than A3B and is not promoted as default

## Decision

M223 improves operator correctness, not raw inference speed. The next MLX-side runtime work should continue with port-preflight crash prevention and split-prefill prepare-time reduction.
