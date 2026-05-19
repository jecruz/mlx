# MLX Request Metadata Client Contract

This contract defines how product clients should route workload intent to the
resident MLX engine without changing global engine configuration before every
request.

## Scope

Applies to:

- `/generate`
- `/v1/completions`
- `/v1/chat/completions`

Validated by:

- `benchmarks/python/request_profile_metadata_gate.py`
- `benchmarks/python/live_request_profile_metadata_probe.py`
- `benchmarks/python/run_live_product_regression_suite.py`

Current live validation artifact:

- `artifacts/m124-live-product-regression-suite/live-product-regression-suite-m124-qwen-a3b.json`
- `artifacts/m128-dax-request-metadata-smoke/dax-request-metadata-smoke-m128-qwen-a3b.json`

## Contract

Clients may include workload metadata directly in the request JSON body.

Accepted fields:

- `runtime_profile`: explicit operator override.
- `workload_intent`: product-level workload hint.
- `memory_class_gb`: approximate target Mac memory class.
- `immediate_second_turn`: prefer immediate repeated-context conversion.
- `low_memory`: force bounded lower-memory behavior.
- `diagnostics_workload`: force diagnostics profile.
- `interactive_workload`: foreground interactive use.
- `agentic_workload`: coding-agent or agent workspace use.
- `repeated_workspace`: repeated repo/workspace context expected.

The server applies request metadata before prefill policy selection, so the
selected runtime profile controls cache population, pending-wait behavior,
memory limits, and prompt-processing policy for that request.

## Priority

Selection precedence:

1. `runtime_profile`
2. diagnostics hints
3. memory-saver intent
4. low-memory hints or `memory_class_gb` of `16`, `24`, or `32`
5. first-hit hints
6. agentic/repeated-workspace hints
7. interactive hints
8. current engine default

Manual `runtime_profile` is always the highest-priority override.

## Workload Intents

Supported `workload_intent` values:

- `interactive`
- `coding-agent`
- `agent-workspace`
- `coding-agent-first-hit`
- `first-hit`
- `coding-agent-low-memory`
- `low-memory`
- `memory-saver`
- `diagnostics`

Routing table:

| Input | Runtime Profile | Use Case |
| --- | --- | --- |
| `runtime_profile=interactive` | `interactive` | Explicit foreground override |
| `workload_intent=interactive` | `interactive` | Foreground chat/UI request |
| `workload_intent=coding-agent` | `agent-workspace-async` | Normal coding-agent reuse |
| `workload_intent=agent-workspace` | `agent-workspace-async` | Normal repeated workspace context |
| `workload_intent=first-hit` | `agent-workspace-first-hit` | Immediate second-turn responsiveness |
| `workload_intent=coding-agent-first-hit` | `agent-workspace-first-hit` | Coding-agent first-hit conversion |
| `workload_intent=low-memory` | `agent-workspace-low-memory` | Smaller-memory Mac path |
| `workload_intent=coding-agent-low-memory` | `agent-workspace-low-memory` | Coding-agent lower-memory path |
| `memory_class_gb=16`, `24`, or `32` | `agent-workspace-low-memory` | Automatic bounded-memory routing |
| `workload_intent=memory-saver` | `memory-saver` | Conservative generic memory-saver mode |
| `workload_intent=diagnostics` | `diagnostics` | Operator diagnostics |

## Completion Example

```json
{
  "model": "local-mlx",
  "prompt": "Summarize this workspace context in one paragraph.",
  "max_tokens": 128,
  "workload_intent": "first-hit",
  "immediate_second_turn": true
}
```

Expected response metrics:

```json
{
  "engine_metrics": {
    "request_runtime_profile": "agent-workspace-first-hit",
    "request_runtime_profile_source": "request_metadata",
    "request_runtime_profile_reason": "immediate repeated-context second turn",
    "request_runtime_profile_applied": true
  }
}
```

## Chat Example

```json
{
  "model": "local-mlx",
  "messages": [
    {
      "role": "user",
      "content": "Use the current repo context and propose the next change."
    }
  ],
  "max_tokens": 256,
  "workload_intent": "coding-agent",
  "repeated_workspace": true,
  "memory_class_gb": 32
}
```

Expected route:

- `agent-workspace-low-memory`

Reason:

- `memory_class_gb=32` takes precedence over the normal coding-agent async
  profile.

## Manual Override Example

```json
{
  "model": "local-mlx",
  "prompt": "Answer interactively.",
  "max_tokens": 64,
  "runtime_profile": "interactive",
  "workload_intent": "low-memory",
  "low_memory": true
}
```

Expected route:

- `interactive`

Reason:

- explicit `runtime_profile` overrides conflicting workload hints.

## Client Guidance

Use these defaults:

