#!/usr/bin/env python3
"""Gate async maturation sweep reports on mature-cache reuse signals."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def load_report(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text())
    if payload.get("type") != "async_maturation_sweep":
        raise ValueError(f"{path}: expected async_maturation_sweep")
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


def best_value(report: dict[str, Any], key: str) -> Any:
    best = report.get("best") or {}
    return best.get(key)


def gate(report: dict[str, Any], args: argparse.Namespace) -> dict[str, Any]:
    failures: list[str] = []
    checks: list[dict[str, Any]] = []
    if report.get("verdict") != "PASS":
        failures.append(f"source verdict was {report.get('verdict')!r}")

    check(
        checks,
        failures,
        label="combo_count",
        actual=report.get("combo_count"),
        operator=">=",
        threshold=args.min_combos,
    )
    check(
        checks,
        failures,
        label="mature_hit_count",
        actual=report.get("mature_hit_count"),
        operator=">=",
        threshold=args.min_mature_hits,
    )
    check(
        checks,
        failures,
        label="mature_cache_hit_speedup_vs_baseline",
        actual=best_value(report, "mature_cache_hit_speedup_vs_baseline"),
        operator=">=",
        threshold=args.min_mature_speedup,
    )
    check(
        checks,
        failures,
        label="mature_hit_actual_prefill_tokens",
        actual=best_value(report, "mature_hit_actual_prefill_tokens"),
        operator="<=",
        threshold=args.max_mature_prefill_tokens,
    )
    check(
        checks,
        failures,
        label="mature_hit_service_request_ms",
        actual=best_value(report, "mature_hit_service_request_ms"),
        operator="<=",
        threshold=args.max_mature_service_ms,
    )
    if args.require_first_hit:
        check(
            checks,
            failures,
            label="hit_count",
            actual=report.get("hit_count"),
            operator=">=",
            threshold=1,
        )

    return {
        "type": "async_maturation_gate",
        "verdict": "PASS" if not failures else "FAIL",
        "source_verdict": report.get("verdict"),
        "source_output_jsonl": report.get("output_jsonl"),
        "best": report.get("best"),
        "first_hit_best": report.get("first_hit_best"),
        "checks": checks,
        "failures": failures,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("maturation_report", type=Path)
    parser.add_argument("--output-json", type=Path)
    parser.add_argument("--min-combos", type=int, default=1)
    parser.add_argument("--min-mature-hits", type=int, default=1)
    parser.add_argument("--min-mature-speedup", type=float, default=2.0)
    parser.add_argument("--max-mature-prefill-tokens", type=float, default=16.0)
    parser.add_argument("--max-mature-service-ms", type=float, default=300.0)
    parser.add_argument("--require-first-hit", action="store_true")
    parser.add_argument("--fail-on-fail", action="store_true")
    args = parser.parse_args()

    report = gate(load_report(args.maturation_report), args)
    for item in report["checks"]:
        print(
            "async_maturation_gate_check",
            item["verdict"],
            item["label"],
            item["actual"],
            item["operator"],
            item["threshold"],
        )
    for failure in report["failures"]:
        print("async_maturation_gate_failure", failure)
    print("async_maturation_gate_result", report["verdict"])
    if args.output_json:
        args.output_json.parent.mkdir(parents=True, exist_ok=True)
        args.output_json.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    return 1 if args.fail_on_fail and report["verdict"] != "PASS" else 0


if __name__ == "__main__":
    raise SystemExit(main())
