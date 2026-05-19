#!/usr/bin/env python3
"""Run Dax --product-mode smoke requests against the live MLX engine."""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path
from typing import Any


EXPECTED = {
    "chat": "interactive",
    "coding-agent": "agent-workspace-async",
    "coding-agent-first-hit": "agent-workspace-first-hit",
    "coding-agent-low-memory": "agent-workspace-low-memory",
    "diagnostics": "diagnostics",
}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8773")
    parser.add_argument(
        "--dax-cli",
        type=Path,
        default=Path("/Users/jeffreycruz/Development/AI_AGENTS/dax-stereo/packages/coding-agent/dist/cli.js"),
    )
    parser.add_argument("--output-json", type=Path, required=True)
    parser.add_argument("--tag", default="m148-qwen-a3b")
    parser.add_argument("--max-tokens", type=int, default=4)
    parser.add_argument("--fail-on-fail", action="store_true")
    args = parser.parse_args()

    rows: list[dict[str, Any]] = []
    failures: list[str] = []
    for mode, expected_profile in EXPECTED.items():
        prompt = f"{args.tag} Dax product mode {mode}. Reply briefly."
        cmd = [
            "node",
            str(args.dax_cli),
            "mlx-engine",
            "--base-url",
            args.base_url,
            "--product-mode",
            mode,
            "--prompt",
            prompt,
            "--max-tokens",
            str(args.max_tokens),
            "--json",
        ]
        completed = subprocess.run(cmd, check=False, capture_output=True, text=True, timeout=240)
        response = json.loads(completed.stdout) if completed.returncode == 0 else None
        metrics = (response or {}).get("engine_metrics") or {}
        ok = (
            completed.returncode == 0
            and metrics.get("request_runtime_profile_source") == "request_metadata"
            and metrics.get("request_runtime_profile") == expected_profile
            and metrics.get("request_runtime_profile_applied") is True
            and metrics.get("request_runtime_profile_scoped") is True
        )
        if not ok:
            failures.append(f"{mode}: profile={metrics.get('request_runtime_profile')!r} returncode={completed.returncode}")
        rows.append(
            {
                "mode": mode,
                "expected_profile": expected_profile,
                "returncode": completed.returncode,
                "request_runtime_profile": metrics.get("request_runtime_profile"),
                "request_runtime_profile_source": metrics.get("request_runtime_profile_source"),
                "request_runtime_profile_scoped": metrics.get("request_runtime_profile_scoped"),
                "service_request_ms": metrics.get("service_request_ms"),
                "command": cmd,
            }
        )

    output = {
        "type": "dax_product_mode_smoke",
        "tag": args.tag,
        "base_url": args.base_url,
        "verdict": "PASS" if not failures else "FAIL",
        "readiness": "dax-product-modes-live" if not failures else "not-ready",
        "row_count": len(rows),
        "rows": rows,
        "failures": failures,
    }
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n")
    print("dax_product_mode_smoke", output["verdict"], "rows", len(rows), "failures", len(failures), args.output_json)
    if args.fail_on_fail and output["verdict"] != "PASS":
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