- UI chat: `workload_intent=interactive`
- Coding agent steady state: `workload_intent=coding-agent`
- Immediate repeated-context second turn: `workload_intent=first-hit`
- Smaller-memory Mac: `workload_intent=coding-agent`, `memory_class_gb=32`
- Operator diagnostics: `workload_intent=diagnostics`

Do not require users to pick raw cache or prefill knobs in the UI. Present the
above as product modes and let the server map them to runtime profiles.

## Dax Client Behavior

Dax uses request metadata for product generation paths:

```bash
node packages/coding-agent/dist/cli.js mlx-engine \
  --base-url http://127.0.0.1:8773 \
  --prompt "Use the current repo context and propose the next change." \
  --max-tokens 128
```

Default prompt and interactive sessions send:

```json
{
  "workload_intent": "coding-agent",
  "agentic_workload": true,
  "repeated_workspace": true
}
```

Dax intent mapping:

| Dax Option | Request Metadata |
| --- | --- |
| no `--intent` with `--prompt` or `--interactive` | `workload_intent=coding-agent`, `agentic_workload=true`, `repeated_workspace=true` |
| `--intent interactive` | `workload_intent=interactive`, `interactive_workload=true` |
| `--intent first-hit` | `workload_intent=first-hit`, `immediate_second_turn=true`, agent workspace flags |
| `--intent low-memory` | `workload_intent=low-memory`, `low_memory=true`, agent workspace flags |
| `--intent memory-saver` | `workload_intent=memory-saver`, `low_memory=true` |
| `--intent diagnostics` | `workload_intent=diagnostics`, `diagnostics_workload=true` |
| `--profile <name>` with generation | `runtime_profile=<name>` |

Operator distinction:

- `--prompt` and `--interactive` use request metadata.
- status-only `--profile` and `--intent` still call `/engine/config`.
- interactive `/profile` remains an explicit global profile override.

## Python Client Helper

`mlx_engine.ui_client` exposes product-mode helpers so clients do not need to
hardcode request metadata fields.

Product modes:

- `chat`
- `coding-agent`
- `coding-agent-first-hit`
- `coding-agent-low-memory`
- `diagnostics`

Example:

```python
from mlx_engine.ui_client import apply_product_mode

payload = apply_product_mode(
    {
        "model": "local-mlx",
        "messages": [
            {
                "role": "user",
                "content": "Use the repo context and suggest the next change.",
            }
        ],
        "max_tokens": 256,
    },
    "coding-agent",
    memory_class_gb=32,
)
```

The resulting payload includes:

```json
{
  "workload_intent": "coding-agent",
  "memory_class_gb": 32,
  "agentic_workload": true,
  "repeated_workspace": true
}
```

Expected route:

- `agent-workspace-low-memory`

Manual override remains available:

```python
payload = apply_product_mode(
    {"model": "local-mlx", "prompt": "Answer interactively.", "max_tokens": 64},
    "coding-agent-low-memory",
    runtime_profile="interactive",
)
```

Validation artifact:

- `artifacts/m126-product-mode-metadata/product-mode-metadata-m126-qwen-a3b.json`
- `artifacts/m128-dax-request-metadata-smoke/dax-request-metadata-smoke-m128-qwen-a3b.json`

## Validation

Static contract gate:

```bash
python3 benchmarks/python/request_profile_metadata_gate.py \
  --output-json artifacts/m122-request-profile-metadata/request-profile-metadata-gate-m122-qwen-a3b.json \
  --tag m122-qwen-a3b \
  --fail-on-fail
```

Live request-metadata probe:

```bash
python3 benchmarks/python/live_request_profile_metadata_probe.py \
  --base-url http://127.0.0.1:8773 \
  --output-json artifacts/m123-live-request-profile-metadata/live-request-profile-metadata-m123-qwen-a3b.json \
  --tag m123-qwen-a3b \
  --fail-on-fail
```

Full product regression suite:

```bash
python3 benchmarks/python/run_live_product_regression_suite.py \
  --base-url http://127.0.0.1:8773 \
  --output-dir artifacts/m124-live-product-regression-suite \
  --tag m124-qwen-a3b \
  --fail-on-fail
```

Product-mode helper probe:

```bash
python3 benchmarks/python/product_mode_metadata_probe.py \
  --output-json artifacts/m126-product-mode-metadata/product-mode-metadata-m126-qwen-a3b.json \
  --tag m126-qwen-a3b \
  --fail-on-fail
```

Acceptance:

- all verdicts are `PASS`
- `engine_metrics.request_runtime_profile_source` is `request_metadata`
- `engine_metrics.request_runtime_profile_applied` is `true`
- manual override precedence is preserved

## Current Limitation

Request metadata currently changes the resident engine runtime profile before
the request runs. With the current single-request scheduler this is acceptable.
If the server later supports true concurrent generation, profile application
must become request-scoped rather than mutating global engine state.
