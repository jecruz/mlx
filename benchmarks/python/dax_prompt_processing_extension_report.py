#!/usr/bin/env python3
"""Extract prompt-processing behavior from Dax product-path JSONL traces."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from statistics import mean
from typing import Any


DEFAULT_INPUTS = [
    Path("artifacts/m97-direct-first-hit-profile/dax-product-first-hit-m97-qwen-a3b-first-hit-direct.jsonl"),
    Path("artifacts/m97-suite-first-hit-direct/dax-product-first-hit-m97-qwen-a3b-first-hit-suite-direct.jsonl"),
    Path("artifacts/m98-direct-low-memory-profile/dax-product-first-hit-m98-qwen-a3b-low-memory-direct.jsonl"),
    Path("artifacts/m98-suite-low-memory-direct/dax-product-first-hit-m98-qwen-a3b-low-memory-suite-direct.jsonl"),
]


def as_float(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


def load_rows(path: Path) -> list[dict[str, Any]]:
    rows = []
    for line_no, line in enumerate(path.read_text().splitlines(), start=1):
        if not line.strip():
            continue
        row = json.loads(line)
        row["_source"] = str(path)
        row["_line_no"] = line_no
        rows.append(row)
    return rows


def prompt_progress_last_ms(row: dict[str, Any]) -> float | None:
    metrics = row.get("engine_metrics") or {}
    value = as_float(metrics.get("prompt_progress_last_ms"))
    if value is not None:
        return value
    trace = metrics.get("prompt_progress_trace") or []
    if trace:
        return as_float(trace[-1].get("elapsed_ms"))
    return None


def compact_row(row: dict[str, Any]) -> dict[str, Any]:
    service_ms = as_float(row.get("service_request_ms"))
    wall_ms = as_float(row.get("wall_ms"))
    progress_ms = prompt_progress_last_ms(row)
    actual_prefill = as_float(row.get("actual_prefill_tokens"))
    prompt_tokens = as_float(row.get("prompt_tokens_estimate"))
    prompt_progress_share = (
        progress_ms / service_ms if progress_ms is not None and service_ms and service_ms > 0 else None
    )
    wall_service_gap_ms = wall_ms - service_ms if wall_ms is not None and service_ms is not None else None
    prefill_tps = (
        actual_prefill / (progress_ms / 1000.0)
        if actual_prefill is not None and progress_ms is not None and progress_ms > 0
        else None
    )
    return {
        "source": row.get("_source"),
        "line_no": row.get("_line_no"),
        "turn": row.get("turn"),
        "runtime_profile": ((row.get("after") or {}).get("runtime_profile")),
        "actual_prefill_tokens": actual_prefill,
        "prompt_tokens_estimate": prompt_tokens,
        "longest_prefix_match_tokens": row.get("longest_prefix_match_tokens"),
        "cache_hit": row.get("cache_hit"),
        "service_request_ms": service_ms,
        "wall_ms": wall_ms,
        "wall_service_gap_ms": wall_service_gap_ms,
        "prompt_progress_last_ms": progress_ms,
        "prompt_progress_share_of_service": prompt_progress_share,
        "actual_prefill_tps": prefill_tps,
    }


def summarize_bucket(rows: list[dict[str, Any]]) -> dict[str, Any]:
    values = [compact_row(row) for row in rows]

    def nums(key: str) -> list[float]:
        return [value for item in values if (value := as_float(item.get(key))) is not None]

    return {
        "count": len(values),
        "mean_actual_prefill_tokens": mean(nums("actual_prefill_tokens")) if nums("actual_prefill_tokens") else None,
        "mean_service_request_ms": mean(nums("service_request_ms")) if nums("service_request_ms") else None,
        "mean_wall_ms": mean(nums("wall_ms")) if nums("wall_ms") else None,
        "mean_prompt_progress_last_ms": mean(nums("prompt_progress_last_ms")) if nums("prompt_progress_last_ms") else None,
        "mean_prompt_progress_share_of_service": mean(nums("prompt_progress_share_of_service"))
        if nums("prompt_progress_share_of_service")
        else None,
        "mean_actual_prefill_tps": mean(nums("actual_prefill_tps")) if nums("actual_prefill_tps") else None,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-jsonl", action="append", type=Path)
    parser.add_argument("--output-json", type=Path, required=True)
    parser.add_argument("--tag", default="m104-qwen-a3b")
    parser.add_argument("--min-long-prefill-rows", type=int, default=4)
    parser.add_argument("--min-short-prefill-rows", type=int, default=8)
    parser.add_argument("--fail-on-fail", action="store_true")
    args = parser.parse_args()

    inputs = args.input_jsonl or DEFAULT_INPUTS
    rows = [row for path in inputs for row in load_rows(path)]
    compact = [compact_row(row) for row in rows]
    long_prefill_rows = [
        row for row in rows if (as_float(row.get("actual_prefill_tokens")) or 0) >= 1024
    ]
    short_prefill_rows = [
        row for row in rows if (as_float(row.get("actual_prefill_tokens")) or 0) <= 64
    ]
    failures: list[str] = []
    if len(long_prefill_rows) < args.min_long_prefill_rows:
        failures.append(f"long_prefill_rows={len(long_prefill_rows)} < {args.min_long_prefill_rows}")
    if len(short_prefill_rows) < args.min_short_prefill_rows:
        failures.append(f"short_prefill_rows={len(short_prefill_rows)} < {args.min_short_prefill_rows}")

    output = {
        "type": "dax_prompt_processing_extension_report",
        "tag": args.tag,
        "verdict": "PASS" if not failures else "FAIL",
        "failures": failures,
        "inputs": [str(path) for path in inputs],
        "row_count": len(rows),
        "buckets": {
            "long_prefill": summarize_bucket(long_prefill_rows),
            "short_prefill": summarize_bucket(short_prefill_rows),
            "all": summarize_bucket(rows),
        },
        "interpretation": {
            "long_prefill_definition": "actual_prefill_tokens >= 1024",
            "short_prefill_definition": "actual_prefill_tokens <= 64",
            "next_sweep_axes": [
                "prompt tokens: 512, 1024, 2048, 4096",
                "reuse ratio: none, first-hit split-prefill, mature cache hit",
                "transport: CLI process, resident Dax client, direct HTTP client",
                "profile: agent-workspace-async, agent-workspace-first-hit, agent-workspace-low-memory",
            ],
        },
        "rows": compact,
    }
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n")

    print(
        "dax_prompt_processing_extension_report",
        output["verdict"],
        "rows",
        len(rows),
        "long",
        len(long_prefill_rows),
        "short",
        len(short_prefill_rows),
        args.output_json,
        flush=True,
    )
    for name, bucket in output["buckets"].items():
        print(
            "bucket",
            name,
            "count",
            bucket["count"],
            "mean_service_ms",
            bucket["mean_service_request_ms"],
            "mean_progress_share",
            bucket["mean_prompt_progress_share_of_service"],
            flush=True,
        )
    return 1 if args.fail_on_fail and failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
