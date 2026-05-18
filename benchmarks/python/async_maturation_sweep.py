#!/usr/bin/env python3
"""Sweep async prefix-cache maturation settings."""

from __future__ import annotations

import argparse
import json
import statistics
import time
import urllib.request
import uuid
from pathlib import Path
from typing import Any


def request_json(
    method: str,
    url: str,
    payload: dict[str, Any] | None = None,
    *,
    timeout: int = 1200,
) -> dict[str, Any]:
    data = None
    headers = {}
    if payload is not None:
        data = json.dumps(payload).encode()
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode())


def write_row(path: Path, row: dict[str, Any]) -> None:
    with path.open("a") as f:
        f.write(json.dumps(row, sort_keys=True) + "\n")


def parse_int_list(value: str) -> list[int]:
    parsed = [int(item.strip()) for item in value.split(",") if item.strip()]
    if not parsed:
        raise argparse.ArgumentTypeError("list must contain at least one integer")
    if any(item < 0 for item in parsed):
        raise argparse.ArgumentTypeError("values must be non-negative")
    return parsed


def build_prompts(*, run_id: str, repeats: int) -> list[tuple[str, str]]:
    shared = (
        f"M79 async maturation sweep {run_id}.\n"
        + (
            "Stable coding-agent context with repository rules, MLX resident "
            "engine telemetry, scheduler state, prefix-cache policy, tool "
            "schemas, and benchmark acceptance criteria. "
        )
        * repeats
    )
    return [
        ("baseline", shared + "\nTask: establish full-prefill baseline."),
        ("schedule", shared + "\nTask: schedule async prefix construction."),
        ("wait_hit", shared + "\nTask: wait for async cache maturation and reuse it."),
        ("mature_hit", shared + "\nTask: reuse the completed async cache without pending wait."),
    ]


def completion(base_url: str, *, prompt: str, max_tokens: int) -> dict[str, Any]:
    response = request_json(
        "POST",
        f"{base_url}/v1/completions",
        {
            "model": "mlx-engine-m79",
            "prompt": prompt,
            "max_tokens": max_tokens,
            "policy": "auto",
        },
    )
    if not response["choices"][0]["text"]:
        raise RuntimeError("completion response was empty")
    return response["engine_metrics"]


def policy_counters(policy: dict[str, Any]) -> dict[str, int]:
    keys = [
        "async_builds_started",
        "async_builds_completed",
        "async_builds_failed",
        "async_builds_skipped",
        "pending_waits",
        "pending_wait_hits",
        "pending_wait_timeouts",
        "pending_wait_misses",
        "pending_build_deduplications",
    ]
    return {key: int(policy.get(key) or 0) for key in keys}


def counter_delta(after: dict[str, int], before: dict[str, int]) -> dict[str, int]:
    return {key: after[key] - before[key] for key in before}


def metric_row(
    *,
    combo_id: str,
    grace_ms: int,
    pending_wait_ms: int,
    phase: str,
    metrics: dict[str, Any],
) -> dict[str, Any]:
    return {
        "type": "request",
        "created": int(time.time()),
        "combo_id": combo_id,
        "async_idle_grace_ms": grace_ms,
        "pending_wait_ms": pending_wait_ms,
        "phase": phase,
        "service_request_ms": metrics.get("service_request_ms"),
        "cache_prepare_ms": metrics.get("cache_prepare_ms"),
        "prompt_tokens_estimate": metrics.get("prompt_tokens_estimate"),
        "actual_prefill_tokens": metrics.get("actual_prefill_tokens"),
        "longest_prefix_match_tokens": metrics.get("longest_prefix_match_tokens"),
        "cache_scheduled": metrics.get("cache_scheduled"),
        "cache_pending": metrics.get("cache_pending"),
        "cache_hit": metrics.get("cache_hit"),
        "cache_build_deduplicated": metrics.get("cache_build_deduplicated"),
        "cache_pending_wait_ms": metrics.get("cache_pending_wait_ms"),
        "cache_pending_wait_result": metrics.get("cache_pending_wait_result"),
    }


