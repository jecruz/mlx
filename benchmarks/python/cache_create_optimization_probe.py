#!/usr/bin/env python3
"""Analyze cache-create overhead from prefix latency sweep JSONL."""

from __future__ import annotations

import argparse
import json
import statistics
from pathlib import Path
from typing import Any


def load_rows(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line_no, line in enumerate(path.read_text().splitlines(), start=1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{path}:{line_no}: invalid JSON: {exc}") from exc
        if isinstance(row, dict) and "phase" in row:
            rows.append(row)
    return rows


def numeric(row: dict[str, Any], key: str) -> float | None:
    value = row.get(key)
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


def mean(rows: list[dict[str, Any]], key: str) -> float | None:
    values = [value for row in rows if (value := numeric(row, key)) is not None]
    return statistics.fmean(values) if values else None


def require_mean(rows: list[dict[str, Any]], key: str, phase: str) -> float:
    value = mean(rows, key)
    if value is None:
        raise ValueError(f"phase {phase} has no numeric {key}")
    return value


def phase_rows(rows: list[dict[str, Any]], phase: str) -> list[dict[str, Any]]:
    return [row for row in rows if row.get("phase") == phase]


def analyze(
    rows: list[dict[str, Any]],
    *,
    min_prepare_share: float,
    min_hit_speedup: float,
) -> dict[str, Any]:
    full = phase_rows(rows, "full_prefill")
    create = phase_rows(rows, "cache_create")
    hit = phase_rows(rows, "cache_hit")
    if not full:
        raise ValueError("missing full_prefill rows")
    if not create:
        raise ValueError("missing cache_create rows")
    if not hit:
        raise ValueError("missing cache_hit rows")

    full_service = require_mean(full, "service_request_ms", "full_prefill")
    create_service = require_mean(create, "service_request_ms", "cache_create")
    create_prepare = require_mean(create, "cache_prepare_ms", "cache_create")
    create_run = require_mean(create, "run_ms", "cache_create")
    hit_service = require_mean(hit, "service_request_ms", "cache_hit")
    hit_prepare = require_mean(hit, "cache_prepare_ms", "cache_hit")

    prepare_share = create_prepare / create_service if create_service > 0 else 0.0
    hit_speedup = full_service / hit_service if hit_service > 0 else 0.0
    create_vs_hit_ratio = create_service / hit_service if hit_service > 0 else 0.0
    estimated_deferred_create_ms = max(create_service - create_prepare, 0.0)
    estimated_deferred_speedup = (
        create_service / estimated_deferred_create_ms
        if estimated_deferred_create_ms > 0
        else 0.0
    )
    failures = []
    if prepare_share < min_prepare_share:
        failures.append(
            f"cache_create prepare share {prepare_share:.3f} < {min_prepare_share:.3f}"
        )
    if hit_speedup < min_hit_speedup:
        failures.append(f"cache_hit speedup {hit_speedup:.3f} < {min_hit_speedup:.3f}")

    return {
        "type": "cache_create_optimization_probe",
        "verdict": "PASS" if not failures else "FAIL",
        "failures": failures,
        "counts": {
            "full_prefill": len(full),
            "cache_create": len(create),
            "cache_hit": len(hit),
        },
        "means": {
            "full_prefill_service_request_ms": full_service,
            "cache_create_service_request_ms": create_service,
            "cache_create_prepare_ms": create_prepare,
            "cache_create_run_ms": create_run,
            "cache_hit_service_request_ms": hit_service,
            "cache_hit_prepare_ms": hit_prepare,
        },
        "derived": {
            "cache_create_prepare_share": prepare_share,
            "cache_hit_speedup_vs_full_prefill": hit_speedup,
            "cache_create_service_ratio_vs_cache_hit": create_vs_hit_ratio,
            "estimated_deferred_cache_create_service_ms": estimated_deferred_create_ms,
            "estimated_deferred_cache_create_speedup": estimated_deferred_speedup,
        },
        "recommendation": (
            "Prioritize moving cache creation off the foreground request path."
            if prepare_share >= min_prepare_share
            else "Cache creation is not dominated by prepare time in this sample."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("jsonl", type=Path)
    parser.add_argument("--output-json", type=Path)
    parser.add_argument("--min-prepare-share", type=float, default=0.50)
    parser.add_argument("--min-hit-speedup", type=float, default=2.0)
    parser.add_argument("--fail-on-fail", action="store_true")
    args = parser.parse_args()

    report = analyze(
        load_rows(args.jsonl),
        min_prepare_share=args.min_prepare_share,
        min_hit_speedup=args.min_hit_speedup,
    )
    print(
        "cache_create_probe",
        report["verdict"],
        "prepare_share",
        round(report["derived"]["cache_create_prepare_share"], 3),
        "hit_speedup",
        round(report["derived"]["cache_hit_speedup_vs_full_prefill"], 3),
        "deferred_service_ms",
        round(report["derived"]["estimated_deferred_cache_create_service_ms"], 2),
    )
    for failure in report["failures"]:
        print("cache_create_probe_failure", failure)
    print("cache_create_probe_recommendation", report["recommendation"])
    if args.output_json:
        args.output_json.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    if args.fail_on_fail and report["verdict"] != "PASS":
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
