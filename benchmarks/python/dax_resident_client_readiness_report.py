#!/usr/bin/env python3
"""Verify the resident Dax client benchmark path is implemented."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--bench-script",
        type=Path,
        default=Path("benchmarks/python/dax_repeated_context_bench.py"),
    )
    parser.add_argument(
        "--fast-path-report",
        type=Path,
        default=Path("artifacts/m105-fast-dax-invocation/fast-dax-invocation-m105-qwen-a3b.json"),
    )
    parser.add_argument("--output-json", type=Path, required=True)
    parser.add_argument("--tag", default="m109-qwen-a3b")
    parser.add_argument("--fail-on-fail", action="store_true")
    args = parser.parse_args()

    source = args.bench_script.read_text()
    fast_path = json.loads(args.fast_path_report.read_text())
    checks = [
        {
            "name": "client_mode_argument",
            "passed": "--client-mode" in source and "resident" in source,
        },
        {
            "name": "direct_resident_completion_call",
            "passed": "run_resident_prompt" in source and "/v1/completions" in source,
        },
        {
            "name": "overhead_ms_row_field",
            "passed": '"overhead_ms"' in source,
        },
        {
            "name": "intent_profile_mapping",
            "passed": "runtime_profile_for_intent" in source,
        },
        {
            "name": "m105_fast_path_passed",
            "passed": fast_path.get("verdict") == "PASS",
        },
    ]
    failures = [check["name"] for check in checks if not check["passed"]]
    output = {
        "type": "dax_resident_client_readiness_report",
        "tag": args.tag,
        "verdict": "PASS" if not failures else "FAIL",
        "failures": failures,
        "checks": checks,
        "implemented_path": {
            "script": str(args.bench_script),
            "mode": "--client-mode resident",
            "endpoint": "/v1/completions",
            "fallback": "--client-mode cli",
        },
        "next_live_validation": (
            "Run dax_repeated_context_bench.py with --client-mode resident "
            "against a loaded resident MLX server and gate overhead_ms <= 500."
        ),
    }
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n")
    print(
        "dax_resident_client_readiness_report",
        output["verdict"],
        "checks",
        len(checks),
        "failures",
        len(failures),
        args.output_json,
        flush=True,
    )
    return 1 if args.fail_on_fail and failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
