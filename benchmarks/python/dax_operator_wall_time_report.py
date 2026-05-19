#!/usr/bin/env python3
"""Summarize Dax operator wall time versus resident engine service time."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from statistics import mean
from typing import Any


DEFAULT_CASES = [
    (
        "m97_first_hit_direct",
        Path(
            "artifacts/m97-direct-first-hit-profile/"
            "dax-product-first-hit-summary-m97-qwen-a3b-first-hit-direct.json"
        ),
    ),
    (
        "m97_first_hit_suite",
        Path(
            "artifacts/m97-suite-first-hit-direct/"
            "dax-product-first-hit-summary-m97-qwen-a3b-first-hit-suite-direct.json"
        ),
    ),
    (
        "m98_low_memory_direct",
        Path(
            "artifacts/m98-direct-low-memory-profile/"
            "dax-product-first-hit-summary-m98-qwen-a3b-low-memory-direct.json"
        ),
    ),
    (
        "m98_low_memory_suite",
        Path(
            "artifacts/m98-suite-low-memory-direct/"
            "dax-product-first-hit-summary-m98-qwen-a3b-low-memory-suite-direct.json"
        ),
    ),
]


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text())


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line_no, line in enumerate(path.read_text().splitlines(), start=1):
        if not line.strip():
            continue
        row = json.loads(line)
        row["_line_no"] = line_no
        rows.append(row)
    return rows


def as_float(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


def row_metrics(row: dict[str, Any]) -> dict[str, Any]:
    wall_ms = as_float(row.get("wall_ms"))
    service_ms = as_float(row.get("service_request_ms"))
    overhead_ms = None
    overhead_ratio_vs_service = None
    service_share_of_wall = None
    if wall_ms is not None and service_ms is not None:
        overhead_ms = wall_ms - service_ms
        if service_ms > 0:
            overhead_ratio_vs_service = overhead_ms / service_ms
        if wall_ms > 0:
            service_share_of_wall = service_ms / wall_ms

    return {
        "turn": row.get("turn"),
        "line_no": row.get("_line_no"),
        "wall_ms": wall_ms,
        "service_request_ms": service_ms,
        "overhead_ms": overhead_ms,
        "overhead_ratio_vs_service": overhead_ratio_vs_service,
        "service_share_of_wall": service_share_of_wall,
        "actual_prefill_tokens": row.get("actual_prefill_tokens"),
        "longest_prefix_match_tokens": row.get("longest_prefix_match_tokens"),
        "cache_hit": row.get("cache_hit"),
        "cache_pending": row.get("cache_pending"),
        "cache_scheduled": row.get("cache_scheduled"),
        "finish_reason": row.get("finish_reason"),
    }


def find_turn(rows: list[dict[str, Any]], turn: int | None) -> dict[str, Any] | None:
    if turn is None:
        return None
    for row in rows:
        if row.get("turn") == turn:
            return row
    return None


def closest_service_row(rows: list[dict[str, Any]], service_ms: float | None) -> dict[str, Any] | None:
    if service_ms is None:
        return None
    candidates = [row for row in rows if as_float(row.get("service_request_ms")) is not None]
    if not candidates:
        return None
    return min(
        candidates,
        key=lambda row: abs(as_float(row.get("service_request_ms")) - service_ms),  # type: ignore[operator]
    )


def summarize_case(label: str, summary_path: Path) -> dict[str, Any]:
    summary = load_json(summary_path)
    artifacts = summary.get("artifacts") or {}
    benchmark_jsonl = Path(artifacts["benchmark_jsonl"])
    rows = load_jsonl(benchmark_jsonl)
    derived = summary.get("derived") or {}

    baseline_row = closest_service_row(rows, as_float(derived.get("baseline_service_request_ms")))
    conversion_row = find_turn(rows, int(derived["conversion_turn"]) if "conversion_turn" in derived else None)
    mature_row = closest_service_row(rows, as_float(derived.get("mature_hit_service_request_ms")))

    row_summaries = [row_metrics(row) for row in rows]
    overheads = [
        item["overhead_ms"]
        for item in row_summaries
        if isinstance(item.get("overhead_ms"), (int, float))
    ]
    service_shares = [
        item["service_share_of_wall"]
        for item in row_summaries
        if isinstance(item.get("service_share_of_wall"), (int, float))
    ]

    baseline = row_metrics(baseline_row) if baseline_row else None
    conversion = row_metrics(conversion_row) if conversion_row else None
    mature = row_metrics(mature_row) if mature_row else None

    def speedup(left: dict[str, Any] | None, right: dict[str, Any] | None, key: str) -> float | None:
        left_value = as_float(left.get(key)) if left else None
        right_value = as_float(right.get(key)) if right else None
        if left_value is None or right_value is None or right_value <= 0:
            return None
        return left_value / right_value

    return {
        "label": label,
        "summary_path": str(summary_path),
        "benchmark_jsonl": str(benchmark_jsonl),
        "verdict": summary.get("verdict"),
        "dax_profile": summary.get("dax_profile"),
        "tag": summary.get("tag"),
        "row_count": len(rows),
        "baseline": baseline,
        "conversion": conversion,
        "mature_hit": mature,
        "derived": {
            "baseline_to_conversion_service_speedup": speedup(baseline, conversion, "service_request_ms"),
            "baseline_to_conversion_wall_speedup": speedup(baseline, conversion, "wall_ms"),
            "baseline_to_mature_service_speedup": speedup(baseline, mature, "service_request_ms"),
            "baseline_to_mature_wall_speedup": speedup(baseline, mature, "wall_ms"),
            "mean_operator_overhead_ms": mean(overheads) if overheads else None,
            "mean_service_share_of_wall": mean(service_shares) if service_shares else None,
        },
        "rows": row_summaries,
    }


def parse_case(value: str) -> tuple[str, Path]:
    if "=" not in value:
        raise argparse.ArgumentTypeError("case must be label=summary.json")
    label, path = value.split("=", 1)
    if not label:
        raise argparse.ArgumentTypeError("case label cannot be empty")
    return label, Path(path)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--case",
        action="append",
        type=parse_case,
        help="Add a case as label=path/to/dax-product-first-hit-summary.json",
    )
    parser.add_argument("--output-json", type=Path, required=True)
    parser.add_argument("--tag", default="m100-qwen-a3b")
    args = parser.parse_args()

    cases = args.case or DEFAULT_CASES
    reports = [summarize_case(label, path) for label, path in cases]
    failures = [
        f"{report['label']}: verdict={report.get('verdict')}"
        for report in reports
        if report.get("verdict") != "PASS"
    ]
    output = {
        "type": "dax_operator_wall_time_report",
        "tag": args.tag,
        "verdict": "PASS" if not failures else "FAIL",
        "case_count": len(reports),
        "failures": failures,
        "cases": reports,
    }
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n")

    print(
        "dax_operator_wall_time_report",
        output["verdict"],
        "cases",
        len(reports),
        args.output_json,
        flush=True,
    )
    for report in reports:
        derived = report["derived"]
        print(
            "case",
            report["label"],
            "profile",
            report.get("dax_profile"),
            "service_speedup",
            derived.get("baseline_to_mature_service_speedup"),
            "wall_speedup",
            derived.get("baseline_to_mature_wall_speedup"),
            "mean_overhead_ms",
            derived.get("mean_operator_overhead_ms"),
            flush=True,
        )
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
