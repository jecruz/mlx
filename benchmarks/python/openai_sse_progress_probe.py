#!/usr/bin/env python3
"""Probe OpenAI-compatible SSE prompt-progress comments."""

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
            f"OpenAI SSE progress probe id {probe_id}.",
            *(
                f"Segment {index}: emit SSE prompt progress comments before "
                "OpenAI-compatible data chunks."
                for index in range(args.repeats)
            ),
        ]
    )
    payload = {
        "model": "local-mlx",
        "prompt": prompt,
        "max_tokens": args.max_tokens,
        "policy": "auto",
        "prefill_step_size": args.prefill_step_size,
        "stream": True,
    }
    req = urllib.request.Request(
        f"{base_url}/v1/completions",
        data=json.dumps(payload).encode(),
        method="POST",
        headers={"Content-Type": "application/json"},
    )

    comments: list[dict[str, Any]] = []
    data_chunks: list[dict[str, Any]] = []
    comments_before_data = 0
    saw_data = False
    started = time.perf_counter()
    with urllib.request.urlopen(req, timeout=180) as resp:
        for raw_line in resp:
            line = raw_line.decode().strip()
            if not line:
                continue
            if line.startswith(": prompt_progress "):
                payload_text = line.removeprefix(": prompt_progress ")
                comment = json.loads(payload_text)
                comment["_client_elapsed_ms"] = 1e3 * (time.perf_counter() - started)
                comments.append(comment)
                if not saw_data:
                    comments_before_data += 1
                continue
            if line.startswith("data: "):
                data = line.removeprefix("data: ")
                if data == "[DONE]":
                    break
                saw_data = True
                data_chunks.append(json.loads(data))

    final_metrics = None
    for chunk in reversed(data_chunks):
        if "engine_metrics" in chunk:
            final_metrics = chunk["engine_metrics"]
            break
    if final_metrics is None:
        raise AssertionError("expected final OpenAI SSE chunk with engine_metrics")

    print(
        "openai_sse_progress",
        len(comments),
        comments_before_data,
        len(data_chunks),
        final_metrics.get("actual_prefill_tokens"),
        final_metrics.get("prompt_progress_events"),
        final_metrics.get("prompt_progress_complete"),
        round(float(final_metrics.get("stream_first_token_ms") or 0.0), 2),
    )
    if comments:
        print(
            "openai_sse_first",
            comments[0].get("processed_tokens"),
            comments[0].get("total_tokens"),
            round(float(comments[0].get("_client_elapsed_ms") or 0.0), 2),
        )
        print(
            "openai_sse_last",
            comments[-1].get("processed_tokens"),
            comments[-1].get("total_tokens"),
            round(float(comments[-1].get("_client_elapsed_ms") or 0.0), 2),
        )

    if len(comments) < 3:
        raise AssertionError("expected multiple SSE prompt progress comments")
    if comments_before_data < 1:
        raise AssertionError("expected at least one progress comment before data chunk")
    if int(final_metrics.get("prompt_progress_events") or 0) != len(comments):
        raise AssertionError("final prompt progress count did not match comments")
    if not final_metrics.get("prompt_progress_complete"):
        raise AssertionError("final metrics did not mark prompt progress complete")

    request_json(
        "POST",
        f"{base_url}/engine/config",
        {"engine_preset": "sync-safe", "prefix_cache_population_mode": "sync"},
    )
    print("openai_sse_progress_result PASS")


if __name__ == "__main__":
    main()
