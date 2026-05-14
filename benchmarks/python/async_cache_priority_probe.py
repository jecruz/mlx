#!/usr/bin/env python3
"""Validate that async prefix-cache builds wait behind foreground inference."""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import time
import urllib.request
import uuid
from typing import Any


def request_json(method: str, url: str, payload: dict[str, Any] | None = None):
    data = None
    headers = {}
    if payload is not None:
        data = json.dumps(payload).encode()
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    with urllib.request.urlopen(req, timeout=240) as resp:
        return json.loads(resp.read().decode())


def completion(base_url: str, prompt: str, max_tokens: int) -> dict[str, Any]:
    response = request_json(
        "POST",
        f"{base_url}/v1/completions",
        {
            "model": "local-gpt-oss",
            "prompt": prompt,
            "max_tokens": max_tokens,
            "policy": "auto",
        },
    )
    return response["engine_metrics"]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8765")
    parser.add_argument("--foreground-clients", type=int, default=3)
    parser.add_argument("--max-tokens", type=int, default=4)
    parser.add_argument("--idle-grace-ms", type=int, default=400)
    parser.add_argument("--wait-timeout-s", type=float, default=12.0)
    args = parser.parse_args()

    base_url = args.base_url.rstrip("/")
    before = request_json("GET", f"{base_url}/health")
    before_policy = before["prefix_cache_policy"]
    try:
        request_json(
            "POST",
            f"{base_url}/engine/config",
            {
                "engine_preset": "async-experimental",
                "prefix_cache_population_mode": "async",
                "prefix_cache_async_idle_grace_ms": args.idle_grace_ms,
            },
        )

        run_id = uuid.uuid4().hex[:8]
        shared_prefix = (
            f"Async foreground priority probe {run_id}.\n"
            "Repository: mlx prompt processing worktree. Objective: validate that "
            "background prefix-cache construction never cuts ahead of foreground "
            "inference requests while agentic coding prompts are arriving. Context: "
            "scheduler, prefix cache, MLX Metal GPU, performance counters, "
            "regression gates, and cache reuse policy. User prompt: "
        )

        first = completion(base_url, shared_prefix + "seed request", args.max_tokens)
        second = completion(
            base_url,
            shared_prefix + "schedule async build",
            args.max_tokens,
        )
        if not second.get("cache_scheduled"):
            raise RuntimeError(f"async cache build was not scheduled: {second}")

        def foreground(index: int) -> dict[str, Any]:
            prompt = (
                f"Foreground priority request {run_id} #{index}. "
                "Answer with one short phrase about prompt processing."
            )
            return completion(base_url, prompt, args.max_tokens)

        with concurrent.futures.ThreadPoolExecutor(
            max_workers=args.foreground_clients,
        ) as executor:
            foreground_results = list(
                executor.map(foreground, range(args.foreground_clients))
            )

        deadline = time.time() + args.wait_timeout_s
        current = request_json("GET", f"{base_url}/health")
        while time.time() < deadline:
            policy = current["prefix_cache_policy"]
            if (
                policy["pending_async_builds"] == 0
                and policy["async_builds_completed"]
                > before_policy.get("async_builds_completed", 0)
            ):
                break
            time.sleep(0.25)
            current = request_json("GET", f"{base_url}/health")

        policy = current["prefix_cache_policy"]
        if policy["pending_async_builds"] != 0:
            raise RuntimeError(f"async cache build did not drain: {policy}")
        if policy["async_builds_completed"] <= before_policy.get(
            "async_builds_completed",
            0,
        ):
            raise RuntimeError(f"async cache build did not complete: {policy}")
        if policy.get("async_idle_grace_wait_ms", 0.0) <= 0:
            raise RuntimeError(f"async idle grace wait counter did not move: {policy}")

        third = completion(base_url, shared_prefix + "cache hit request", args.max_tokens)
        if not third.get("cache_hit"):
            raise RuntimeError(f"async cache was built but not reused: {third}")

        print(
            "async_priority",
            "ok",
            "first_match",
            first["longest_prefix_match_tokens"],
            "scheduled_match",
            second["longest_prefix_match_tokens"],
            "foreground",
            len(foreground_results),
            "grace_wait_ms",
            round(policy.get("async_idle_grace_wait_ms", 0.0), 2),
            "grace_resets",
            policy.get("async_idle_grace_resets", 0),
            "cache_hit_prefill_tokens",
            third.get("actual_prefill_tokens"),
        )
    finally:
        request_json("POST", f"{base_url}/engine/config", {"engine_preset": "sync-safe"})


if __name__ == "__main__":
    main()
