#!/usr/bin/env python3
"""Gate Dax/operator overhead from product benchmark evidence."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from statistics import mean
from typing import Any


def as_float(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


def load_rows(path: Path) -> list[dict[str, Any]]:
    if path.suffix == ".jsonl":
        return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    payload = json.loads(path.read_text())
    if payload.get("type") == "dax_operator_wall_time_report":
        rows = []
        for case in payload.get("cases", []):
            rows.extend(case.get("rows", []))
        return rows
    if "rows" in payload:
        return payload["rows"]
    raise ValueError(f"unsupported overhead input: {path}")


def overhead_for_row(row: dict[str, Any]) -> float | None:
    existing = as_float(row.get("overhead_ms"))
    if existing is not None:
        return existing
    wall_ms = as_float(row.get("wall_ms"))
    service_ms = as_float(row.get("service_request_ms"))
    if wall_ms is None or service_ms is None:
        return None
    return wall_ms - service_ms


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path)
    parser.add_argument("--output-json", type=Path, required=True)
    parser.add_argument("--tag", default="m110-qwen-a3b")
    parser.add_argument("--max-mean-overhead-ms", type=float, default=500.0)
    parser.add_argument("--max-p95-overhead-ms", type=float)
    parser.add_argument("--fail-on-fail", action="store_true")
    args = parser.parse_args()

    rows = load_rows(args.input)
    overheads = [value for row in rows if (value := overhead_for_row(row)) is not None]
    failures: list[str] = []
    if not overheads:
        failures.append("no overhead values found")

    mean_overhead = mean(overheads) if overheads else None
    sorted_overheads = sorted(overheads)
    p95_overhead = (
        sorted_overheads[min(len(sorted_overheads) - 1, int(len(sorted_overheads) * 0.95))]
        if sorted_overheads
        else None
    )
    if mean_overhead is not None and mean_overhead > args.max_mean_overhead_ms:
        failures.append(f"mean_overhead_ms {mean_overhead:.3f} > {args.max_mean_overhead_ms:.3f}")
    if (
        args.max_p95_overhead_ms is not None
        and p95_overhead is not None
        and p95_overhead > args.max_p95_overhead_ms
    ):
        failures.append(f"p95_overhead_ms {p95_overhead:.3f} > {args.max_p95_overhead_ms:.3f}")

    output = {
        "type": "dax_operator_overhead_gate",
        "tag": args.tag,
        "verdict": "PASS" if not failures else "FAIL",
        "input": str(args.input),
        "row_count": len(rows),
        "overhead_count": len(overheads),
        "thresholds": {
            "max_mean_overhead_ms": args.max_mean_overhead_ms,
            "max_p95_overhead_ms": args.max_p95_overhead_ms,
        },
        "metrics": {
            "mean_overhead_ms": mean_overhead,
            "max_overhead_ms": max(overheads) if overheads else None,
            "p95_overhead_ms": p95_overhead,
            "min_overhead_ms": min(overheads) if overheads else None,
        },
        "failures": failures,
    }
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n")
    print(
        "dax_operator_overhead_gate",
        output["verdict"],
        "rows",
        len(rows),
        "mean_overhead_ms",
        mean_overhead,
        args.output_json,
        flush=True,
    )
    for failure in failures:
        print("failure", failure, flush=True)
    return 1 if args.fail_on_fail and failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
