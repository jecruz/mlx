# M239 Prowl Promotion Visibility Installed-App Smoke

Status: PASS

## Acceptance

Launch or smoke the installed Prowl app path and verify the M235 promotion
summary is reachable from the operator settings/readiness surfaces.

## Installed-App Smoke

- App path: `/Applications/Prowl.app`
- Smoke command:
  `PROWL_APP_SMOKE_APP_BUNDLE=/Applications/Prowl.app PROWL_APP_SMOKE_DAEMON_PORT=18897 PROWL_APP_SMOKE_MODEL_ID= scripts/smoke-prowl-macos-app.sh`
- Result: `Prowl macOS app smoke passed.`
- Daemon: `http://127.0.0.1:18897`
- Direct backend: `http://127.0.0.1:18900`
- Direct child: `http://127.0.0.1:18901`
- Cleanup: enabled

Captured smoke artifacts:

- `prowl-app-health-m239.json`
- `prowl-direct-health-m239.json`
- `prowl-models-m239.json`

Observed runtime health:

- daemon status: `ok`
- active model: `NVIDIA-Nemotron-3-Nano-4B-Q8_0`
- active profile: `default`
- direct child reachable: `true`
- model catalog entries: `102`

## Promotion Visibility Reachability

The M235 promotion fields remain wired into the Prowl operator artifact
surfaces:

- readiness card source:
  `/Users/jeffreycruz/Development/LLM_INFERENCE/prowl-llm/apps/prowl-macos/Sources/ProwlMac/Features/Engine/MLXOperatorReadinessCard.swift`
- settings source:
  `/Users/jeffreycruz/Development/LLM_INFERENCE/prowl-llm/apps/prowl-macos/Sources/ProwlMac/Features/Settings/SettingsModelSourcesCard.swift`
- artifact-client test:
  `/Users/jeffreycruz/Development/LLM_INFERENCE/prowl-llm/apps/prowl-macos/Tests/ProwlTests/MLXOperatorArtifactClientTests.swift`

Source reachability checks found:

- `swapCandidateProfile`
- `swapFirstDuplicateServiceMs`
- `swapMatureHitSpeedup`
- `swapMaxPeakMemoryGB`
- readiness summary text with `profile=`, `first-dup=`, `speedup=`, and
  `peak=`
- settings summary text beginning `Promotion:`

## Targeted Validation

Command:

```bash
swift test --package-path apps/prowl-macos -c release --filter MLXOperatorArtifactClientTests/testPassArtifactsReportPassRootStatus
```

Result:

- tests executed: `1`
- failures: `0`
- status: `PASS`

## Performance Report

M239 does not change the MLX inference hot path. It verifies that the product
surface can expose the lower-memory promotion evidence produced by earlier MLX
gates.

Current evidence preserved from the live MLX gates:

- M237 bounded first-hit baseline service: `4310.493 ms`
- M237 first duplicate service: `186.185 ms`
- M237 best hit service: `183.017 ms`
- M237 mature-hit speedup: `23.152x`
- M237 peak memory: `10.142 GB`
- M237 cache memory: `0.022 GB`
- M238 low-memory routed service: `243.735 ms`
- M238 low-memory routed prefill: `55` tokens

## Conclusion

M239 passes. The installed Prowl app path launches through the existing smoke
harness, the direct backend is reachable, and the M235 lower-memory promotion
fields are still covered by the artifact-client decode test and visible from
the readiness/settings source surfaces.
