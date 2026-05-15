#!/usr/bin/env python3
"""Validate request-derived prefix-cache population."""

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
            "model": "mlx-engine-m15",
            "prompt": prompt,
            "max_tokens": max_tokens,
            "policy": "auto",
        },
    )
    metrics = response["engine_metrics"]
    if not response["choices"][0]["text"]:
        raise RuntimeError("completion response was empty")
    return metrics


def build_prompts(*, run_id: str, repeats: int) -> list[str]:
    shared = (
        f"M15 request-cache trim probe {run_id}.\n"
        + (
            "Agentic coding workload with repeated repository context, benchmark "
            "targets, scheduler rules, prefix-cache metadata, and MLX Metal timing. "
        )
        * repeats
    )
    return [
        shared + "\nTask: establish the cold baseline request.",
        shared + "\nTask: populate the reusable prefix from this request cache.",
        shared + "\nTask: reuse the request-derived prefix cache.",
    ]


def configure_case(base_url: str, *, mode: str, idle_grace_ms: int) -> None:
    if mode == "request":
        payload: dict[str, Any] = {
            "engine_preset": "custom",
            "max_concurrent_requests": 1,
            "max_queued_requests": 16,
            "prefix_cache_population_mode": "request",
        }
    elif mode == "async":
        payload = {
            "engine_preset": "async-experimental",
            "prefix_cache_async_idle_grace_ms": idle_grace_ms,
        }
    else:
        raise ValueError(f"unsupported mode: {mode}")
    request_json("POST", f"{base_url}/engine/config", payload)


def wait_for_async_build(
    base_url: str,
    *,
    before_completed: int,
    timeout_s: float,
) -> None:
    deadline = time.time() + timeout_s
    health = request_json("GET", f"{base_url}/health")
    while time.time() < deadline:
        policy = health["prefix_cache_policy"]
        if (
            policy["pending_async_builds"] == 0
            and policy["async_builds_completed"] > before_completed
        ):
            return
        if policy["async_builds_failed"] > 0:
            raise RuntimeError(f"async build failed: {policy}")
        time.sleep(0.25)
        health = request_json("GET", f"{base_url}/health")
    raise RuntimeError(f"async build did not complete: {health['prefix_cache_policy']}")


