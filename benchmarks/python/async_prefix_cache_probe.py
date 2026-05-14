#!/usr/bin/env python3
"""Probe async resident MLX prefix-cache population."""

from __future__ import annotations

import argparse
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
    parser.add_argument("--max-tokens", type=int, default=4)
    parser.add_argument("--wait-timeout-s", type=float, default=8.0)
    args = parser.parse_args()

    base_url = args.base_url.rstrip("/")
    health = request_json("GET", f"{base_url}/health")
    print("async_policy", health["prefix_cache_policy"])

    run_id = uuid.uuid4().hex[:8]
    shared_prefix = (
        f"Async prefix probe {run_id}.\n"
        "System: You are validating async prefix-cache population in a resident "
        "MLX engine. Stable coding-agent context: tools, repo rules, benchmark "
        "policy, scheduler facts, and cache safety metadata are repeated across "
        "turns. User: "
    )

    first = completion(base_url, shared_prefix + "first request", args.max_tokens)
    second = completion(base_url, shared_prefix + "second request", args.max_tokens)
    print(
        "async_probe",
        1,
        first["longest_prefix_match_tokens"],
        first.get("cache_reuse_enabled"),
        first.get("cache_scheduled"),
        first.get("cache_hit"),
        first.get("cache_created"),
        round(first.get("cache_prepare_ms") or 0.0, 2),
        round(first.get("service_request_ms") or 0.0, 2),
    )
    print(
        "async_probe",
        2,
        second["longest_prefix_match_tokens"],
        second.get("cache_reuse_enabled"),
        second.get("cache_scheduled"),
        second.get("cache_hit"),
        second.get("cache_created"),
        round(second.get("cache_prepare_ms") or 0.0, 2),
        round(second.get("service_request_ms") or 0.0, 2),
    )

    deadline = time.time() + args.wait_timeout_s
    current = request_json("GET", f"{base_url}/health")
    while time.time() < deadline:
        policy = current["prefix_cache_policy"]
        if policy["pending_async_builds"] == 0 and policy["async_builds_completed"] > 0:
            break
        time.sleep(0.25)
        current = request_json("GET", f"{base_url}/health")
    print(
        "async_wait",
        current["prefix_cache_policy"]["pending_async_builds"],
        current["prefix_cache_policy"]["async_builds_started"],
        current["prefix_cache_policy"]["async_builds_completed"],
        current["prefix_cache_policy"]["async_builds_failed"],
        current["prefix_kv_cache"]["entries"],
    )

    third = completion(base_url, shared_prefix + "third request", args.max_tokens)
    print(
        "async_probe",
        3,
        third["longest_prefix_match_tokens"],
        third.get("cache_reuse_enabled"),
        third.get("cache_scheduled"),
        third.get("cache_hit"),
        third.get("cache_created"),
        round(third.get("cache_prepare_ms") or 0.0, 2),
        round(third.get("service_request_ms") or 0.0, 2),
        third.get("actual_prefill_tokens"),
    )


if __name__ == "__main__":
    main()
