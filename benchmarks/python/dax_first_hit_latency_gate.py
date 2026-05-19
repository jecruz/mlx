#!/usr/bin/env python3
"""Gate the pre-hit latency shape in Dax repeated-context reports."""

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


def first_scheduled_before_hit(rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    for row in rows[1:]:
        if row.get("cache_hit"):
            return None
        if row.get("cache_scheduled"):
            return row
    return None


def first_hit(rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    return next((row for row in rows[1:] if row.get("cache_hit")), None)


def gate(report: dict[str, Any], args: argparse.Namespace) -> dict[str, Any]:
    rows = list(report.get("rows") or [])
    baseline = rows[0] if rows else None
    schedule = first_scheduled_before_hit(rows)
    hit = first_hit(rows)
    checks: list[dict[str, Any]] = []
    failures: list[str] = []
    if report.get("verdict") != "PASS":
        failures.append(f"source verdict was {report.get('verdict')!r}")
    if baseline is None:
        failures.append("missing baseline row")
    if schedule is None:
        failures.append("missing scheduled pre-hit row")
    if hit is None:
        failures.append("missing first cache-hit row")

    baseline_ms = numeric((baseline or {}).get("service_request_ms"))
    schedule_ms = numeric((schedule or {}).get("service_request_ms"))
    schedule_prefill = numeric((schedule or {}).get("actual_prefill_tokens"))
    hit_ms = numeric((hit or {}).get("service_request_ms"))
    hit_prefill = numeric((hit or {}).get("actual_prefill_tokens"))
    schedule_ratio = (
        schedule_ms / baseline_ms
        if schedule_ms is not None and baseline_ms is not None and baseline_ms > 0
        else None
    )
    hit_speedup = (
        baseline_ms / hit_ms
        if baseline_ms is not None and hit_ms is not None and hit_ms > 0
        else None
    )

    check(
        checks,
        failures,
        label="scheduled_pre_hit_service_request_ms",
        actual=schedule_ms,
        operator="<=",
        threshold=args.max_scheduled_pre_hit_ms,
    )
    check(
        checks,
        failures,
        label="scheduled_pre_hit_ratio_vs_baseline",
        actual=schedule_ratio,
        operator="<=",
        threshold=args.max_scheduled_pre_hit_ratio,
    )
    check(
        checks,
        failures,
        label="scheduled_pre_hit_actual_prefill_tokens",
        actual=schedule_prefill,
        operator=">=",
        threshold=args.min_scheduled_pre_hit_prefill_tokens,
    )
    check(
        checks,
        failures,
        label="first_hit_speedup_vs_baseline",
        actual=hit_speedup,
        operator=">=",
        threshold=args.min_first_hit_speedup,
    )
    check(
        checks,
        failures,
        label="first_hit_actual_prefill_tokens",
        actual=hit_prefill,
        operator="<=",
        threshold=args.max_first_hit_prefill_tokens,
    )

    return {
        "type": "dax_first_hit_latency_gate",
        "verdict": "PASS" if not failures else "FAIL",
        "source_verdict": report.get("verdict"),
        "source_output_jsonl": report.get("output_jsonl"),
        "checks": checks,
        "failures": failures,
        "baseline": baseline,
        "scheduled_pre_hit": schedule,
        "first_hit": hit,
        "derived": {
            "scheduled_pre_hit_service_request_ms": schedule_ms,
            "scheduled_pre_hit_ratio_vs_baseline": schedule_ratio,
            "scheduled_pre_hit_actual_prefill_tokens": schedule_prefill,
            "first_hit_service_request_ms": hit_ms,
            "first_hit_speedup_vs_baseline": hit_speedup,
            "first_hit_actual_prefill_tokens": hit_prefill,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("repeated_context_report", type=Path)
    parser.add_argument("--output-json", type=Path)
    parser.add_argument("--max-scheduled-pre-hit-ms", type=float, default=1600.0)
    parser.add_argument("--max-scheduled-pre-hit-ratio", type=float, default=0.50)
    parser.add_argument("--min-scheduled-pre-hit-prefill-tokens", type=int, default=512)
    parser.add_argument("--min-first-hit-speedup", type=float, default=2.0)
    parser.add_argument("--max-first-hit-prefill-tokens", type=int, default=32)
    parser.add_argument("--fail-on-fail", action="store_true")
    args = parser.parse_args()

    report = gate(load_report(args.repeated_context_report), args)
    for item in report["checks"]:
        print(
            "dax_first_hit_latency_gate_check",
            item["verdict"],
            item["label"],
            item["actual"],
            item["operator"],
            item["threshold"],
        )
    for failure in report["failures"]:
        print("dax_first_hit_latency_gate_failure", failure)
    print("dax_first_hit_latency_gate_result", report["verdict"])
    if args.output_json:
        args.output_json.parent.mkdir(parents=True, exist_ok=True)
        args.output_json.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    return 1 if args.fail_on_fail and report["verdict"] != "PASS" else 0


if __name__ == "__main__":
    raise SystemExit(main())
