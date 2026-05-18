#!/usr/bin/env python3
"""Gate runtime profile comparison reports on cache-create regression signals."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def load_report(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text())
    if payload.get("type") != "runtime_profile_comparison_suite":
        raise ValueError(f"{path}: expected runtime_profile_comparison_suite")
    return payload


def check(
    checks: list[dict[str, Any]],
    failures: list[str],
    *,
    label: str,
    actual: float | None,
    operator: str,
    threshold: float,
) -> None:
    if actual is None:
        verdict = "SKIP"
    elif operator == "<=":
        verdict = "PASS" if actual <= threshold else "FAIL"
    elif operator == ">=":
        verdict = "PASS" if actual >= threshold else "FAIL"
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
        failures.append(f"{label}: {actual:.6f} {operator} {threshold:.6f} failed")


def selected_results(report: dict[str, Any], include_presets: set[str] | None) -> list[dict[str, Any]]:
    results = report.get("results") or []
    if include_presets is None:
        return results
    return [result for result in results if result.get("preset") in include_presets]


def gate(report: dict[str, Any], args: argparse.Namespace) -> dict[str, Any]:
    include = (
        {preset.strip() for preset in args.include_presets.split(",") if preset.strip()}
        if args.include_presets
        else None
    )
    failures: list[str] = []
    checks: list[dict[str, Any]] = []
    skipped: list[str] = []
    for result in selected_results(report, include):
        preset = result.get("preset") or "unknown"
        probe = (
            ((result.get("artifacts") or {}).get("cache_create_probe") or {}).get(
                "report"
            )
            or {}
        )
        verdict = probe.get("verdict")
        if verdict == "SKIP":
            skipped.append(preset)
            if not args.allow_skip:
                failures.append(f"{preset}: cache-create probe skipped")
            continue
        if verdict not in {"PASS", "FAIL"}:
            failures.append(f"{preset}: missing cache-create probe report")
            continue
        derived = probe.get("derived") or {}
        check(
            checks,
            failures,
            label=f"{preset}.cache_create_prepare_share",
            actual=derived.get("cache_create_prepare_share"),
            operator="<=",
            threshold=args.max_prepare_share,
        )
        check(
            checks,
            failures,
            label=f"{preset}.estimated_deferred_cache_create_service_ms",
            actual=derived.get("estimated_deferred_cache_create_service_ms"),
            operator="<=",
            threshold=args.max_deferred_service_ms,
        )
        check(
            checks,
            failures,
            label=f"{preset}.cache_create_service_ratio_vs_cache_hit",
            actual=derived.get("cache_create_service_ratio_vs_cache_hit"),
            operator="<=",
            threshold=args.max_create_hit_ratio,
        )
        check(
            checks,
            failures,
            label=f"{preset}.cache_hit_speedup_vs_full_prefill",
            actual=derived.get("cache_hit_speedup_vs_full_prefill"),
            operator=">=",
            threshold=args.min_hit_speedup,
        )
    return {
        "type": "runtime_profile_comparison_gate",
        "verdict": "PASS" if not failures else "FAIL",
        "source_tag": report.get("tag"),
        "include_presets": sorted(include) if include is not None else None,
        "allow_skip": args.allow_skip,
        "checks": checks,
        "skipped_presets": skipped,
        "failures": failures,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("comparison_report", type=Path)
    parser.add_argument("--output-json", type=Path)
    parser.add_argument("--include-presets")
    parser.add_argument("--allow-skip", action="store_true")
    parser.add_argument("--max-prepare-share", type=float, default=0.60)
    parser.add_argument("--max-deferred-service-ms", type=float, default=300.0)
    parser.add_argument("--max-create-hit-ratio", type=float, default=2.0)
    parser.add_argument("--min-hit-speedup", type=float, default=2.0)
    parser.add_argument("--fail-on-fail", action="store_true")
    args = parser.parse_args()

    report = gate(load_report(args.comparison_report), args)
    for item in report["checks"]:
        print(
            "profile_gate_check",
            item["verdict"],
            item["label"],
            item["actual"],
            item["operator"],
            item["threshold"],
        )
    for preset in report["skipped_presets"]:
        print("profile_gate_skip", preset)
    for failure in report["failures"]:
        print("profile_gate_failure", failure)
    print("profile_gate_result", report["verdict"])
    if args.output_json:
        args.output_json.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    return 1 if args.fail_on_fail and report["verdict"] != "PASS" else 0


if __name__ == "__main__":
    raise SystemExit(main())
