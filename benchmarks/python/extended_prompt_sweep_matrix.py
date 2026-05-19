#!/usr/bin/env python3
"""Build the extended prompt-processing sweep matrix for MLX/Dax."""

from __future__ import annotations

import argparse
import json
from itertools import product
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-json", type=Path, required=True)
    parser.add_argument("--tag", default="m111-qwen-a3b")
    parser.add_argument("--fail-on-fail", action="store_true")
    args = parser.parse_args()

    prompt_tokens = [512, 1024, 2048, 4096]
    reuse_modes = ["none", "first-hit", "mature-hit"]
    transports = ["cli", "resident"]
    profiles = [
        "agent-workspace-async",
        "agent-workspace-first-hit",
        "agent-workspace-low-memory",
    ]
    cases = [
        {
            "prompt_tokens": tokens,
            "reuse_mode": reuse,
            "transport": transport,
            "runtime_profile": profile,
            "required_metrics": [
                "wall_ms",
                "service_request_ms",
                "overhead_ms",
                "actual_prefill_tokens",
                "prompt_progress_last_ms",
                "peak_memory_gb",
            ],
        }
        for tokens, reuse, transport, profile in product(
            prompt_tokens, reuse_modes, transports, profiles
        )
    ]
    failures = []
    expected_count = len(prompt_tokens) * len(reuse_modes) * len(transports) * len(profiles)
    if len(cases) != expected_count:
        failures.append(f"case_count={len(cases)} expected={expected_count}")

    output = {
        "type": "extended_prompt_sweep_matrix",
        "tag": args.tag,
        "verdict": "PASS" if not failures else "FAIL",
        "failures": failures,
        "case_count": len(cases),
        "axes": {
            "prompt_tokens": prompt_tokens,
            "reuse_modes": reuse_modes,
            "transports": transports,
            "profiles": profiles,
        },
        "acceptance": {
            "must_include_resident_transport": True,
            "must_report_overhead_ms": True,
            "must_report_prompt_progress": True,
            "must_report_peak_memory_gb": True,
        },
        "cases": cases,
    }
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n")
    print(
        "extended_prompt_sweep_matrix",
        output["verdict"],
        "cases",
        len(cases),
        args.output_json,
        flush=True,
    )
    return 1 if args.fail_on_fail and failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
