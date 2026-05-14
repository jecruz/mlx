#!/usr/bin/env python3
"""Smoke-test the resident MLX service API surface."""

from __future__ import annotations

import argparse
import json
import urllib.request
from typing import Any


def request_json(method: str, url: str, payload: dict[str, Any] | None = None):
    data = None
    headers = {}
    if payload is not None:
        data = json.dumps(payload).encode()
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    with urllib.request.urlopen(req, timeout=120) as resp:
        return json.loads(resp.read().decode())


def request_text(method: str, url: str, payload: dict[str, Any] | None = None):
    data = None
    headers = {}
    if payload is not None:
        data = json.dumps(payload).encode()
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    with urllib.request.urlopen(req, timeout=120) as resp:
        return resp.read().decode()


def count_sse_events(text: str) -> tuple[int, bool]:
    lines = [line for line in text.splitlines() if line.startswith("data: ")]
    return len(lines), any(line == "data: [DONE]" for line in lines)


def sse_json_events(text: str) -> list[dict[str, Any]]:
    events = []
    for line in text.splitlines():
        if not line.startswith("data: ") or line == "data: [DONE]":
            continue
        events.append(json.loads(line.removeprefix("data: ")))
    return events


def final_engine_metrics(text: str) -> dict[str, Any]:
    for event in reversed(sse_json_events(text)):
        metrics = event.get("engine_metrics")
        if metrics is not None:
            return metrics
    raise AssertionError("expected final SSE event with engine_metrics")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8765")
    parser.add_argument(
        "--skip-lifecycle",
        action="store_true",
        help="Do not call /engine/unload or /engine/reload.",
    )
    args = parser.parse_args()
    base_url = args.base_url.rstrip("/")

    health = request_json("GET", f"{base_url}/health")
    print(
        "health",
        health["ok"],
        health["device"]["default_device"],
        health.get("profile_path"),
        health["metrics"]["total_requests"],
    )

    engine = request_json("GET", f"{base_url}/engine")
    print(
        "engine",
        engine["reload_count"],
        engine["profile_loaded"],
        ",".join(engine["policy_names"]),
    )

    generated = request_json(
        "POST",
        f"{base_url}/generate",
        {
            "prompt": "Give one concise reason resident inference is fast.",
            "max_tokens": 8,
            "policy": "auto",
        },
    )
    print(
        "generate",
        generated["request_id"],
        generated["effective_policy"],
        generated["prefill_step_size"],
        generated["prompt_tokens"],
        generated["generation_tokens"],
        generated["stop_reason"],
    )

    completion = request_json(
        "POST",
        f"{base_url}/v1/completions",
        {
            "model": "local-gpt-oss",
            "prompt": "Name one MLX engine metric:",
            "max_tokens": 6,
            "policy": "auto",
        },
    )
    print(
        "completion",
        completion["object"],
        completion["choices"][0]["finish_reason"],
        completion["usage"]["total_tokens"],
        completion["engine_metrics"]["effective_policy"],
    )

    chat = request_json(
        "POST",
        f"{base_url}/v1/chat/completions",
        {
            "model": "local-gpt-oss",
            "messages": [{"role": "user", "content": "Reply with one word: ready"}],
            "max_tokens": 4,
            "policy": "auto",
        },
    )
    print(
        "chat",
        chat["object"],
        chat["choices"][0]["message"]["role"],
        chat["usage"]["total_tokens"],
        chat["engine_metrics"]["prefill_step_size"],
    )

    streamed_completion = request_text(
        "POST",
        f"{base_url}/v1/completions",
        {
            "model": "local-gpt-oss",
            "prompt": "Stream one short word:",
            "max_tokens": 4,
            "policy": "auto",
            "stream": True,
        },
    )
    event_count, saw_done = count_sse_events(streamed_completion)
    print("stream_completion", event_count, saw_done)

    streamed_chat = request_text(
        "POST",
        f"{base_url}/v1/chat/completions",
        {
            "model": "local-gpt-oss",
            "messages": [{"role": "user", "content": "Stream one short word"}],
            "max_tokens": 4,
            "policy": "auto",
            "stream": True,
        },
    )
    event_count, saw_done = count_sse_events(streamed_chat)
    print("stream_chat", event_count, saw_done)

    stream_prefix = (
        f"Benchmark stream run id: {generated['request_id']}\n"
        "System: You are validating streaming prefix reuse in a resident MLX "
        "engine. Context block: alpha beta gamma delta epsilon zeta eta theta. "
        "Instruction: answer with one short word. User: "
    )
    request_text(
        "POST",
        f"{base_url}/v1/completions",
        {
            "model": "local-gpt-oss",
            "prompt": stream_prefix + "first streaming request",
            "max_tokens": 2,
            "policy": "auto",
            "stream": True,
        },
    )
    streamed_prefix_second = request_text(
        "POST",
        f"{base_url}/v1/completions",
        {
            "model": "local-gpt-oss",
            "prompt": stream_prefix + "second streaming request",
            "max_tokens": 2,
            "policy": "auto",
            "stream": True,
        },
    )
    stream_prefix_metrics = final_engine_metrics(streamed_prefix_second)
    if not stream_prefix_metrics["cache_reuse_enabled"]:
        raise AssertionError("expected streaming prefix cache reuse on second request")
    print(
        "stream_prefix",
        stream_prefix_metrics["longest_prefix_match_tokens"],
        round(stream_prefix_metrics["prefix_reuse_ratio"], 3),
        stream_prefix_metrics["cache_candidate"],
        stream_prefix_metrics.get("cache_reuse_enabled"),
        stream_prefix_metrics.get("cache_hit"),
        stream_prefix_metrics.get("cache_created"),
        round(stream_prefix_metrics.get("cache_prepare_ms") or 0.0, 2),
        stream_prefix_metrics.get("cached_prefix_tokens"),
        stream_prefix_metrics.get("actual_prefill_tokens"),
        round(stream_prefix_metrics.get("stream_first_token_ms") or 0.0, 2),
        round(stream_prefix_metrics.get("stream_mean_token_gap_ms") or 0.0, 2),
    )

    shared_prefix = (
        "System: You are benchmarking repeated prefix reuse in a resident MLX "
        "engine. Context block: alpha beta gamma delta epsilon zeta eta theta. "
        "Instruction: answer with one short word. User: "
    )
    prefix_first = request_json(
        "POST",
        f"{base_url}/v1/completions",
        {
            "model": "local-gpt-oss",
            "prompt": shared_prefix + "first request",
            "max_tokens": 2,
            "policy": "auto",
        },
    )
    prefix_second = request_json(
        "POST",
        f"{base_url}/v1/completions",
        {
            "model": "local-gpt-oss",
            "prompt": shared_prefix + "second request",
            "max_tokens": 2,
            "policy": "auto",
        },
    )
    prefix_metrics = prefix_second["engine_metrics"]
    if prefix_metrics["longest_prefix_match_tokens"] <= 0:
        raise AssertionError("expected shared-prefix metrics on second related request")
    print(
        "prefix",
        prefix_first["engine_metrics"]["cache_candidate"],
        prefix_metrics["longest_prefix_match_tokens"],
        round(prefix_metrics["prefix_reuse_ratio"], 3),
        prefix_metrics["cache_candidate"],
        prefix_metrics.get("cache_reuse_enabled"),
        prefix_metrics.get("cache_hit"),
        prefix_metrics.get("cache_created"),
        round(prefix_metrics.get("cache_prepare_ms") or 0.0, 2),
        prefix_metrics.get("cached_prefix_tokens"),
        prefix_metrics.get("actual_prefill_tokens"),
    )

    metrics = request_json("GET", f"{base_url}/metrics")
    print(
        "metrics",
        metrics["total_requests"],
        metrics["successful_requests"],
        metrics["failed_requests"],
        len(metrics["recent_requests"]),
        metrics["cache_candidate_requests"],
    )

    if args.skip_lifecycle:
        return

    unloaded = request_json("POST", f"{base_url}/engine/unload")
    print(
        "unload",
        unloaded["loaded"],
        unloaded["unload_count"],
        unloaded["model"],
    )

    reloaded = request_json(
        "POST",
        f"{base_url}/engine/reload",
        {"warmup_prompt_tokens": "64"},
    )
    print(
        "reload",
        reloaded["reload_count"],
        reloaded["device"]["default_device"],
        reloaded["profile_loaded"],
        reloaded["warmup_prompt_tokens"],
    )


if __name__ == "__main__":
    main()