def run_case(
    *,
    base_url: str,
    artifact: Path,
    mode: str,
    repeats: int,
    max_tokens: int,
    async_wait_timeout_s: float,
    async_idle_grace_ms: int,
) -> dict[str, Any]:
    configure_case(base_url, mode=mode, idle_grace_ms=async_idle_grace_ms)
    request_json(
        "POST",
        f"{base_url}/engine/cache/prune",
        {"target_entries": 0, "clear_mlx_cache": False},
    )
    before = request_json("GET", f"{base_url}/health")
    before_policy = before["prefix_cache_policy"]
    before_async_completed = int(before_policy.get("async_builds_completed") or 0)
    prompts = build_prompts(run_id=f"{mode}-{uuid.uuid4().hex[:8]}", repeats=repeats)
    rows = []
    for index, prompt in enumerate(prompts, start=1):
        metrics = completion(base_url, prompt=prompt, max_tokens=max_tokens)
        phase = ("baseline", "populate", "hit")[index - 1]
        row = {
            "type": "request",
            "created": int(time.time()),
            "mode": mode,
            "phase": phase,
            "service_request_ms": metrics.get("service_request_ms"),
            "run_ms": metrics.get("run_ms"),
            "cache_prepare_ms": metrics.get("cache_prepare_ms"),
            "prompt_tokens_estimate": metrics.get("prompt_tokens_estimate"),
            "actual_prefill_tokens": metrics.get("actual_prefill_tokens"),
            "longest_prefix_match_tokens": metrics.get("longest_prefix_match_tokens"),
            "cache_reuse_enabled": metrics.get("cache_reuse_enabled"),
            "cache_hit": metrics.get("cache_hit"),
            "cache_scheduled": metrics.get("cache_scheduled"),
            "cache_stored_from_request": metrics.get("cache_stored_from_request"),
            "cache_request_trimmed_tokens": metrics.get("cache_request_trimmed_tokens"),
            "cache_request_store_reason": metrics.get("cache_request_store_reason"),
            "cached_prefix_tokens": metrics.get("cached_prefix_tokens"),
        }
        rows.append(row)
        write_row(artifact, row)
        print(
            "m15_request",
            mode,
            phase,
            "service_ms",
            round(float(row["service_request_ms"] or 0.0), 2),
            "cache_prepare_ms",
            round(float(row["cache_prepare_ms"] or 0.0), 2),
            "actual_prefill",
            row["actual_prefill_tokens"],
            "stored_from_request",
            row["cache_stored_from_request"],
            "scheduled",
            row["cache_scheduled"],
            "hit",
            row["cache_hit"],
            flush=True,
        )
        if phase == "populate" and row["cache_scheduled"]:
            wait_for_async_build(
                base_url,
                before_completed=before_async_completed,
                timeout_s=async_wait_timeout_s,
            )

    after = request_json("GET", f"{base_url}/health")
    after_policy = after["prefix_cache_policy"]
    populate = rows[1]
    hit = rows[2]
    if mode == "request" and not (
        populate["cache_stored_from_request"]
        or populate["cache_request_store_reason"]
        in {
            "not_trimmable_fallback_async",
            "trim_incomplete_fallback_async",
        }
    ):
        raise RuntimeError(
            "request case neither stored cache from request nor used a safe "
            f"fallback: {populate}"
        )
    if mode == "async" and not populate["cache_scheduled"]:
        raise RuntimeError(f"async case did not schedule cache build: {populate}")
    if not hit["cache_hit"]:
        raise RuntimeError(f"{mode} case did not hit cache on follow-up: {hit}")
    if mode == "request" and populate["cache_stored_from_request"]:
        async_delta = (
            int(after_policy.get("async_builds_completed") or 0)
            - before_async_completed
        )
        if async_delta != 0:
            raise RuntimeError(f"request case unexpectedly ran async builds: {async_delta}")
    return {
        "mode": mode,
        "rows": rows,
        "before_policy": before_policy,
        "after_policy": after_policy,
        "populate_service_request_ms": float(populate["service_request_ms"]),
        "populate_cache_prepare_ms": float(populate["cache_prepare_ms"] or 0.0),
        "hit_service_request_ms": float(hit["service_request_ms"]),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8765")
    parser.add_argument(
        "--output-jsonl",
        type=Path,
        default=Path("request-prefix-cache-m15.jsonl"),
    )
    parser.add_argument("--prefix-repeats", type=int, default=24)
    parser.add_argument("--max-tokens", type=int, default=4)
    parser.add_argument("--async-wait-timeout-s", type=float, default=20.0)
    parser.add_argument("--async-idle-grace-ms", type=int, default=50)
    args = parser.parse_args()

    base_url = args.base_url.rstrip("/")
    args.output_jsonl.write_text("")
    async_case = run_case(
        base_url=base_url,
        artifact=args.output_jsonl,
        mode="async",
        repeats=args.prefix_repeats,
        max_tokens=args.max_tokens,
        async_wait_timeout_s=args.async_wait_timeout_s,
        async_idle_grace_ms=args.async_idle_grace_ms,
    )
    request_case = run_case(
        base_url=base_url,
        artifact=args.output_jsonl,
        mode="request",
        repeats=args.prefix_repeats,
        max_tokens=args.max_tokens,
        async_wait_timeout_s=args.async_wait_timeout_s,
        async_idle_grace_ms=args.async_idle_grace_ms,
    )
    improvement_ms = (
        async_case["populate_service_request_ms"]
        - request_case["populate_service_request_ms"]
    )
    summary = {
        "type": "summary",
        "created": int(time.time()),
        "async_populate_service_request_ms": async_case[
            "populate_service_request_ms"
        ],
        "async_populate_cache_prepare_ms": async_case["populate_cache_prepare_ms"],
        "request_populate_service_request_ms": request_case[
            "populate_service_request_ms"
        ],
        "request_populate_cache_prepare_ms": request_case["populate_cache_prepare_ms"],
        "populate_request_vs_async_improvement_ms": improvement_ms,
        "async_hit_service_request_ms": async_case["hit_service_request_ms"],
        "request_hit_service_request_ms": request_case["hit_service_request_ms"],
    }
    write_row(args.output_jsonl, summary)
    print(
        "m15_summary",
        "populate_improvement_ms",
        round(improvement_ms, 2),
        "request_populate_ms",
        round(request_case["populate_service_request_ms"], 2),
        "async_populate_ms",
        round(async_case["populate_service_request_ms"], 2),
        args.output_jsonl,
        flush=True,
    )
    request_json("POST", f"{base_url}/engine/config", {"engine_preset": "sync-safe"})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
