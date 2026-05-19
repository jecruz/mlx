#!/usr/bin/env python3
"""Derive Dax/operator overhead reduction targets from wall-time evidence."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from statistics import mean
from typing import Any


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text())


def as_float(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


def projected_case(case: dict[str, Any], target_overhead_ms: float) -> dict[str, Any]:
    baseline = case.get("baseline") or {}
    mature = case.get("mature_hit") or {}
    baseline_service = as_float(baseline.get("service_request_ms"))
    mature_service = as_float(mature.get("service_request_ms"))
    baseline_wall = as_float(baseline.get("wall_ms"))
    mature_wall = as_float(mature.get("wall_ms"))
    derived = case.get("derived") or {}
    mean_overhead = as_float(derived.get("mean_operator_overhead_ms"))

    projected_baseline_wall = (
        baseline_service + target_overhead_ms if baseline_service is not None else None
    )
    projected_mature_wall = mature_service + target_overhead_ms if mature_service is not None else None
    projected_wall_speedup = (
        projected_baseline_wall / projected_mature_wall
        if projected_baseline_wall is not None
        and projected_mature_wall is not None
        and projected_mature_wall > 0
        else None
    )
    current_wall_speedup = as_float(derived.get("baseline_to_mature_wall_speedup"))
    mature_wall_reduction_ms = (
        mature_wall - projected_mature_wall
        if mature_wall is not None and projected_mature_wall is not None
        else None
    )
    mature_wall_reduction_pct = (
        mature_wall_reduction_ms / mature_wall
        if mature_wall_reduction_ms is not None and mature_wall is not None and mature_wall > 0
        else None
    )

    return {
        "label": case.get("label"),
        "dax_profile": case.get("dax_profile"),
        "current": {
            "baseline_wall_ms": baseline_wall,
            "mature_wall_ms": mature_wall,
            "baseline_service_ms": baseline_service,
            "mature_service_ms": mature_service,
            "mean_operator_overhead_ms": mean_overhead,
            "wall_speedup": current_wall_speedup,
        },
        "target": {
            "operator_overhead_ms": target_overhead_ms,
            "projected_baseline_wall_ms": projected_baseline_wall,
            "projected_mature_wall_ms": projected_mature_wall,
            "projected_wall_speedup": projected_wall_speedup,
            "mature_wall_reduction_ms": mature_wall_reduction_ms,
            "mature_wall_reduction_pct": mature_wall_reduction_pct,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--wall-time-report",
        type=Path,
        default=Path("artifacts/m100-operator-wall-time/dax-operator-wall-time-m100-qwen-a3b.json"),
    )
    parser.add_argument("--output-json", type=Path, required=True)
    parser.add_argument("--tag", default="m103-qwen-a3b")
    parser.add_argument("--target-overhead-ms", type=float, default=500.0)
    parser.add_argument("--warn-overhead-ms", type=float, default=1000.0)
    parser.add_argument("--fail-on-fail", action="store_true")
    args = parser.parse_args()

    source = load_json(args.wall_time_report)
    cases = source.get("cases") or []
    projections = [projected_case(case, args.target_overhead_ms) for case in cases]
    overheads = [
        as_float((case.get("derived") or {}).get("mean_operator_overhead_ms")) for case in cases
    ]
    overheads = [value for value in overheads if value is not None]
    mature_reductions = [
        as_float((case.get("target") or {}).get("mature_wall_reduction_pct"))
        for case in projections
    ]
    mature_reductions = [value for value in mature_reductions if value is not None]
    mean_overhead = mean(overheads) if overheads else None
    max_overhead = max(overheads) if overheads else None
    failures: list[str] = []
    if source.get("verdict") != "PASS":
        failures.append(f"source wall-time report is {source.get('verdict')!r}")
    if not cases:
        failures.append("no wall-time cases found")
    if max_overhead is None or max_overhead <= args.warn_overhead_ms:
        failures.append(
            f"overhead signal too weak for reduction milestone: max_overhead={max_overhead}"
        )

    output = {
        "type": "dax_operator_overhead_reduction_report",
        "tag": args.tag,
        "verdict": "PASS" if not failures else "FAIL",
        "source_report": str(args.wall_time_report),
        "target_overhead_ms": args.target_overhead_ms,
        "warn_overhead_ms": args.warn_overhead_ms,
        "case_count": len(cases),
        "failures": failures,
        "summary": {
            "mean_operator_overhead_ms": mean_overhead,
            "max_operator_overhead_ms": max_overhead,
            "mean_projected_mature_wall_reduction_pct": mean(mature_reductions)
            if mature_reductions
            else None,
        },
        "recommendations": [
            {
                "priority": 1,
                "item": "Avoid per-request Dax CLI process startup for benchmark/product calls.",
                "reason": "M100 wall time includes large overhead outside resident service_request_ms.",
            },
            {
                "priority": 2,
                "item": "Keep a resident Dax client/session or direct transport for repeated prompt turns.",
                "reason": "The model service path is already faster than operator-visible wall time.",
            },
            {
                "priority": 3,
                "item": "Track wall_ms, service_request_ms, and overhead_ms in every product-path gate.",
                "reason": "Service-only wins can be hidden by product invocation overhead.",
            },
        ],
        "cases": projections,
    }
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n")

    print(
        "dax_operator_overhead_reduction_report",
        output["verdict"],
        "cases",
        len(cases),
        "mean_overhead_ms",
        mean_overhead,
        args.output_json,
        flush=True,
    )
    for case in projections:
        target = case["target"]
        print(
            "case",
            case["label"],
            "current_wall_speedup",
            case["current"]["wall_speedup"],
            "projected_wall_speedup",
            target["projected_wall_speedup"],
            "mature_wall_reduction_pct",
            target["mature_wall_reduction_pct"],
            flush=True,
        )
    return 1 if args.fail_on_fail and failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
