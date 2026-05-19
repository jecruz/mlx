#!/usr/bin/env python3
"""Plan and gate the fast Dax invocation path for MLX product calls."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text())


def as_float(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--overhead-report",
        type=Path,
        default=Path(
            "artifacts/m103-operator-overhead-reduction/operator-overhead-reduction-m103-qwen-a3b.json"
        ),
    )
    parser.add_argument(
        "--prompt-report",
        type=Path,
        default=Path(
            "artifacts/m104-prompt-processing-extension/prompt-processing-extension-m104-qwen-a3b.json"
        ),
    )
    parser.add_argument("--output-json", type=Path, required=True)
    parser.add_argument("--tag", default="m105-qwen-a3b")
    parser.add_argument("--target-overhead-ms", type=float, default=500.0)
    parser.add_argument("--fail-on-fail", action="store_true")
    args = parser.parse_args()

    overhead = load_json(args.overhead_report)
    prompt = load_json(args.prompt_report)
    current_mean_overhead = as_float((overhead.get("summary") or {}).get("mean_operator_overhead_ms"))
    projected_reduction = as_float(
        (overhead.get("summary") or {}).get("mean_projected_mature_wall_reduction_pct")
    )
    long_prompt_share = as_float(
        ((prompt.get("buckets") or {}).get("long_prefill") or {}).get(
            "mean_prompt_progress_share_of_service"
        )
    )
    failures: list[str] = []
    if overhead.get("verdict") != "PASS":
        failures.append("overhead report did not pass")
    if prompt.get("verdict") != "PASS":
        failures.append("prompt-processing extension report did not pass")
    if current_mean_overhead is None or current_mean_overhead <= args.target_overhead_ms:
        failures.append(
            f"current_mean_overhead_ms={current_mean_overhead} is not above target={args.target_overhead_ms}"
        )
    if long_prompt_share is None or long_prompt_share < 0.8:
        failures.append(f"long_prompt_share={long_prompt_share} does not show prompt bottleneck")

    output = {
        "type": "dax_fast_invocation_path_report",
        "tag": args.tag,
        "verdict": "PASS" if not failures else "FAIL",
        "failures": failures,
        "inputs": {
            "overhead_report": str(args.overhead_report),
            "prompt_report": str(args.prompt_report),
        },
        "current": {
            "mean_operator_overhead_ms": current_mean_overhead,
            "target_operator_overhead_ms": args.target_overhead_ms,
            "projected_mature_wall_reduction_pct": projected_reduction,
            "long_prefill_prompt_progress_share_of_service": long_prompt_share,
        },
        "recommended_path": {
            "name": "resident-dax-client",
            "goal": "Reuse a loaded Dax process/client for repeated MLX product calls.",
            "transport_order": [
                "in-process Dax panel/client call",
                "resident Dax local RPC/IPC client",
                "direct HTTP client to MLX resident service",
                "fallback npx/tsx CLI process",
            ],
            "acceptance": {
                "mean_operator_overhead_ms": f"<={args.target_overhead_ms}",
                "must_preserve_metrics": ["wall_ms", "service_request_ms", "overhead_ms"],
                "must_preserve_profile_controls": [
                    "agent-workspace-async",
                    "agent-workspace-first-hit",
                    "agent-workspace-low-memory",
                ],
            },
        },
        "implementation_tasks": [
            {
                "order": 1,
                "task": "Add a reusable Dax MLX client object that keeps config, HTTP agent, and profile state warm.",
            },
            {
                "order": 2,
                "task": "Teach product benchmark paths to call the reusable client before falling back to npx/tsx.",
            },
            {
                "order": 3,
                "task": "Emit overhead_ms in product benchmark rows and gate it against the M103 target.",
            },
            {
                "order": 4,
                "task": "Keep prompt-progress metrics separate so faster transport does not hide engine prompt bottlenecks.",
            },
        ],
    }
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n")
    print(
        "dax_fast_invocation_path_report",
        output["verdict"],
        "mean_overhead_ms",
        current_mean_overhead,
        "target_overhead_ms",
        args.target_overhead_ms,
        args.output_json,
        flush=True,
    )
    for failure in failures:
        print("failure", failure, flush=True)
    return 1 if args.fail_on_fail and failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
