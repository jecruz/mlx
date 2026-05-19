#!/usr/bin/env python3
"""Gate first duplicate-request conversion in Dax repeated-context reports."""

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


def numeric(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


def check(
    checks: list[dict[str, Any]],
    failures: list[str],
    *,
    label: str,
    actual: float | int | str | bool | None,
    operator: str,
    threshold: float | int | str | bool,
) -> None:
    if operator == "==":
        verdict = "PASS" if actual == threshold else "FAIL"
    elif actual is None:
        verdict = "FAIL"
    elif operator == ">=":
        verdict = "PASS" if float(actual) >= float(threshold) else "FAIL"
    elif operator == "<=":
        verdict = "PASS" if float(actual) <= float(threshold) else "FAIL"
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
        failures.append(f"{label}: {actual!r} {operator} {threshold!r} failed")


def first_conversion(rows: list[dict[str, Any]], max_prefill_tokens: int) -> dict[str, Any] | None:
    for row in rows[1:]:
        prefill = numeric(row.get("actual_prefill_tokens"))
        metrics = row.get("engine_metrics") or {}
        converted = bool(
            row.get("cache_hit")
            or metrics.get("cache_created")
            or metrics.get("cache_split_prefill")
            or metrics.get("cache_stored_from_request")
        )
        if converted and prefill is not None and prefill <= max_prefill_tokens:
            return row
    return None


def first_mature_hit(rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    return next((row for row in rows[1:] if row.get("cache_hit")), None)


def gate(report: dict[str, Any], args: argparse.Namespace) -> dict[str, Any]:
    rows = list(report.get("rows") or [])
    baseline = rows[0] if rows else None
    conversion = first_conversion(rows, args.max_conversion_prefill_tokens)
    mature_hit = first_mature_hit(rows)
    checks: list[dict[str, Any]] = []
    failures: list[str] = []
    if report.get("verdict") != "PASS":
        failures.append(f"source verdict was {report.get('verdict')!r}")
    if baseline is None:
        failures.append("missing baseline row")
    if conversion is None:
        failures.append("missing first conversion row")
    if mature_hit is None:
        failures.append("missing mature cache-hit row")

    baseline_ms = numeric((baseline or {}).get("service_request_ms"))
    conversion_ms = numeric((conversion or {}).get("service_request_ms"))
    conversion_prefill = numeric((conversion or {}).get("actual_prefill_tokens"))
    conversion_turn = (conversion or {}).get("turn")
    conversion_ratio = (
        conversion_ms / baseline_ms
        if conversion_ms is not None and baseline_ms is not None and baseline_ms > 0
        else None
    )
    mature_ms = numeric((mature_hit or {}).get("service_request_ms"))
    mature_prefill = numeric((mature_hit or {}).get("actual_prefill_tokens"))
    mature_speedup = (
        baseline_ms / mature_ms
        if baseline_ms is not None and mature_ms is not None and mature_ms > 0
        else None
    )
    conversion_metrics = (conversion or {}).get("engine_metrics") or {}
    conversion_path_ok = (
        True
        if args.conversion_path == "any"
        else bool(conversion_metrics.get("cache_split_prefill"))
    )

    check(
        checks,
        failures,
        label="conversion_turn",
        actual=conversion_turn,
        operator="==",
        threshold=args.expected_conversion_turn,
    )
    check(
        checks,
        failures,
        label="conversion_actual_prefill_tokens",
        actual=conversion_prefill,
        operator="<=",
        threshold=args.max_conversion_prefill_tokens,
    )
    check(
        checks,
        failures,
        label="conversion_service_ratio_vs_baseline",
        actual=conversion_ratio,
        operator="<=",
        threshold=args.max_conversion_ratio,
    )
    check(
        checks,
        failures,
        label="conversion_path",
        actual=conversion_path_ok,
        operator="==",
        threshold=True,
    )
    check(
        checks,
        failures,
        label="mature_hit_speedup_vs_baseline",
        actual=mature_speedup,
        operator=">=",
        threshold=args.min_mature_hit_speedup,
    )
    check(
        checks,
        failures,
        label="mature_hit_actual_prefill_tokens",
        actual=mature_prefill,
        operator="<=",
        threshold=args.max_mature_hit_prefill_tokens,
    )

    return {
        "type": "dax_first_hit_conversion_gate",
        "verdict": "PASS" if not failures else "FAIL",
        "source_verdict": report.get("verdict"),
        "source_output_jsonl": report.get("output_jsonl"),
        "checks": checks,
        "failures": failures,
        "baseline": baseline,
        "first_conversion": conversion,
        "first_mature_hit": mature_hit,
        "derived": {
            "baseline_service_request_ms": baseline_ms,
            "conversion_service_request_ms": conversion_ms,
            "conversion_ratio_vs_baseline": conversion_ratio,
            "conversion_actual_prefill_tokens": conversion_prefill,
            "conversion_turn": conversion_turn,
            "mature_hit_service_request_ms": mature_ms,
            "mature_hit_speedup_vs_baseline": mature_speedup,
            "mature_hit_actual_prefill_tokens": mature_prefill,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("repeated_context_report", type=Path)
    parser.add_argument("--output-json", type=Path)
    parser.add_argument("--expected-conversion-turn", type=int, default=2)
    parser.add_argument("--max-conversion-prefill-tokens", type=int, default=32)
    parser.add_argument("--max-conversion-ratio", type=float, default=0.85)
    parser.add_argument(
        "--conversion-path",
        choices=("split-prefill", "any"),
        default="split-prefill",
    )
    parser.add_argument("--min-mature-hit-speedup", type=float, default=2.0)
    parser.add_argument("--max-mature-hit-prefill-tokens", type=int, default=32)
    parser.add_argument("--fail-on-fail", action="store_true")
    args = parser.parse_args()

    report = gate(load_report(args.repeated_context_report), args)
    for item in report["checks"]:
        print(
            "dax_first_hit_conversion_gate_check",
            item["verdict"],
            item["label"],
            item["actual"],
            item["operator"],
            item["threshold"],
        )
    for failure in report["failures"]:
        print("dax_first_hit_conversion_gate_failure", failure)
    print("dax_first_hit_conversion_gate_result", report["verdict"])
    if args.output_json:
        args.output_json.parent.mkdir(parents=True, exist_ok=True)
        args.output_json.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    return 1 if args.fail_on_fail and report["verdict"] != "PASS" else 0


if __name__ == "__main__":
    raise SystemExit(main())
