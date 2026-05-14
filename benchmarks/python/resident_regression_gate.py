#!/usr/bin/env python3
"""Regression gate for resident MLX benchmark artifacts."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


def load_rows(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        raise SystemExit(f"{path}: file not found")
    rows = []
    for line_no, line in enumerate(path.read_text().splitlines(), start=1):
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError as exc:
            raise SystemExit(f"{path}:{line_no}: invalid JSON: {exc}") from exc
    if not rows:
        raise SystemExit(f"{path}: no rows found")
    return rows


def summary_by_phase(path: Path) -> dict[str, dict[str, Any]]:
    return {
        row["phase"]: row
        for row in load_rows(path)
        if row.get("type") == "summary"
    }


def request_rows_by_phase(path: Path, phase: str) -> list[dict[str, Any]]:
    return [
        row
        for row in load_rows(path)
        if row.get("type") == "request" and row.get("phase") == phase
    ]


def require_phase(
    *,
    summaries: dict[str, dict[str, Any]],
    phase: str,
    artifact: Path,
) -> dict[str, Any]:
    row = summaries.get(phase)
    if row is None:
        raise AssertionError(f"{artifact}: missing summary phase {phase!r}")
    return row


def check_le(
    *,
    label: str,
    actual: float,
    threshold: float,
    failures: list[str],
) -> None:
    verdict = "PASS" if actual <= threshold else "FAIL"
    print("gate_check", verdict, label, round(actual, 3), "<=", threshold)
    if verdict == "FAIL":
        failures.append(f"{label}: {actual:.3f} > {threshold:.3f}")


def check_ge(
    *,
    label: str,
    actual: float,
    threshold: float,
    failures: list[str],
) -> None:
    verdict = "PASS" if actual >= threshold else "FAIL"
    print("gate_check", verdict, label, round(actual, 3), ">=", threshold)
    if verdict == "FAIL":
        failures.append(f"{label}: {actual:.3f} < {threshold:.3f}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cache-artifact", type=Path, required=True)
    parser.add_argument("--prefill-artifact", type=Path, required=True)
    parser.add_argument("--max-cache-hit-service-ms", type=float, default=250.0)
    parser.add_argument("--max-cache-hit-prefill-tokens", type=float, default=16.0)
    parser.add_argument("--max-warm-prefill-service-ms", type=float, default=550.0)
    parser.add_argument("--min-warm-prefill-tokens", type=float, default=500.0)
    parser.add_argument("--max-cold-to-warm-ratio", type=float, default=8.0)
    args = parser.parse_args()

    failures: list[str] = []
    cache_summaries = summary_by_phase(args.cache_artifact)
    prefill_summaries = summary_by_phase(args.prefill_artifact)

    cache_hit = require_phase(
        summaries=cache_summaries,
        phase="cache_hit",
        artifact=args.cache_artifact,
    )
    warm_prefill = require_phase(
        summaries=prefill_summaries,
        phase="prefill_warm",
        artifact=args.prefill_artifact,
    )
    cold_prefill = require_phase(
        summaries=prefill_summaries,
        phase="prefill_cold",
        artifact=args.prefill_artifact,
    )

    check_le(
        label="cache_hit.mean_service_request_ms",
        actual=float(cache_hit["mean_service_request_ms"]),
        threshold=args.max_cache_hit_service_ms,
        failures=failures,
    )
    check_le(
        label="cache_hit.mean_actual_prefill_tokens",
        actual=float(cache_hit["mean_actual_prefill_tokens"]),
        threshold=args.max_cache_hit_prefill_tokens,
        failures=failures,
    )
    check_le(
        label="prefill_warm.mean_service_request_ms",
        actual=float(warm_prefill["mean_service_request_ms"]),
        threshold=args.max_warm_prefill_service_ms,
        failures=failures,
    )
    check_ge(
        label="prefill_warm.mean_actual_prefill_tokens",
        actual=float(warm_prefill["mean_actual_prefill_tokens"]),
        threshold=args.min_warm_prefill_tokens,
        failures=failures,
    )

    cold_to_warm = float(cold_prefill["mean_service_request_ms"]) / float(
        warm_prefill["mean_service_request_ms"]
    )
    check_le(
        label="prefill_cold_to_warm_ratio",
        actual=cold_to_warm,
        threshold=args.max_cold_to_warm_ratio,
        failures=failures,
    )

    cache_hit_requests = request_rows_by_phase(args.cache_artifact, "cache_hit")
    bad_cache_rows = [
        row
        for row in cache_hit_requests
        if not row.get("cache_hit")
        or not row.get("cache_reuse_enabled")
        or float(row.get("actual_prefill_tokens") or 0) > args.max_cache_hit_prefill_tokens
    ]
    print(
        "gate_check",
        "PASS" if not bad_cache_rows else "FAIL",
        "cache_hit_rows_reuse_suffix",
        len(cache_hit_requests) - len(bad_cache_rows),
        "/",
        len(cache_hit_requests),
    )
    if bad_cache_rows:
        failures.append(f"cache_hit rows failed suffix reuse: {len(bad_cache_rows)}")

    warm_rows = request_rows_by_phase(args.prefill_artifact, "prefill_warm")
    bad_warm_rows = [
        row
        for row in warm_rows
        if row.get("cache_reuse_enabled")
        or float(row.get("actual_prefill_tokens") or 0) < args.min_warm_prefill_tokens
    ]
    print(
        "gate_check",
        "PASS" if not bad_warm_rows else "FAIL",
        "prefill_warm_rows_no_cache_full_prefill",
        len(warm_rows) - len(bad_warm_rows),
        "/",
        len(warm_rows),
    )
    if bad_warm_rows:
        failures.append(f"prefill_warm rows failed full-prefill isolation: {len(bad_warm_rows)}")

    if failures:
        print("gate_result FAIL")
        for failure in failures:
            print("gate_failure", failure)
        return 1

    print("gate_result PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
