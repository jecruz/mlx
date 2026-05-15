#!/usr/bin/env python3
"""Verify duplicate async prefix builds are amortized while pending."""

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
            "model": "mlx-engine-m20",
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
        f"M20 async prefix-build amortization probe {run_id}.\n"
        + (
            "Repeated local coding-agent context with repository instructions, "
            "scheduler state, MLX cache policy, and benchmark telemetry. "
        )
        * repeats
    )
    return [
        shared + "\nTask: establish baseline.",
        shared + "\nTask: schedule the shared prefix build.",
        shared + "\nTask: arrive while the same prefix build is still pending.",
        shared + "\nTask: confirm the completed shared prefix cache is reused.",
    ]


def wait_for_async_build(
    base_url: str,
    *,
    before_completed: int,
    timeout_s: float,
) -> dict[str, Any]:
    deadline = time.time() + timeout_s
    health = request_json("GET", f"{base_url}/health")
    while time.time() < deadline:
        policy = health["prefix_cache_policy"]
        if (
            int(policy.get("pending_async_builds") or 0) == 0
            and int(policy.get("async_builds_completed") or 0) > before_completed
        ):
            return health
        if int(policy.get("async_builds_failed") or 0) > 0:
            raise RuntimeError(f"async build failed: {policy}")
        time.sleep(0.25)
        health = request_json("GET", f"{base_url}/health")
    raise RuntimeError(f"async build did not complete: {health['prefix_cache_policy']}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8765")
    parser.add_argument(
        "--output-jsonl",
        type=Path,
        default=Path("async-prefix-build-amortization-m20.jsonl"),
    )
    parser.add_argument("--prefix-repeats", type=int, default=60)
    parser.add_argument("--max-tokens", type=int, default=4)
    parser.add_argument("--async-idle-grace-ms", type=int, default=1500)
    parser.add_argument("--async-wait-timeout-s", type=float, default=45.0)
    args = parser.parse_args()

    base_url = args.base_url.rstrip("/")
    args.output_jsonl.write_text("")
    request_json(
        "POST",
        f"{base_url}/engine/config",
        {
            "engine_preset": "async-experimental",
            "prefix_cache_async_idle_grace_ms": args.async_idle_grace_ms,
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
    before_dedup = int(before_policy.get("pending_build_deduplications") or 0)

    try:
        rows = []
        for phase, prompt in zip(
            ("baseline", "schedule", "duplicate_pending", "hit"),
            build_prompts(repeats=args.prefix_repeats),
            strict=True,
        ):
            if phase == "hit":
                wait_for_async_build(
                    base_url,
                    before_completed=before_completed,
                    timeout_s=args.async_wait_timeout_s,
                )
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
                "cache_build_dedup_reason": metrics.get("cache_build_dedup_reason"),
            }
            rows.append(row)
            write_row(args.output_jsonl, row)
            print(
                "m20_request",
                phase,
                "service_ms",
                round(float(row["service_request_ms"] or 0.0), 2),
                "scheduled",
                row["cache_scheduled"],
                "pending",
                row["cache_pending"],
                "dedup",
                row["cache_build_deduplicated"],
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
        dedup_delta = (
            int(after_policy.get("pending_build_deduplications") or 0) - before_dedup
        )
        schedule = rows[1]
        duplicate = rows[2]
        hit = rows[3]
        if not schedule["cache_scheduled"]:
            raise RuntimeError(
                f"schedule phase did not schedule async build: {schedule}"
            )
        if not duplicate["cache_build_deduplicated"]:
            raise RuntimeError(
                f"duplicate phase did not deduplicate pending build: {duplicate}"
            )
        if started_delta != 1:
            raise RuntimeError(
                f"expected one started async build, saw {started_delta}: "
                f"{after_policy}"
            )
        if completed_delta != 1:
            raise RuntimeError(
                f"expected one completed async build, saw {completed_delta}: "
                f"{after_policy}"
            )
        if dedup_delta < 1:
            raise RuntimeError(
                f"expected pending build deduplication, saw {dedup_delta}: "
                f"{after_policy}"
            )
        if not hit["cache_hit"]:
            raise RuntimeError(f"hit phase did not reuse completed cache: {hit}")

        summary = {
            "type": "summary",
            "created": int(time.time()),
            "started_delta": started_delta,
            "completed_delta": completed_delta,
            "pending_build_deduplications_delta": dedup_delta,
            "duplicate_actual_prefill_tokens": duplicate["actual_prefill_tokens"],
            "hit_actual_prefill_tokens": hit["actual_prefill_tokens"],
        }
        write_row(args.output_jsonl, summary)
        print(
            "m20_summary",
            "started_delta",
            started_delta,
            "completed_delta",
            completed_delta,
            "dedup_delta",
            dedup_delta,
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
