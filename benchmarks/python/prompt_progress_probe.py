#!/usr/bin/env python3
"""Probe native MLX prompt progress callback telemetry."""

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


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8765")
    parser.add_argument("--prefill-step-size", type=int, default=16)
    parser.add_argument("--repeats", type=int, default=64)
    parser.add_argument("--max-tokens", type=int, default=4)
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
        {"engine_preset": "sync-safe", "prefix_cache_population_mode": "off"},
    )
    request_json(
        "POST",
        f"{base_url}/engine/cache/prune",
        {"target_entries": 0, "clear_mlx_cache": False},
    )

    probe_id = uuid.uuid4().hex
    prompt = "\n".join(
        [
            f"Prompt progress probe id {probe_id}.",
            *(
                f"Segment {index}: measure native MLX prefill callback progress "
                "for long resident prompts."
                for index in range(args.repeats)
            ),
        ]
    )
    response = request_json(
        "POST",
        f"{base_url}/v1/completions",
        {
            "model": "local-mlx",
            "prompt": prompt,
            "max_tokens": args.max_tokens,
            "policy": "auto",
            "prefill_step_size": args.prefill_step_size,
        },
    )
    metrics = response["engine_metrics"]
    print(
        "prompt_progress",
        metrics.get("prompt_tokens"),
        metrics.get("actual_prefill_tokens"),
        metrics.get("prefill_step_size"),
        metrics.get("prompt_progress_events"),
        metrics.get("prompt_progress_processed_tokens"),
        metrics.get("prompt_progress_total_tokens"),
        metrics.get("prompt_progress_complete"),
        round(float(metrics.get("prompt_progress_last_ms") or 0.0), 2),
    )
    print("prompt_progress_trace", json.dumps(metrics.get("prompt_progress_trace")))

    events = int(metrics.get("prompt_progress_events") or 0)
    processed = int(metrics.get("prompt_progress_processed_tokens") or 0)
    total = int(metrics.get("prompt_progress_total_tokens") or 0)
    actual = int(metrics.get("actual_prefill_tokens") or 0)
    if events < 3:
        raise AssertionError(f"expected multiple prompt progress events, got {events}")
    if not metrics.get("prompt_progress_complete"):
        raise AssertionError("prompt progress did not complete")
    if processed != total:
        raise AssertionError("prompt progress processed token count did not reach total")
    if total != actual:
        raise AssertionError("prompt progress total does not match actual prefill")

    request_json(
        "POST",
        f"{base_url}/engine/config",
        {"engine_preset": "sync-safe", "prefix_cache_population_mode": "sync"},
    )
    print("prompt_progress_result PASS")


if __name__ == "__main__":
    main()
