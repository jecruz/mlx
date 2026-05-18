#!/usr/bin/env python3
"""Calibrate resident regression thresholds from measured gate reports."""

from __future__ import annotations

import argparse
import json
import statistics
from pathlib import Path
from typing import Any


CHECK_TO_FLAG = {
    "cache_hit.mean_service_request_ms": "max_cache_hit_service_ms",
    "cache_hit.mean_actual_prefill_tokens": "max_cache_hit_prefill_tokens",
    "cache_create.mean_service_request_ms": "max_cache_create_service_ms",
    "cache_create.cache_prepare_share": "max_cache_create_prepare_share",
    "prefill_warm.mean_service_request_ms": "max_warm_prefill_service_ms",
    "prefill_warm.mean_actual_prefill_tokens": "min_warm_prefill_tokens",
    "prefill_cold_to_warm_ratio": "max_cold_to_warm_ratio",
    "cache_hit.service_speedup_vs_full_prefill": "min_cache_hit_speedup_vs_full_prefill",
    "cache_hit.prefill_reduction_vs_full_prefill": "min_cache_hit_prefill_reduction_vs_full_prefill",
}

LOWER_IS_BETTER = {
    "cache_hit.mean_service_request_ms",
    "cache_hit.mean_actual_prefill_tokens",
    "cache_create.mean_service_request_ms",
    "cache_create.cache_prepare_share",
    "prefill_warm.mean_service_request_ms",
    "prefill_cold_to_warm_ratio",
}

MINIMUMS = {
    "max_cache_hit_prefill_tokens": 16.0,
    "max_cache_create_prepare_share": 0.50,
    "min_cache_hit_speedup_vs_full_prefill": 2.0,
    "min_cache_hit_prefill_reduction_vs_full_prefill": 0.80,
}


def load_gate(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text())
    if payload.get("type") != "resident_regression_gate":
        raise ValueError(f"{path}: expected resident_regression_gate")
    return payload


def measured_checks(paths: list[Path]) -> dict[str, list[float]]:
    values: dict[str, list[float]] = {}
    for path in paths:
        report = load_gate(path)
        for check in report.get("checks", []):
            label = check.get("label")
            actual = check.get("actual")
            if label not in CHECK_TO_FLAG:
                continue
            if isinstance(actual, bool) or not isinstance(actual, (int, float)):
                continue
            values.setdefault(label, []).append(float(actual))
    return values


def calibrate(
    values: dict[str, list[float]],
    *,
    high_headroom: float,
    low_headroom: float,
) -> dict[str, Any]:
    thresholds: dict[str, float] = {}
    details: dict[str, dict[str, float | int]] = {}
    for label, measured in sorted(values.items()):
        flag = CHECK_TO_FLAG[label]
        baseline = max(measured) if label in LOWER_IS_BETTER else min(measured)
        if label in LOWER_IS_BETTER:
            threshold = baseline * high_headroom
        else:
            threshold = baseline * low_headroom
        if flag in MINIMUMS:
            if label in LOWER_IS_BETTER:
                threshold = max(threshold, MINIMUMS[flag])
            else:
                threshold = max(threshold, MINIMUMS[flag])
        thresholds[flag] = threshold
        details[label] = {
            "count": len(measured),
            "mean": statistics.fmean(measured),
            "baseline": baseline,
            "threshold": threshold,
        }
    return {
        "type": "resident_threshold_calibration",
        "thresholds": thresholds,
        "details": details,
    }


def flag_name(name: str) -> str:
    return "--" + name.replace("_", "-")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("gate_reports", nargs="+", type=Path)
    parser.add_argument("--output-json", type=Path)
    parser.add_argument("--high-headroom", type=float, default=1.25)
    parser.add_argument("--low-headroom", type=float, default=0.75)
    args = parser.parse_args()

    report = calibrate(
        measured_checks(args.gate_reports),
        high_headroom=args.high_headroom,
        low_headroom=args.low_headroom,
    )
    print("threshold_calibration", len(args.gate_reports), "reports")
    for name, value in sorted(report["thresholds"].items()):
        print("threshold", flag_name(name), round(value, 6))
    if args.output_json:
        args.output_json.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
