#!/usr/bin/env python3
"""Probe best-effort cancellation for a live raw /generate stream."""

from __future__ import annotations

import argparse
import json
import threading
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
    parser.add_argument("--repeats", type=int, default=96)
    parser.add_argument("--max-tokens", type=int, default=32)
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
            f"Cancellation probe id {probe_id}.",
            *(
                f"Segment {index}: keep prompt prefill long enough to cancel "
                "through the resident request registry."
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

    events: list[dict[str, Any]] = []
    cancel_response: dict[str, Any] | None = None
    cancel_error: Exception | None = None

    def cancel(request_id: str) -> None:
        nonlocal cancel_response, cancel_error
        try:
            cancel_response = request_json(
                "POST",
                f"{base_url}/engine/requests/{request_id}/cancel",
            )
        except Exception as exc:  # pragma: no cover - diagnostic path
            cancel_error = exc

    req = urllib.request.Request(
        f"{base_url}/generate",
        data=json.dumps(payload).encode(),
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    cancel_thread: threading.Thread | None = None
    with urllib.request.urlopen(req, timeout=180) as resp:
        for raw_line in resp:
            line = raw_line.decode().strip()
            if not line:
                continue
            event = json.loads(line)
            events.append(event)
            if event["type"] == "prompt_progress" and cancel_thread is None:
                cancel_thread = threading.Thread(
                    target=cancel,
                    args=(event["request_id"],),
                    daemon=True,
                )
                cancel_thread.start()
            if event["type"] in {"cancelled", "final", "error"}:
                break

    if cancel_thread is not None:
        cancel_thread.join(timeout=10)
    if cancel_error is not None:
        raise AssertionError(f"cancel request failed: {cancel_error}")
    if cancel_response is None or not cancel_response.get("ok"):
        raise AssertionError(f"cancel response was not ok: {cancel_response}")

    progress_events = [event for event in events if event["type"] == "prompt_progress"]
    cancelled_events = [event for event in events if event["type"] == "cancelled"]
    token_events = [event for event in events if event["type"] == "token"]
    if not cancelled_events:
        raise AssertionError(f"stream did not emit cancelled event: {events[-3:]}")
    cancelled = cancelled_events[-1]
    registry = request_json("GET", f"{base_url}/engine/requests")
    completed = registry.get("completed", [])
    request_state = next(
        (
            entry
            for entry in completed
            if entry.get("request_id") == cancelled["request_id"]
        ),
        None,
    )
    if request_state is None or request_state.get("status") != "cancelled":
        raise AssertionError(f"registry did not record cancellation: {request_state}")

    print(
        "cancel_request",
        cancelled["request_id"],
        len(progress_events),
        len(token_events),
        cancelled.get("prompt_progress_events"),
        request_state.get("status"),
        cancel_response["request"].get("status"),
    )
    request_json(
        "POST",
        f"{base_url}/engine/config",
        {"engine_preset": "sync-safe", "prefix_cache_population_mode": "sync"},
    )
    print("cancel_request_result PASS")


if __name__ == "__main__":
    main()
