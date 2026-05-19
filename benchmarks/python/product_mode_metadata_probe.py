#!/usr/bin/env python3
"""Validate product-mode to request-metadata client helpers."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from mlx_engine.ui_client import apply_product_mode, metadata_for_product_mode


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-json", type=Path, required=True)
    parser.add_argument("--tag", default="m126-qwen-a3b")
    parser.add_argument("--fail-on-fail", action="store_true")
    args = parser.parse_args()

    cases = [
        ("chat", {}, "interactive"),
        ("coding-agent", {}, "agent-workspace-async"),
        ("coding-agent", {"memory_class_gb": 32}, "agent-workspace-low-memory"),
        ("coding-agent-first-hit", {}, "agent-workspace-first-hit"),
        ("coding-agent-low-memory", {}, "agent-workspace-low-memory"),
        ("diagnostics", {}, "diagnostics"),
        (
            "coding-agent-low-memory",
            {"runtime_profile": "interactive"},
            "interactive",
        ),
    ]
    results = []
    failures = []
    for mode, kwargs, expected_profile in cases:
        metadata = metadata_for_product_mode(mode, **kwargs)
        fields = metadata.request_fields()
        payload = apply_product_mode(
            {"model": "local-mlx", "prompt": "hello", "max_tokens": 1},
            mode,
            **kwargs,
        )
        passed = metadata.expected_runtime_profile == expected_profile
        if not passed:
            failures.append(
                f"{mode} {kwargs}: expected={expected_profile!r} "
                f"observed={metadata.expected_runtime_profile!r}"
            )
        missing_payload_fields = [
            key for key, value in fields.items() if payload.get(key) != value
        ]
        if missing_payload_fields:
            failures.append(
                f"{mode} {kwargs}: payload mismatch fields={missing_payload_fields}"
            )
        results.append(
            {
                "mode": mode,
                "kwargs": kwargs,
                "request_fields": fields,
                "expected_runtime_profile": expected_profile,
                "observed_runtime_profile": metadata.expected_runtime_profile,
                "payload": payload,
                "verdict": "PASS" if passed and not missing_payload_fields else "FAIL",
            }
        )

    output = {
        "type": "product_mode_metadata_probe",
        "tag": args.tag,
        "verdict": "PASS" if not failures else "FAIL",
        "case_count": len(cases),
        "cases": results,
        "failures": failures,
    }
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n")
    print(
        "product_mode_metadata_probe",
        output["verdict"],
        "cases",
        len(cases),
        "failures",
        len(failures),
        args.output_json,
        flush=True,
    )
    for failure in failures:
        print("failure", failure, flush=True)
    return 1 if args.fail_on_fail and failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
