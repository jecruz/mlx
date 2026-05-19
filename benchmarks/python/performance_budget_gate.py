#!/usr/bin/env python3
"""Gate performance budget readiness without hiding open optimization gaps."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--performance-report-json", type=Path, required=True)
    parser.add_argument("--output-json", type=Path, required=True)
    parser.add_argument("--tag", default="m196-performance-budget")
    parser.add_argument("--fail-on-fail", action="store_true")
    args = parser.parse_args()

    report = json.loads(args.performance_report_json.read_text())
    current = report.get("current") or {}
    target = report.get("target") or {}
    mature = current.get("mature_hit_service_request_ms")
    target_ms = target.get("mature_hit_service_request_ms")
    failures = []
    warnings = []
    if report.get("verdict") != "PASS":
        failures.append(f"performance report is {report.get('verdict')!r}")
    if current.get("quality_threshold_verdict") != "PASS":
        failures.append("quality threshold is not PASS")
    if current.get("speedup_vs_baseline", 0) < target.get("minimum_speedup_vs_baseline", 0):
        failures.append("speedup budget failed")
    if isinstance(mature, int | float) and isinstance(target_ms, int | float) and mature > target_ms:
        warnings.append(f"optimization gap remains: {mature:.3f}ms > {target_ms:.3f}ms")
    output = {
        "type": "performance_budget_gate",
        "tag": args.tag,
        "verdict": "PASS" if not failures else "FAIL",
        "readiness": "performance-budget-gated" if not failures else "not-ready",
        "mature_hit_service_request_ms": mature,
        "target_mature_hit_service_request_ms": target_ms,
        "speedup_vs_baseline": current.get("speedup_vs_baseline"),
        "quality_threshold_verdict": current.get("quality_threshold_verdict"),
        "warnings": warnings,
        "failures": failures,
    }
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n")
    print(
        "performance_budget_gate",
        output["verdict"],
        output["readiness"],
        "warnings",
        len(warnings),
        "failures",
        len(failures),
        args.output_json,
    )
    return 1 if args.fail_on_fail and failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
