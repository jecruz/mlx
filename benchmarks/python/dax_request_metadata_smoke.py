#!/usr/bin/env python3
"""Validate that the Dax CLI sends MLX request metadata to the live server."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any


def check_equal(checks: list[dict[str, Any]], name: str, actual: Any, expected: Any) -> None:
    checks.append(
        {
            "name": name,
            "actual": actual,
            "expected": expected,
            "pass": actual == expected,
        }
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8773")
    parser.add_argument(
        "--dax-cli",
        type=Path,
        default=Path(
            "/Users/jeffreycruz/Development/AI_AGENTS/dax-stereo/packages/coding-agent/dist/cli.js"
        ),
    )
    parser.add_argument("--output-json", type=Path, required=True)
    parser.add_argument("--tag", default="m131-qwen-a3b")
    parser.add_argument("--intent", default="coding-agent")
    parser.add_argument("--max-tokens", type=int, default=8)
    parser.add_argument("--fail-on-fail", action="store_true")
    args = parser.parse_args()

    prompt = f"{args.tag} Dax request metadata smoke. Reply with one short sentence."
    cmd = [
        "node",
        str(args.dax_cli),
        "mlx-engine",
        "--base-url",
        args.base_url,
        "--intent",
        args.intent,
        "--prompt",
        prompt,
        "--max-tokens",
        str(args.max_tokens),
        "--json",
    ]
    completed = subprocess.run(cmd, check=False, capture_output=True, text=True, timeout=240)
    response: dict[str, Any] | None = None
    checks: list[dict[str, Any]] = []
    failures: list[str] = []
    if completed.returncode == 0:
        response = json.loads(completed.stdout)
        metrics = response.get("engine_metrics") or {}
        check_equal(checks, "request_runtime_profile_source", metrics.get("request_runtime_profile_source"), "request_metadata")
        check_equal(checks, "request_runtime_profile_applied", metrics.get("request_runtime_profile_applied"), True)
        check_equal(checks, "workload_intent", metrics.get("workload_intent"), args.intent)
        check_equal(checks, "agentic_workload", metrics.get("agentic_workload"), True)
        check_equal(checks, "repeated_workspace", metrics.get("repeated_workspace"), True)
        for check in checks:
            if not check["pass"]:
                failures.append(f"{check['name']}: {check['actual']!r} != {check['expected']!r}")
    else:
        failures.append(f"Dax command failed with returncode={completed.returncode}")

    output = {
        "type": "dax_request_metadata_smoke",
        "tag": args.tag,
        "base_url": args.base_url,
        "dax_cli": str(args.dax_cli),
        "command": cmd,
        "returncode": completed.returncode,
        "verdict": "PASS" if not failures else "FAIL",
        "readiness": "dax-request-metadata-live" if not failures else "not-ready",
        "checks": checks,
        "failures": failures,
        "response": response,
        "stderr": completed.stderr,
    }
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n")
    print(
        "dax_request_metadata_smoke",
        output["verdict"],
        "checks",
        len(checks),
        "failures",
        len(failures),
        args.output_json,
        flush=True,
    )
    if args.fail_on_fail and output["verdict"] != "PASS":
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
