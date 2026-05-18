#!/usr/bin/env python3
"""Gate Dax repeated-context benchmark reports."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def load_report(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text())
    if payload.get("type") != "dax_repeated_context_bench":
        raise ValueError(f"{path}: expected dax_repeated_context_bench")
    return payload


def check(
    checks: list[dict[str, Any]],
    failures: list[str],
    *,
    label: str,
    actual: float | int | None,
    operator: str,
    threshold: float,
) -> None:
    if actual is None:
        verdict = "FAIL"
    elif operator == ">=":
        verdict = "PASS" if actual >= threshold else "FAIL"
    elif operator == "<=":
        verdict = "PASS" if actual <= threshold else "FAIL"
    else:
        raise ValueError(f"unsupported operator: {operator}")
    checks.append(
        {
            "label": label,
            "actual": actual,
            "operator": operator,
            "threshold": threshold,
            "verdict": verdict,
        }
    )
    if verdict == "FAIL":
        failures.append(f"{label}: {actual!r} {operator} {threshold} failed")


def row_value(report: dict[str, Any], row_key: str, value_key: str) -> Any:
    row = report.get(row_key) or {}
    return row.get(value_key)


def gate(report: dict[str, Any], args: argparse.Namespace) -> dict[str, Any]:
    failures: list[str] = []
    checks: list[dict[str, Any]] = []
    if report.get("verdict") != "PASS":
        failures.append(f"source verdict was {report.get('verdict')!r}")

    check(
        checks,
        failures,
        label="hit_count",
        actual=report.get("hit_count"),
        operator=">=",
        threshold=args.min_hit_count,
    )
    check(
        checks,
        failures,
        label="best_hit_speedup_vs_baseline",
        actual=report.get("best_hit_speedup_vs_baseline"),
        operator=">=",
        threshold=args.min_speedup,
    )
    check(
        checks,
        failures,
        label="baseline_actual_prefill_tokens",
        actual=row_value(report, "baseline", "actual_prefill_tokens"),
        operator=">=",
        threshold=args.min_baseline_prefill_tokens,
    )
    check(
        checks,
        failures,
        label="best_hit_actual_prefill_tokens",
        actual=row_value(report, "best_hit", "actual_prefill_tokens"),
        operator="<=",
        threshold=args.max_hit_prefill_tokens,
    )
    check(
        checks,
        failures,
        label="best_hit_service_request_ms",
        actual=report.get("best_hit_service_request_ms"),
        operator="<=",
        threshold=args.max_hit_service_ms,
    )
    return {
        "type": "dax_repeated_context_gate",
        "verdict": "PASS" if not failures else "FAIL",
        "source_verdict": report.get("verdict"),
        "source_output_jsonl": report.get("output_jsonl"),
        "checks": checks,
        "failures": failures,
        "baseline": report.get("baseline"),
        "best_hit": report.get("best_hit"),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("repeated_context_report", type=Path)
    parser.add_argument("--output-json", type=Path)
    parser.add_argument("--min-hit-count", type=int, default=1)
    parser.add_argument("--min-speedup", type=float, default=2.0)
    parser.add_argument("--min-baseline-prefill-tokens", type=int, default=512)
    parser.add_argument("--max-hit-prefill-tokens", type=int, default=32)
    parser.add_argument("--max-hit-service-ms", type=float, default=400.0)
    parser.add_argument("--fail-on-fail", action="store_true")
    args = parser.parse_args()

    report = gate(load_report(args.repeated_context_report), args)
    for item in report["checks"]:
        print(
            "dax_repeated_context_gate_check",
            item["verdict"],
            item["label"],
            item["actual"],
            item["operator"],
            item["threshold"],
        )
    for failure in report["failures"]:
        print("dax_repeated_context_gate_failure", failure)
    print("dax_repeated_context_gate_result", report["verdict"])
    if args.output_json:
        args.output_json.parent.mkdir(parents=True, exist_ok=True)
        args.output_json.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    return 1 if args.fail_on_fail and report["verdict"] != "PASS" else 0


if __name__ == "__main__":
    raise SystemExit(main())