def numeric(row: dict[str, Any], key: str) -> float | None:
    value = row.get(key)
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


def run_combo(
    *,
    base_url: str,
    output_jsonl: Path,
    grace_ms: int,
    pending_wait_ms: int,
    prefix_repeats: int,
    max_tokens: int,
) -> dict[str, Any]:
    combo_id = f"grace{grace_ms}-wait{pending_wait_ms}-{uuid.uuid4().hex[:8]}"
    request_json(
        "POST",
        f"{base_url}/engine/config",
        {
            "engine_preset": "async-experimental",
            "prefix_cache_async_idle_grace_ms": grace_ms,
            "prefix_cache_pending_wait_ms": pending_wait_ms,
        },
    )
    request_json(
        "POST",
        f"{base_url}/engine/cache/prune",
        {"target_entries": 0, "clear_mlx_cache": False},
    )
    before_policy = policy_counters(
        request_json("GET", f"{base_url}/health")["prefix_cache_policy"]
    )
    rows = []
    for phase, prompt in build_prompts(run_id=combo_id, repeats=prefix_repeats):
        row = metric_row(
            combo_id=combo_id,
            grace_ms=grace_ms,
            pending_wait_ms=pending_wait_ms,
            phase=phase,
            metrics=completion(base_url, prompt=prompt, max_tokens=max_tokens),
        )
        rows.append(row)
        write_row(output_jsonl, row)
        print(
            "m79_request",
            grace_ms,
            pending_wait_ms,
            phase,
            "service_ms",
            round(float(row["service_request_ms"] or 0.0), 2),
            "scheduled",
            row["cache_scheduled"],
            "wait_result",
            row["cache_pending_wait_result"],
            "hit",
            row["cache_hit"],
            "actual_prefill",
            row["actual_prefill_tokens"],
            flush=True,
        )

    after_policy = policy_counters(
        request_json("GET", f"{base_url}/health")["prefix_cache_policy"]
    )
    deltas = counter_delta(after_policy, before_policy)
    baseline = next(row for row in rows if row["phase"] == "baseline")
    wait_hit = next(row for row in rows if row["phase"] == "wait_hit")
    mature_hit = next(row for row in rows if row["phase"] == "mature_hit")
    baseline_service = numeric(baseline, "service_request_ms")
    wait_service = numeric(wait_hit, "service_request_ms")
    mature_service = numeric(mature_hit, "service_request_ms")
    wait_speedup = (
        baseline_service / wait_service
        if baseline_service is not None and wait_service is not None and wait_service > 0
        else None
    )
    mature_speedup = (
        baseline_service / mature_service
        if baseline_service is not None
        and mature_service is not None
        and mature_service > 0
        else None
    )
    summary = {
        "type": "combo_summary",
        "created": int(time.time()),
        "combo_id": combo_id,
        "async_idle_grace_ms": grace_ms,
        "pending_wait_ms": pending_wait_ms,
        "cache_hit": bool(wait_hit.get("cache_hit")),
        "mature_cache_hit": bool(mature_hit.get("cache_hit")),
        "cache_pending_wait_result": wait_hit.get("cache_pending_wait_result"),
        "cache_pending_wait_ms": wait_hit.get("cache_pending_wait_ms"),
        "baseline_service_request_ms": baseline_service,
        "wait_hit_service_request_ms": wait_service,
        "mature_hit_service_request_ms": mature_service,
        "wait_hit_actual_prefill_tokens": wait_hit.get("actual_prefill_tokens"),
        "mature_hit_actual_prefill_tokens": mature_hit.get("actual_prefill_tokens"),
        "cache_hit_speedup_vs_baseline": wait_speedup,
        "mature_cache_hit_speedup_vs_baseline": mature_speedup,
        "policy_deltas": deltas,
    }
    write_row(output_jsonl, summary)
    print(
        "m79_combo",
        grace_ms,
        pending_wait_ms,
        "hit",
        summary["cache_hit"],
        "mature_hit",
        summary["mature_cache_hit"],
        "wait_result",
        summary["cache_pending_wait_result"],
        "wait_speedup",
        round(wait_speedup or 0.0, 3),
        "mature_speedup",
        round(mature_speedup or 0.0, 3),
        "wait_ms",
        round(float(summary["cache_pending_wait_ms"] or 0.0), 2),
        "completed",
        deltas["async_builds_completed"],
        flush=True,
    )
    return summary


