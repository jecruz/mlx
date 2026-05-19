#!/usr/bin/env python3
"""Render a compact prompt-processing performance report."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def render(report: dict) -> str:
    current = report["current"]
    target = report["target"]
    lines = [
        f"Prompt Processing Performance: {report['verdict']}",
        f"readiness={report['readiness']} quality={current['quality_threshold_verdict']}",
        (
            f"baseline={current['baseline_service_request_ms']}ms "
            f"mature_hit={current['mature_hit_service_request_ms']}ms "
            f"speedup={current['speedup_vs_baseline']}x"
        ),
        (
            f"target={target['mature_hit_service_request_ms']}ms "
            f"required_reduction={target['required_reduction_ms']}ms "
            f"required_reduction_pct={target['required_reduction_percent']}%"
        ),
        (
            f"memory_source={current['memory_source']} "
            f"max_active={current['max_active_memory_gb']}GB"
        ),
    ]
    warnings = report.get("warnings") or []
    if warnings:
        lines.append("warnings:")
        lines.extend(f"- {warning}" for warning in warnings)
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--performance-report-json", type=Path, required=True)
    parser.add_argument("--output-text", type=Path, required=True)
    parser.add_argument("--output-json", type=Path, required=True)
    parser.add_argument("--tag", default="m199-performance-report-render")
    parser.add_argument("--fail-on-fail", action="store_true")
    args = parser.parse_args()

    report = json.loads(args.performance_report_json.read_text())
    text = render(report)
    output = {
        "type": "performance_report_render",
        "tag": args.tag,
        "verdict": "PASS" if report.get("verdict") == "PASS" else "FAIL",
        "readiness": "performance-report-rendered" if report.get("verdict") == "PASS" else "not-ready",
        "performance_report_json": str(args.performance_report_json),
        "text": text,
        "failures": [] if report.get("verdict") == "PASS" else ["performance report is not PASS"],
    }
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_text.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n")
    args.output_text.write_text(text)
    print(text, end="")
    print(
        "performance_report_render",
        output["verdict"],
        output["readiness"],
        args.output_json,
    )
    return 1 if args.fail_on_fail and output["verdict"] != "PASS" else 0


if __name__ == "__main__":
    raise SystemExit(main())
