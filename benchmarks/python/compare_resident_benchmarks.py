#!/usr/bin/env python3
"""Compare resident benchmark JSONL artifacts by phase."""

from __future__ import annotations

import argparse
import json
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
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise SystemExit(f"{path}:{line_no}: invalid JSON: {exc}") from exc
        rows.append(row)
    if not rows:
        raise SystemExit(f"{path}: no rows found")
    return rows


def artifact_summary(path: Path) -> dict[str, Any]:
    rows = load_rows(path)
    health_start = next((row for row in rows if row.get("type") == "health_start"), {})
    request_rows = [row for row in rows if row.get("type") == "request"]
    phase_rows = {
        row["phase"]: row
        for row in rows
        if row.get("type") == "summary"
    }
    return {
        "path": path,
        "run_id": rows[0].get("run_id"),
        "engine_preset": health_start.get("engine_preset"),
        "population_mode": (
            health_start.get("prefix_cache_policy", {}).get("population_mode")
        ),
        "cache_max_entries": (
            health_start.get("prefix_kv_cache", {}).get("max_entries")
        ),
        "memory_limit_bytes": (
            health_start.get("prefix_cache_policy", {}).get("memory_limit_bytes")
        ),
        "request_count": len(request_rows),
        "phase_rows": phase_rows,
    }


def fmt(value: Any, precision: int = 2) -> str:
    if value is None:
        return "-"
    if isinstance(value, float):
        return f"{value:.{precision}f}"
    return str(value)


def phase_value(summary: dict[str, Any], phase: str, key: str) -> float | None:
    row = summary["phase_rows"].get(phase)
    if row is None:
        return None
    value = row.get(key)
    return float(value) if value is not None else None


def speedup(baseline: float | None, candidate: float | None) -> float | None:
    if baseline is None or candidate is None or candidate == 0:
        return None
    return baseline / candidate


def reduction_ratio(baseline: float | None, candidate: float | None) -> float | None:
    if baseline is None or baseline == 0 or candidate is None:
        return None
    return (baseline - candidate) / baseline


def percent(value: float | None) -> str:
    if value is None:
        return "-"
    return f"{value * 100:.1f}%"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("jsonl", nargs="+", type=Path)
    parser.add_argument(
        "--baseline",
        type=Path,
        default=None,
        help="Artifact to use as the speedup baseline. Defaults to first file.",
    )
    args = parser.parse_args()

    summaries = [artifact_summary(path) for path in args.jsonl]
    baseline_path = args.baseline or args.jsonl[0]
    baseline = next(
        (summary for summary in summaries if summary["path"] == baseline_path),
        None,
    )
    if baseline is None:
        raise SystemExit(f"baseline artifact not included: {baseline_path}")

    print(
        "artifact preset mode cache_entries memory_limit request_count run_id"
    )
    for summary in summaries:
        print(
            "artifact",
            summary["path"],
            summary["engine_preset"],
            summary["population_mode"],
            summary["cache_max_entries"],
            summary["memory_limit_bytes"],
            summary["request_count"],
            summary["run_id"],
        )

    print()
    print(
        "phase artifact count mean_service_request_ms mean_actual_prefill_tokens "
        "speedup_vs_baseline"
    )
    for phase in (
        "prefill_cold",
        "prefill_warm",
        "full_prefill",
        "cache_scheduled",
        "cache_create",
        "cache_hit",
    ):
        baseline_service = phase_value(
            baseline,
            phase,
            "mean_service_request_ms",
        )
        for summary in summaries:
            row = summary["phase_rows"].get(phase)
            if row is None:
                continue
            candidate_service = row.get("mean_service_request_ms")
            print(
                "phase",
                phase,
                summary["path"],
                row.get("count"),
                fmt(candidate_service),
                fmt(row.get("mean_actual_prefill_tokens")),
                fmt(speedup(baseline_service, candidate_service)),
            )

    print()
    print(
        "derived artifact phase service_speedup_vs_full_prefill "
        "prefill_reduction_vs_full_prefill cache_prepare_share"
    )
    for summary in summaries:
        full_service = phase_value(summary, "full_prefill", "mean_service_request_ms")
        full_prefill_tokens = phase_value(
            summary,
            "full_prefill",
            "mean_actual_prefill_tokens",
        )
        for phase in ("cache_scheduled", "cache_create", "cache_hit"):
            row = summary["phase_rows"].get(phase)
            if row is None:
                continue
            service = row.get("mean_service_request_ms")
            prepare = row.get("mean_cache_prepare_ms")
            prefill_tokens = row.get("mean_actual_prefill_tokens")
            print(
                "derived",
                summary["path"],
                phase,
                fmt(speedup(full_service, service)),
                percent(reduction_ratio(full_prefill_tokens, prefill_tokens)),
                percent(
                    float(prepare) / float(service)
                    if prepare is not None and service not in (None, 0)
                    else None
                ),
            )


if __name__ == "__main__":
    main()
