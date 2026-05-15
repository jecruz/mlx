#!/usr/bin/env python3
"""Verify pending async prefix builds can be awaited by a duplicate request."""

from __future__ import annotations

import argparse
import json
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


def completion(base_url: str, *, prompt: str, max_tokens: int) -> dict[str, Any]:
    response = request_json(
        "POST",
        f"{base_url}/v1/completions",
        {
            "model": "mlx-engine-m21",
            "prompt": prompt,
            "max_tokens": max_tokens,
            "policy": "auto",
        },
    )
    metrics = response["engine_metrics"]
    if not response["choices"][0]["text"]:
        raise RuntimeError("completion response was empty")
    return metrics


def build_prompts(*, repeats: int) -> list[str]:
    run_id = uuid.uuid4().hex[:8]
    shared = (
        f"M21 pending prefix-build wait probe {run_id}.\n"
        + (
            "Repeated local MLX engine context with request scheduling, "
            "background cache construction, and prefix reuse telemetry. "
        )
        * repeats
    )
    return [
        shared + "\nTask: establish baseline.",
        shared + "\nTask: schedule the shared async prefix build.",
        shared + "\nTask: wait for the pending prefix build and reuse it.",
    ]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8765")
    parser.add_argument(
        "--output-jsonl",
        type=Path,
        default=Path("async-prefix-pending-wait-m21.jsonl"),
    )
    parser.add_argument("--prefix-repeats", type=int, default=60)
    parser.add_argument("--max-tokens", type=int, default=4)
    parser.add_argument("--async-idle-grace-ms", type=int, default=500)
    parser.add_argument("--pending-wait-ms", type=int, default=6000)
    args = parser.parse_args()

    base_url = args.base_url.rstrip("/")
    args.output_jsonl.write_text("")
    request_json(
        "POST",
        f"{base_url}/engine/config",
        {
            "engine_preset": "async-experimental",
            "prefix_cache_async_idle_grace_ms": args.async_idle_grace_ms,
            "prefix_cache_pending_wait_ms": args.pending_wait_ms,
        },
    )
    request_json(
        "POST",
        f"{base_url}/engine/cache/prune",
        {"target_entries": 0, "clear_mlx_cache": False},
    )
    before = request_json("GET", f"{base_url}/health")
    before_policy = before["prefix_cache_policy"]
    before_started = int(before_policy.get("async_builds_started") or 0)
    before_completed = int(before_policy.get("async_builds_completed") or 0)
    before_waits = int(before_policy.get("pending_waits") or 0)
    before_wait_hits = int(before_policy.get("pending_wait_hits") or 0)

    try:
        rows = []
        for phase, prompt in zip(
            ("baseline", "schedule", "wait_hit"),
            build_prompts(repeats=args.prefix_repeats),
            strict=True,
        ):
            metrics = completion(base_url, prompt=prompt, max_tokens=args.max_tokens)
            row = {
                "type": "request",
                "created": int(time.time()),
                "phase": phase,
                "service_request_ms": metrics.get("service_request_ms"),
                "cache_prepare_ms": metrics.get("cache_prepare_ms"),
                "prompt_tokens_estimate": metrics.get("prompt_tokens_estimate"),
                "actual_prefill_tokens": metrics.get("actual_prefill_tokens"),
                "longest_prefix_match_tokens": metrics.get(
                    "longest_prefix_match_tokens"
                ),
                "cache_scheduled": metrics.get("cache_scheduled"),
                "cache_pending": metrics.get("cache_pending"),
                "cache_hit": metrics.get("cache_hit"),
                "cache_build_deduplicated": metrics.get("cache_build_deduplicated"),
                "cache_pending_wait_ms": metrics.get("cache_pending_wait_ms"),
                "cache_pending_wait_result": metrics.get(
                    "cache_pending_wait_result"
                ),
            }
            rows.append(row)
            write_row(args.output_jsonl, row)
            print(
                "m21_request",
                phase,
                "service_ms",
                round(float(row["service_request_ms"] or 0.0), 2),
                "scheduled",
                row["cache_scheduled"],
                "pending",
                row["cache_pending"],
                "wait_result",
                row["cache_pending_wait_result"],
                "hit",
                row["cache_hit"],
                "actual_prefill",
                row["actual_prefill_tokens"],
                flush=True,
            )

        after = request_json("GET", f"{base_url}/health")
        after_policy = after["prefix_cache_policy"]
        started_delta = (
            int(after_policy.get("async_builds_started") or 0) - before_started
        )
        completed_delta = (
            int(after_policy.get("async_builds_completed") or 0) - before_completed
        )
        waits_delta = int(after_policy.get("pending_waits") or 0) - before_waits
        wait_hits_delta = (
            int(after_policy.get("pending_wait_hits") or 0) - before_wait_hits
        )
        schedule = rows[1]
        wait_hit = rows[2]
        if not schedule["cache_scheduled"]:
            raise RuntimeError(f"schedule phase did not schedule build: {schedule}")
        if not wait_hit["cache_build_deduplicated"]:
            raise RuntimeError(f"wait phase did not deduplicate build: {wait_hit}")
        if wait_hit["cache_pending_wait_result"] != "hit":
            raise RuntimeError(f"wait phase did not hit after waiting: {wait_hit}")
        if not wait_hit["cache_hit"]:
            raise RuntimeError(f"wait phase did not reuse completed cache: {wait_hit}")
        if int(wait_hit["actual_prefill_tokens"] or 0) > 16:
            raise RuntimeError(f"wait phase did too much prefill: {wait_hit}")
        if started_delta != 1 or completed_delta != 1:
            raise RuntimeError(
                "expected one async build start and completion, saw "
                f"started={started_delta} completed={completed_delta}: {after_policy}"
            )
        if waits_delta != 1 or wait_hits_delta != 1:
            raise RuntimeError(
                "expected one pending wait hit, saw "
                f"waits={waits_delta} wait_hits={wait_hits_delta}: {after_policy}"
            )

        summary = {
            "type": "summary",
            "created": int(time.time()),
            "started_delta": started_delta,
            "completed_delta": completed_delta,
            "pending_waits_delta": waits_delta,
            "pending_wait_hits_delta": wait_hits_delta,
            "wait_hit_actual_prefill_tokens": wait_hit["actual_prefill_tokens"],
            "wait_hit_service_request_ms": wait_hit["service_request_ms"],
            "wait_hit_cache_pending_wait_ms": wait_hit["cache_pending_wait_ms"],
        }
        write_row(args.output_jsonl, summary)
        print(
            "m21_summary",
            "started_delta",
            started_delta,
            "completed_delta",
            completed_delta,
            "waits_delta",
            waits_delta,
            "wait_hits_delta",
            wait_hits_delta,
            args.output_jsonl,
            flush=True,
        )
    finally:
        request_json(
            "POST",
            f"{base_url}/engine/config",
            {"engine_preset": "sync-safe"},
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
