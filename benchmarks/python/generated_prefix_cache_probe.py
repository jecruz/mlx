#!/usr/bin/env python3
"""Probe generated-token prefix cache recording and follow-up reuse."""

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
    parser.add_argument("--first-max-tokens", type=int, default=12)
    parser.add_argument("--second-max-tokens", type=int, default=4)
    args = parser.parse_args()
    base_url = args.base_url.rstrip("/")

    health = request_json("GET", f"{base_url}/health")
    print(
        "health",
        health["ok"],
        health["device"]["default_device"],
        health.get("engine_preset"),
    )

    request_json(
        "POST",
        f"{base_url}/engine/config",
        {"engine_preset": "sync-safe", "prefix_cache_population_mode": "sync"},
    )
    request_json(
        "POST",
        f"{base_url}/engine/cache/prune",
        {"target_entries": 0, "clear_mlx_cache": False},
    )

    probe_id = uuid.uuid4().hex
    prompt = (
        f"Generated prefix cache probe {probe_id}. "
        "Write a short deterministic continuation about MLX resident inference: "
    )
    first = request_json(
        "POST",
        f"{base_url}/v1/completions",
        {
            "model": "local-mlx",
            "prompt": prompt,
            "max_tokens": args.first_max_tokens,
            "policy": "auto",
        },
    )
    first_metrics = first["engine_metrics"]
    generated_text = first["choices"][0]["text"]
    followup_prompt = prompt + generated_text + " Continue with one concise metric."
    second = request_json(
        "POST",
        f"{base_url}/v1/completions",
        {
            "model": "local-mlx",
            "prompt": followup_prompt,
            "max_tokens": args.second_max_tokens,
            "policy": "auto",
        },
    )
    second_metrics = second["engine_metrics"]

    print(
        "generated_prefix_first",
        first_metrics.get("prompt_tokens"),
        first_metrics.get("generation_tokens"),
        first_metrics.get("generated_token_count_recorded"),
        first_metrics.get("generated_prefix_cache_recorded"),
        first_metrics.get("generated_prefix_cache_tokens"),
    )
    print(
        "generated_prefix_second",
        second_metrics.get("prompt_tokens"),
        second_metrics.get("longest_prefix_match_tokens"),
        second_metrics.get("cache_reuse_enabled"),
        second_metrics.get("cache_hit"),
        second_metrics.get("cached_prefix_tokens"),
        second_metrics.get("actual_prefill_tokens"),
    )

    if not first_metrics.get("generated_prefix_cache_recorded"):
        raise AssertionError(f"generated prefix cache was not recorded: {first_metrics}")
    if int(first_metrics.get("generated_token_count_recorded") or 0) <= 0:
        raise AssertionError("first request did not record generated token ids")
    if not second_metrics.get("cache_reuse_enabled"):
        raise AssertionError("follow-up prompt did not reuse generated prefix cache")
    if not second_metrics.get("cache_hit"):
        raise AssertionError("follow-up prompt should hit generated prefix cache")
    if int(second_metrics.get("actual_prefill_tokens") or 0) >= int(
        second_metrics.get("prompt_tokens") or 0
    ):
        raise AssertionError("follow-up prompt did not reduce actual prefill tokens")

    print("generated_prefix_cache_result PASS")


if __name__ == "__main__":
    main()
