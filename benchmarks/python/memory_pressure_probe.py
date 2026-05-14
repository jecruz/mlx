#!/usr/bin/env python3
"""Probe resident MLX prefix-cache memory pressure behavior."""

from __future__ import annotations

import argparse
import json
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
    with urllib.request.urlopen(req, timeout=180) as resp:
        return json.loads(resp.read().decode())


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8765")
    parser.add_argument("--max-tokens", type=int, default=4)
    args = parser.parse_args()

    base_url = args.base_url.rstrip("/")
    health_before = request_json("GET", f"{base_url}/health")
    print(
        "memory_before",
        health_before["prefix_kv_cache"]["entries"],
        health_before["prefix_kv_cache"]["evictions"],
        health_before["prefix_cache_policy"],
    )

    run_id = uuid.uuid4().hex[:8]
    shared_prefix = (
        f"Memory pressure probe {run_id}.\n"
        "System: You are validating resident MLX prefix-cache pruning. "
        "Context: alpha beta gamma delta epsilon zeta eta theta. "
        "Stable repository facts: prefix caches should be retained when there is "
        "memory headroom and pruned when the configured MLX cache-memory limit "
        "is exceeded. User: "
    )
    for index, suffix in enumerate(("first request", "second request"), start=1):
        response = request_json(
            "POST",
            f"{base_url}/v1/completions",
            {
                "model": "local-gpt-oss",
                "prompt": shared_prefix + suffix,
                "max_tokens": args.max_tokens,
                "policy": "auto",
            },
        )
        metrics = response["engine_metrics"]
        print(
            "memory_probe",
            index,
            metrics["longest_prefix_match_tokens"],
            metrics.get("cache_reuse_enabled"),
            metrics.get("cache_hit"),
            metrics.get("cache_created"),
            metrics.get("memory_prune_applied"),
            metrics.get("memory_prune_removed_entries"),
            round(metrics.get("service_request_ms") or 0.0, 2),
        )

    health_after_requests = request_json("GET", f"{base_url}/health")
    print(
        "memory_after_requests",
        health_after_requests["prefix_kv_cache"]["entries"],
        health_after_requests["prefix_kv_cache"]["evictions"],
        health_after_requests["prefix_kv_cache"]["prunes"],
        health_after_requests["prefix_cache_policy"],
    )

    prune = request_json(
        "POST",
        f"{base_url}/engine/cache/prune",
        {"target_entries": 0, "clear_mlx_cache": True},
    )
    print(
        "manual_prune",
        prune["before_entries"],
        prune["after_entries"],
        prune["removed_entries"],
        prune["clear_mlx_cache"],
    )

    health_after_prune = request_json("GET", f"{base_url}/health")
    print(
        "memory_after_prune",
        health_after_prune["prefix_kv_cache"]["entries"],
        health_after_prune["prefix_kv_cache"]["evictions"],
        health_after_prune["prefix_kv_cache"]["prunes"],
    )


if __name__ == "__main__":
    main()
