#!/usr/bin/env python3
"""Probe exact-prompt prefix cache reuse through the resident service API."""

from __future__ import annotations

import argparse
import json
import uuid
import urllib.request
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


def engine_metrics(response: dict[str, Any]) -> dict[str, Any]:
    metrics = response.get("engine_metrics")
    if not isinstance(metrics, dict):
        raise AssertionError("response did not include engine_metrics")
    return metrics


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8765")
    parser.add_argument("--max-tokens", type=int, default=4)
    parser.add_argument("--policy", default="auto")
    args = parser.parse_args()
    base_url = args.base_url.rstrip("/")

    health = request_json("GET", f"{base_url}/health")
    initial_preset = health.get("engine_preset")
    print(
        "health",
        health["ok"],
        health["device"]["default_device"],
        initial_preset,
    )

    request_json("POST", f"{base_url}/engine/config", {"engine_preset": "sync-safe"})
    request_json(
        "POST",
        f"{base_url}/engine/cache/prune",
        {"target_entries": 0, "clear_mlx_cache": False},
    )

    prompt = (
        "Exact prompt cache probe. Explain resident local inference in precise "
        "engineering terms. Mention prompt processing, KV cache reuse, scheduler "
        "control, and Metal execution. Keep the answer concise. Probe id: "
        f"{uuid.uuid4().hex}."
    )
    payload = {
        "model": "local-mlx",
        "prompt": prompt,
        "max_tokens": args.max_tokens,
        "policy": args.policy,
    }

    first = engine_metrics(request_json("POST", f"{base_url}/v1/completions", payload))
    second = engine_metrics(request_json("POST", f"{base_url}/v1/completions", payload))
    third = engine_metrics(request_json("POST", f"{base_url}/v1/completions", payload))

    rows = [first, second, third]
    for index, metrics in enumerate(rows, start=1):
        print(
            "exact_prefix",
            index,
            metrics.get("prompt_tokens"),
            metrics.get("longest_prefix_match_tokens"),
            metrics.get("cache_reuse_enabled"),
            metrics.get("cache_created"),
            metrics.get("cache_hit"),
            metrics.get("cache_exact_match_trimmed"),
            metrics.get("cached_prefix_tokens"),
            metrics.get("actual_prefill_tokens"),
            round(float(metrics.get("service_request_ms") or 0.0), 2),
        )

    if second.get("cache_reuse_enabled"):
        first_reuse = second
    elif third.get("cache_reuse_enabled"):
        first_reuse = third
    else:
        raise AssertionError("exact repeated prompt did not reuse prefix cache")
    if not first_reuse.get("cache_exact_match_trimmed"):
        raise AssertionError("first exact reuse was not marked as trimmed")
    if int(first_reuse.get("actual_prefill_tokens") or 0) != 1:
        raise AssertionError("first exact reuse should prefill one trailing token")
    if not third.get("cache_hit"):
        raise AssertionError("third exact prompt should hit existing cache")
    if int(third.get("actual_prefill_tokens") or 0) != 1:
        raise AssertionError("third exact prompt should prefill one trailing token")

    print("exact_prefix_result PASS")


if __name__ == "__main__":
    main()
