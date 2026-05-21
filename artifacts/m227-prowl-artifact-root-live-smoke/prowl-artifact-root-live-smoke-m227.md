# M227 Prowl Artifact-Root Live Smoke

## Result

M227 is complete. Prowl's artifact client reads the configured MLX artifact root live from:

`/Users/jeffreycruz/Development/LLM_INFERENCE/mlx/.worktrees/prompt-processing-bench`

The smoke confirmed that Prowl does not need an app rebuild to see newly added MLX artifacts. The current live app-visible state is:

- root status: `STALE`
- quality status: `PASS`
- quality source: `artifacts/m226-lower-memory-first-hit-conversion/quality-threshold-gate-m226-qwen25-coder-14b-adapted.json`
- quality verdict: `PASS`
- quality readiness: `ci-quality-ready`
- model-swap status: `STALE`
- model-swap source: `artifacts/m216-lower-memory-candidate-replacement/model-swap-acceptance-m216-gpt-oss-low-reasoning.json`

The `STALE` root status is correct. The MLX artifact root now has M226 quality evidence, but the newest model-swap artifact is still M216, so Prowl should warn instead of presenting the root as fully PASS.

## Live Smoke

Temporary Prowl XCTest added for the smoke and removed before completion:

```swift
func testConfiguredDefaultRootReadsLatestM226QualityArtifact() async throws {
    let root = URL(fileURLWithPath: AppModel.defaultMLXArtifactRootDirectory)
    let summary = await MLXOperatorArtifactClient(rootURL: root).summary()

    XCTAssertEqual(summary.rootPath, root.standardizedFileURL.path)
    XCTAssertEqual(summary.qualityStatus, "PASS")
    XCTAssertEqual(summary.qualityVerdict, "PASS")
    XCTAssertEqual(summary.qualityReadiness, "ci-quality-ready")
    XCTAssertEqual(
        summary.qualitySource,
        "artifacts/m226-lower-memory-first-hit-conversion/quality-threshold-gate-m226-qwen25-coder-14b-adapted.json"
    )
    XCTAssertEqual(summary.swapStatus, "STALE")
    XCTAssertEqual(
        summary.swapSource,
        "artifacts/m216-lower-memory-candidate-replacement/model-swap-acceptance-m216-gpt-oss-low-reasoning.json"
    )
}
```

Command:

```sh
swift test --package-path apps/prowl-macos -c release --filter ProwlTests.MLXOperatorArtifactClientTests/testConfiguredDefaultRootReadsLatestM226QualityArtifact
```

Result:

- build complete
- selected live-smoke test passed
- executed `1` test
- failures `0`

The temporary test exercised the actual Prowl `MLXOperatorArtifactClient` and `AppModel.defaultMLXArtifactRootDirectory` path. It was removed after the smoke so the Prowl repo remains unchanged.

## Regression Check

Command:

```sh
swift test --package-path apps/prowl-macos -c release
```

Result:

- build complete
- `MLXOperatorArtifactClientTests`: `3` passed
- `SettingsEngineReadinessEvaluatorTests`: `8` passed
- `SettingsSelectedModelReadinessEvaluatorTests`: `5` passed
- full suite: `16` passed, `0` failed

Prowl repo status after smoke:

- clean
- no committed Prowl code change required

## Performance

This milestone is app/status validation only. It does not change MLX runtime code, prompt processing, cache creation, generation, or model loading.

Current relevant MLX performance evidence remains from M226:

- lower-memory candidate turn-2 prefill: `11` tokens, down from M222 `2081`
- mature-hit service: `185.817 ms`
- mature-hit speedup vs baseline: `21.390x`
- loaded lower-memory candidate active memory: `8.309 GB`
- first-duplicate latency is still blocked by synchronous cache build: `3366.409 ms` cache prepare

## Decision

M227 validates the product surface contract: Prowl sees the configured MLX artifact root live and surfaces the latest artifact state without rebuilding the app. The current warning state is correct and useful because model-swap evidence is stale relative to the latest quality milestone.