def choose_best(summaries: list[dict[str, Any]], min_speedup: float) -> dict[str, Any] | None:
    candidates = [
        summary
        for summary in summaries
        if summary["mature_cache_hit"]
        and (summary.get("mature_cache_hit_speedup_vs_baseline") or 0.0) >= min_speedup
    ]
    if not candidates:
        return None
    return min(
        candidates,
        key=lambda item: (
            int(item["pending_wait_ms"]),
            int(item["async_idle_grace_ms"]),
            float(item.get("wait_hit_service_request_ms") or 1e9),
        ),
    )


def choose_first_hit_best(summaries: list[dict[str, Any]]) -> dict[str, Any] | None:
    candidates = [summary for summary in summaries if summary["cache_hit"]]
    if not candidates:
        return None
    return min(
        candidates,
        key=lambda item: (
            int(item["pending_wait_ms"]),
            int(item["async_idle_grace_ms"]),
            float(item.get("cache_pending_wait_ms") or 1e9),
        ),
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8765")
    parser.add_argument("--output-jsonl", type=Path, default=Path("async-maturation-m79.jsonl"))
    parser.add_argument("--output-json", type=Path)
    parser.add_argument("--grace-ms", type=parse_int_list, default=parse_int_list("0,25,50,100,250"))
    parser.add_argument("--pending-wait-ms", type=parse_int_list, default=parse_int_list("0,250,500,1000,1500"))
    parser.add_argument("--prefix-repeats", type=int, default=8)
    parser.add_argument("--max-tokens", type=int, default=6)
    parser.add_argument("--min-speedup", type=float, default=2.0)
    parser.add_argument("--fail-on-no-hit", action="store_true")
    args = parser.parse_args()

    base_url = args.base_url.rstrip("/")
    args.output_jsonl.parent.mkdir(parents=True, exist_ok=True)
    args.output_jsonl.write_text("")
    summaries = []
    try:
        for grace_ms in args.grace_ms:
            for pending_wait_ms in args.pending_wait_ms:
                summaries.append(
                    run_combo(
                        base_url=base_url,
                        output_jsonl=args.output_jsonl,
                        grace_ms=grace_ms,
                        pending_wait_ms=pending_wait_ms,
                        prefix_repeats=args.prefix_repeats,
                        max_tokens=args.max_tokens,
                    )
                )
    finally:
        request_json(
            "POST",
            f"{base_url}/engine/config",
            {"engine_preset": "sync-safe"},
        )

    best = choose_best(summaries, min_speedup=args.min_speedup)
    first_hit_best = choose_first_hit_best(summaries)
    report = {
        "type": "async_maturation_sweep",
        "verdict": "PASS" if best is not None else "FAIL",
        "base_url": base_url,
        "output_jsonl": str(args.output_jsonl),
        "min_speedup": args.min_speedup,
        "combo_count": len(summaries),
        "hit_count": sum(1 for summary in summaries if summary["cache_hit"]),
        "mature_hit_count": sum(1 for summary in summaries if summary["mature_cache_hit"]),
        "best": best,
        "first_hit_best": first_hit_best,
        "summaries": summaries,
    }
    if args.output_json:
        args.output_json.parent.mkdir(parents=True, exist_ok=True)
        args.output_json.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(
        "m79_result",
        report["verdict"],
        "combos",
        report["combo_count"],
        "hits",
        report["hit_count"],
        "mature_hits",
        report["mature_hit_count"],
        "best",
        None if best is None else f"grace={best['async_idle_grace_ms']} wait={best['pending_wait_ms']}",
        "first_hit_best",
        None
        if first_hit_best is None
        else f"grace={first_hit_best['async_idle_grace_ms']} wait={first_hit_best['pending_wait_ms']}",
        flush=True,
    )
    if args.fail_on_no_hit and best is None:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
