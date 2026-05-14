#!/usr/bin/env python3
"""Probe live prompt-progress events from the raw /generate JSONL stream."""

from __future__ import annotations

import argparse
import json
import time
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
            f"Live prompt progress probe id {probe_id}.",
            *(
                f"Segment {index}: stream prompt progress before token decode "
                "for long resident prompts."
                for index in range(args.repeats)
            ),
        ]
    )
    payload = {
        "prompt": prompt,
        "max_tokens": args.max_tokens,
        "policy": "auto",
        "prefill_step_size": args.prefill_step_size,
        "stream": True,
    }
    req = urllib.request.Request(
        f"{base_url}/generate",
        data=json.dumps(payload).encode(),
        method="POST",
        headers={"Content-Type": "application/json"},
    )

    events: list[dict[str, Any]] = []
    started = time.perf_counter()
    with urllib.request.urlopen(req, timeout=180) as resp:
        for raw_line in resp:
            line = raw_line.decode().strip()
            if not line:
                continue
            event = json.loads(line)
            event["_client_elapsed_ms"] = 1e3 * (time.perf_counter() - started)
            events.append(event)
            if event["type"] == "final":
                break
            if event["type"] == "error":
                raise AssertionError(event["error"])

    progress_events = [event for event in events if event["type"] == "prompt_progress"]
    token_events = [event for event in events if event["type"] == "token"]
    final = next(event for event in events if event["type"] == "final")
    first_token_index = next(
        (index for index, event in enumerate(events) if event["type"] == "token"),
        None,
    )
    progress_before_token = [
        event
        for index, event in enumerate(events)
        if event["type"] == "prompt_progress"
        and (first_token_index is None or index < first_token_index)
    ]

    print(
        "live_prompt_progress",
        len(progress_events),
        len(progress_before_token),
        len(token_events),
        final.get("actual_prefill_tokens"),
        final.get("prompt_progress_events"),
        final.get("prompt_progress_complete"),
        round(float(final.get("stream_first_token_ms") or 0.0), 2),
    )
    if progress_events:
        print(
            "live_prompt_first",
            progress_events[0].get("processed_tokens"),
            progress_events[0].get("total_tokens"),
            round(float(progress_events[0].get("_client_elapsed_ms") or 0.0), 2),
        )
        print(
            "live_prompt_last",
            progress_events[-1].get("processed_tokens"),
            progress_events[-1].get("total_tokens"),
            round(float(progress_events[-1].get("_client_elapsed_ms") or 0.0), 2),
        )

    if len(progress_events) < 3:
        raise AssertionError("expected multiple live prompt progress events")
    if not progress_before_token:
        raise AssertionError("expected prompt progress before first token event")
    if not final.get("prompt_progress_complete"):
        raise AssertionError("final metrics did not mark prompt progress complete")
    if int(final.get("prompt_progress_events") or 0) != len(progress_events):
        raise AssertionError("final progress event count did not match streamed events")

    request_json(
        "POST",
        f"{base_url}/engine/config",
        {"engine_preset": "sync-safe", "prefix_cache_population_mode": "sync"},
    )
    print("live_prompt_progress_result PASS")


if __name__ == "__main__":
    main()
