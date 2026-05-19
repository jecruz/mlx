#!/usr/bin/env python3
"""Validate the prompt-processing performance report contract."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


REQUIRED_TOP = ["type", "tag", "verdict", "readiness", "current", "target", "warnings", "failures"]
REQUIRED_CURRENT = [
    "baseline_service_request_ms",
    "mature_hit_service_request_ms",
    "speedup_vs_baseline",
    "max_active_memory_gb",
    "memory_source",
    "quality_threshold_verdict",
]
REQUIRED_TARGET = [
    "mature_hit_service_request_ms",
    "required_reduction_ms",
    "required_reduction_percent",
    "minimum_speedup_vs_baseline",
]


def missing(name: str, obj: dict, keys: list[str]) -> list[str]:
    return [f"{name} missing {key}" for key in keys if key not in obj]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--performance-report-json", type=Path, required=True)
    parser.add_argument("--output-json", type=Path, required=True)
    parser.add_argument("--tag", default="m198-performance-report-contract")
    parser.add_argument("--fail-on-fail", action="store_true")
    args = parser.parse_args()

    report = json.loads(args.performance_report_json.read_text())
    current = report.get("current") or {}
    target = report.get("target") or {}
    failures = []
    failures.extend(missing("report", report, REQUIRED_TOP))
    failures.extend(missing("current", current, REQUIRED_CURRENT))
    failures.extend(missing("target", target, REQUIRED_TARGET))
    if report.get("type") != "prompt_processing_performance_report":
        failures.append(f"unexpected type {report.get('type')!r}")
    if report.get("verdict") != "PASS":
        failures.append(f"report verdict is {report.get('verdict')!r}")
    if current.get("quality_threshold_verdict") != "PASS":
        failures.append("quality threshold is not PASS")
    for key in ("baseline_service_request_ms", "mature_hit_service_request_ms", "speedup_vs_baseline"):
        value = current.get(key)
        if not isinstance(value, int | float) or value <= 0:
            failures.append(f"current.{key} must be positive")
    output = {
        "type": "performance_report_contract_probe",
        "tag": args.tag,
        "verdict": "PASS" if not failures else "FAIL",
        "readiness": "performance-report-contract-ready" if not failures else "not-ready",
        "performance_report_json": str(args.performance_report_json),
        "failures": failures,
    }
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n")
    print(
        "performance_report_contract_probe",
        output["verdict"],
        output["readiness"],
        "failures",
        len(failures),
        args.output_json,
    )
    return 1 if args.fail_on_fail and failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
