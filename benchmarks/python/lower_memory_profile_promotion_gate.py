#!/usr/bin/env python3
"""Gate lower-memory profile promotion from first-hit, memory, speed, and quality evidence."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text())


def numeric(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        return float(value)
    return None


def rows_from_repeated_context(path: Path) -> list[dict[str, Any]]:
    payload = load_json(path)
    rows = payload.get("rows")
    if not isinstance(rows, list):
        raise ValueError(f"repeated-context artifact has no rows list: {path}")
    return rows


def engine_metrics(row: dict[str, Any]) -> dict[str, Any]:
    metrics = row.get("engine_metrics")
    return metrics if isinstance(metrics, dict) else {}


def check(
    checks: list[dict[str, Any]],
    *,
    label: str,
    actual: Any,
    operator: str,
    threshold: Any,
    passed: bool,
) -> None:
    checks.append(
        {
            "label": label,
            "actual": actual,
            "operator": operator,
            "threshold": threshold,
            "verdict": "PASS" if passed else "FAIL",
        }
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repeated-context-json", type=Path, required=True)
    parser.add_argument("--conversion-gate-json", type=Path, required=True)
    parser.add_argument("--quality-threshold-json", type=Path, required=True)
    parser.add_argument("--output-json", type=Path, required=True)
    parser.add_argument("--tag", default="m230-lower-memory-profile-promotion")
    parser.add_argument("--max-active-memory-gb", type=float, default=10.0)
    parser.add_argument("--max-peak-memory-gb", type=float, default=10.0)
    parser.add_argument("--max-first-duplicate-service-ms", type=float, default=250.0)
    parser.add_argument("--max-first-duplicate-prefill-tokens", type=float, default=32.0)
    parser.add_argument("--max-conversion-ratio", type=float, default=0.20)
    parser.add_argument("--min-mature-hit-speedup", type=float, default=5.0)
    parser.add_argument("--require-proactive-prefix-cache", action="store_true")
    parser.add_argument("--fail-on-fail", action="store_true")
    args = parser.parse_args()

    rows = rows_from_repeated_context(args.repeated_context_json)
    conversion_gate = load_json(args.conversion_gate_json)
    quality = load_json(args.quality_threshold_json)
    derived = conversion_gate.get("derived") or {}

    active_memory_values = [
        value
        for row in rows
        if (value := numeric(engine_metrics(row).get("active_memory_gb"))) is not None
    ]
    peak_memory_values = [
        value
        for row in rows
        if (value := numeric(engine_metrics(row).get("peak_memory_gb"))) is not None
    ]
    first_duplicate = rows[1] if len(rows) > 1 else {}
    first_duplicate_metrics = engine_metrics(first_duplicate)
    first_duplicate_service = numeric(
        first_duplicate_metrics.get("service_request_ms")
        or first_duplicate.get("service_request_ms")
    )
    first_duplicate_prefill = numeric(first_duplicate_metrics.get("actual_prefill_tokens"))
    first_duplicate_hit = bool(first_duplicate_metrics.get("cache_hit"))
    first_duplicate_created = bool(first_duplicate_metrics.get("cache_created"))
    first_request_metrics = engine_metrics(rows[0]) if rows else {}
    proactive_created = numeric(first_request_metrics.get("proactive_prefix_cache_created"))

    checks: list[dict[str, Any]] = []
    max_active_memory = max(active_memory_values) if active_memory_values else None
    max_peak_memory = max(peak_memory_values) if peak_memory_values else None
    conversion_ratio = numeric(derived.get("conversion_ratio_vs_baseline"))
    mature_hit_speedup = numeric(derived.get("mature_hit_speedup_vs_baseline"))

    check(
        checks,
        label="quality_threshold_verdict",
        actual=quality.get("verdict"),
        operator="==",
        threshold="PASS",
        passed=quality.get("verdict") == "PASS",
    )
    check(
        checks,
        label="quality_threshold_readiness",
        actual=quality.get("readiness"),
        operator="==",
        threshold="ci-quality-ready",
        passed=quality.get("readiness") == "ci-quality-ready",
    )
    check(
        checks,
        label="conversion_gate_verdict",
        actual=conversion_gate.get("verdict"),
        operator="==",
        threshold="PASS",
        passed=conversion_gate.get("verdict") == "PASS",
    )
    check(
        checks,
        label="max_active_memory_gb",
        actual=max_active_memory,
        operator="<=",
        threshold=args.max_active_memory_gb,
        passed=max_active_memory is not None
        and max_active_memory <= args.max_active_memory_gb,
    )
    check(
        checks,
        label="max_peak_memory_gb",
        actual=max_peak_memory,
        operator="<=",
        threshold=args.max_peak_memory_gb,
        passed=max_peak_memory is not None and max_peak_memory <= args.max_peak_memory_gb,
    )
    check(
        checks,
        label="first_duplicate_service_ms",
        actual=first_duplicate_service,
        operator="<=",
        threshold=args.max_first_duplicate_service_ms,
        passed=first_duplicate_service is not None
        and first_duplicate_service <= args.max_first_duplicate_service_ms,
    )
    check(
        checks,
        label="first_duplicate_prefill_tokens",
        actual=first_duplicate_prefill,
        operator="<=",
        threshold=args.max_first_duplicate_prefill_tokens,
        passed=first_duplicate_prefill is not None
        and first_duplicate_prefill <= args.max_first_duplicate_prefill_tokens,
    )
    check(
        checks,
        label="first_duplicate_cache_hit",
        actual=first_duplicate_hit,
        operator="==",
        threshold=True,
        passed=first_duplicate_hit,
    )
    check(
        checks,
        label="first_duplicate_cache_created",
        actual=first_duplicate_created,
        operator="==",
        threshold=False,
        passed=not first_duplicate_created,
    )
    check(
        checks,
        label="conversion_ratio_vs_baseline",
        actual=conversion_ratio,
        operator="<=",
        threshold=args.max_conversion_ratio,
        passed=conversion_ratio is not None and conversion_ratio <= args.max_conversion_ratio,
    )
    check(
        checks,
        label="mature_hit_speedup_vs_baseline",
        actual=mature_hit_speedup,
        operator=">=",
        threshold=args.min_mature_hit_speedup,
        passed=mature_hit_speedup is not None
        and mature_hit_speedup >= args.min_mature_hit_speedup,
    )
    if args.require_proactive_prefix_cache:
        check(
            checks,
            label="proactive_prefix_cache_created",
            actual=proactive_created,
            operator=">=",
            threshold=1,
            passed=proactive_created is not None and proactive_created >= 1,
        )

    failures = [check for check in checks if check["verdict"] != "PASS"]
    output = {
        "type": "lower_memory_profile_promotion_gate",
        "tag": args.tag,
        "verdict": "PASS" if not failures else "FAIL",
        "readiness": (
            "lower-memory-profile-promotable"
            if not failures
            else "lower-memory-profile-blocked"
        ),
        "model": first_request_metrics.get("model"),
        "inputs": {
            "repeated_context_json": str(args.repeated_context_json),
            "conversion_gate_json": str(args.conversion_gate_json),
            "quality_threshold_json": str(args.quality_threshold_json),
        },
        "thresholds": {
            "max_active_memory_gb": args.max_active_memory_gb,
            "max_peak_memory_gb": args.max_peak_memory_gb,
            "max_first_duplicate_service_ms": args.max_first_duplicate_service_ms,
            "max_first_duplicate_prefill_tokens": (
                args.max_first_duplicate_prefill_tokens
            ),
            "max_conversion_ratio": args.max_conversion_ratio,
            "min_mature_hit_speedup": args.min_mature_hit_speedup,
            "require_proactive_prefix_cache": args.require_proactive_prefix_cache,
        },
        "metrics": {
            "max_active_memory_gb": max_active_memory,
            "max_peak_memory_gb": max_peak_memory,
            "first_duplicate_service_ms": first_duplicate_service,
            "first_duplicate_prefill_tokens": first_duplicate_prefill,
            "first_duplicate_cache_hit": first_duplicate_hit,
            "first_duplicate_cache_created": first_duplicate_created,
            "conversion_ratio_vs_baseline": conversion_ratio,
            "mature_hit_speedup_vs_baseline": mature_hit_speedup,
            "proactive_prefix_cache_created": proactive_created,
        },
        "quality": {
            "verdict": quality.get("verdict"),
            "readiness": quality.get("readiness"),
        },
        "checks": checks,
        "failures": failures,
    }
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n")
    print(
        "lower_memory_profile_promotion_gate",
        output["verdict"],
        output["readiness"],
        "checks",
        len(checks),
        "failures",
        len(failures),
        args.output_json,
    )
    for failure in failures:
        print("failure", failure["label"], failure["actual"], failure["operator"], failure["threshold"])
    return 1 if args.fail_on_fail and failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
