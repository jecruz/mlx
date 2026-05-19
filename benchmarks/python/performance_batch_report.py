#!/usr/bin/env python3
"""Package performance artifacts and next milestones into one final report."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def load_json(path: Path) -> dict:
    return json.loads(path.read_text())


def write_markdown(path: Path, output: dict) -> None:
    perf = output["performance"]
    lines = [
        "# M201 Performance Batch Report",
        "",
        f"Verdict: `{output['verdict']}`",
        f"Readiness: `{output['readiness']}`",
        "",
        "## Performance",
        "",
        f"- baseline service request: `{perf['baseline_service_request_ms']} ms`",
        f"- mature reusable-turn service request: `{perf['mature_hit_service_request_ms']} ms`",
        f"- speedup vs baseline: `{perf['speedup_vs_baseline']}x`",
        f"- max active memory: `{perf['max_active_memory_gb']} GB`",
        f"- target mature hit: `{perf['target_mature_hit_service_request_ms']} ms`",
        f"- required reduction: `{perf['required_reduction_ms']} ms`",
        "",
        "## Next Milestones",
        "",
    ]
    for item in output["next_milestones"]:
        lines.append(f"- `{item['milestone']}`: {item['title']} - {item['acceptance']}")
    lines.extend(["", "## Failures", ""])
    lines.extend([f"- `{failure}`" for failure in output["failures"]] or ["- none"])
    lines.append("")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--performance-report-json", type=Path, required=True)
    parser.add_argument("--budget-gate-json", type=Path, required=True)
    parser.add_argument("--snapshot-json", type=Path, required=True)
    parser.add_argument("--next-plan-json", type=Path, required=True)
    parser.add_argument("--output-json", type=Path, required=True)
    parser.add_argument("--output-md", type=Path, required=True)
    parser.add_argument("--tag", default="m201-performance-batch-report")
    parser.add_argument("--fail-on-fail", action="store_true")
    args = parser.parse_args()

    report = load_json(args.performance_report_json)
    budget = load_json(args.budget_gate_json)
    snapshot = load_json(args.snapshot_json)
    plan = load_json(args.next_plan_json)
    failures = []
    for name, payload in (
        ("performance report", report),
        ("budget gate", budget),
        ("live snapshot", snapshot),
        ("next plan", plan),
    ):
        if payload.get("verdict") != "PASS":
            failures.append(f"{name} verdict is {payload.get('verdict')!r}")
        if payload.get("failures"):
            failures.append(f"{name} has {len(payload['failures'])} failures")
    current = report.get("current") or {}
    target = report.get("target") or {}
    output = {
        "type": "performance_batch_report",
        "tag": args.tag,
        "verdict": "PASS" if not failures else "FAIL",
        "readiness": "performance-batch-reported" if not failures else "not-ready",
        "performance": {
            "baseline_service_request_ms": current.get("baseline_service_request_ms"),
            "mature_hit_service_request_ms": current.get("mature_hit_service_request_ms"),
            "speedup_vs_baseline": current.get("speedup_vs_baseline"),
            "max_active_memory_gb": current.get("max_active_memory_gb"),
            "quality_threshold_verdict": current.get("quality_threshold_verdict"),
            "target_mature_hit_service_request_ms": target.get("mature_hit_service_request_ms"),
            "required_reduction_ms": target.get("required_reduction_ms"),
            "required_reduction_percent": target.get("required_reduction_percent"),
        },
        "next_milestones": plan.get("next_milestones") or [],
        "source_artifacts": {
            "performance_report_json": str(args.performance_report_json),
            "budget_gate_json": str(args.budget_gate_json),
            "snapshot_json": str(args.snapshot_json),
            "next_plan_json": str(args.next_plan_json),
        },
        "failures": failures,
    }
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n")
    write_markdown(args.output_md, output)
    print(
        "performance_batch_report",
        output["verdict"],
        output["readiness"],
        "next",
        len(output["next_milestones"]),
        "failures",
        len(failures),
        args.output_json,
    )
    return 1 if args.fail_on_fail and failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
