#!/usr/bin/env python3
"""Concurrent traffic plus cancellation pressure probe for the resident engine."""

from __future__ import annotations

import argparse
import json
import threading
import time
import urllib.error
import urllib.request
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any


def request_json(
    method: str,
    url: str,
    payload: dict[str, Any] | None = None,
    *,
    timeout: int = 240,
) -> dict[str, Any]:
    data = None
    headers = {}
    if payload is not None:
        data = json.dumps(payload).encode()
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode())


def completion(base_url: str, *, index: int, max_tokens: int) -> dict[str, Any]:
    started = time.perf_counter()
    try:
        response = request_json(
            "POST",
            f"{base_url}/v1/completions",
            {
                "model": "local-mlx",
                "prompt": (
                    f"Concurrent pressure request {index} {uuid.uuid4().hex}. "
                    "Answer with one compact MLX scheduling observation."
                ),
                "max_tokens": max_tokens,
                "policy": "auto",
            },
            timeout=300,
        )
        metrics = response["engine_metrics"]
        return {
            "ok": True,
            "index": index,
            "elapsed_ms": 1e3 * (time.perf_counter() - started),
            "request_id": metrics["request_id"],
            "scheduler_queue_wait_ms": metrics.get("scheduler_queue_wait_ms"),
            "engine_lock_wait_ms": metrics.get("engine_lock_wait_ms"),
            "service_request_ms": metrics.get("service_request_ms"),
            "generation_tokens": metrics.get("generation_tokens"),
        }
    except urllib.error.HTTPError as exc:
        return {
            "ok": False,
            "index": index,
            "elapsed_ms": 1e3 * (time.perf_counter() - started),
            "status": exc.code,
            "detail": exc.read().decode(errors="replace"),
        }


def cancel_stream(
    base_url: str,
    *,
    repeats: int,
    prefill_step_size: int,
    max_tokens: int,
) -> dict[str, Any]:
    probe_id = uuid.uuid4().hex
    prompt = "\n".join(
        [
            f"Concurrent cancellation pressure probe {probe_id}.",
            *(
                f"Segment {index}: keep prompt prefill active long enough for "
                "queued foreground clients to stack behind cancellation."
                for index in range(repeats)
            ),
        ]
    )
    payload = {
        "prompt": prompt,
        "max_tokens": max_tokens,
        "policy": "auto",
        "prefill_step_size": prefill_step_size,
        "stream": True,
    }
    req = urllib.request.Request(
        f"{base_url}/generate",
        data=json.dumps(payload).encode(),
        method="POST",
        headers={"Content-Type": "application/json"},
    )

    events: list[dict[str, Any]] = []
    cancel_response: dict[str, Any] | None = None
    cancel_error: Exception | None = None

    def cancel(request_id: str) -> None:
        nonlocal cancel_response, cancel_error
        try:
            cancel_response = request_json(
                "POST",
                f"{base_url}/engine/requests/{request_id}/cancel",
                timeout=120,
            )
        except Exception as exc:  # pragma: no cover - diagnostic path
            cancel_error = exc

    cancel_thread: threading.Thread | None = None
    with urllib.request.urlopen(req, timeout=300) as resp:
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
        cancel_thread.join(timeout=15)
    if cancel_error is not None:
        raise AssertionError(f"cancel request failed: {cancel_error}")
    if cancel_response is None or not cancel_response.get("ok"):
        raise AssertionError(f"cancel response was not ok: {cancel_response}")

    progress_events = [event for event in events if event["type"] == "prompt_progress"]
    token_events = [event for event in events if event["type"] == "token"]
    cancelled_events = [event for event in events if event["type"] == "cancelled"]
    if not cancelled_events:
        raise AssertionError(f"stream did not emit cancelled event: {events[-3:]}")
    if token_events:
        raise AssertionError("cancelled pressure stream emitted token events")

    cancelled = cancelled_events[-1]
    return {
        "request_id": cancelled["request_id"],
        "progress_events": len(progress_events),
        "token_events": len(token_events),
        "cancel_status": cancel_response["request"].get("status"),
        "cancelled_event": cancelled,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8765")
    parser.add_argument("--clients", type=int, default=4)
    parser.add_argument("--client-workers", type=int, default=4)
    parser.add_argument("--client-max-tokens", type=int, default=8)
    parser.add_argument("--cancel-repeats", type=int, default=128)
    parser.add_argument("--prefill-step-size", type=int, default=16)
    parser.add_argument("--cancel-max-tokens", type=int, default=32)
    args = parser.parse_args()
    base_url = args.base_url.rstrip("/")

    health = request_json("GET", f"{base_url}/health")
    print("health", health["ok"], health["device"]["default_device"])
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
    before = request_json("GET", f"{base_url}/health")
    before_scheduler = before["scheduler"]
    before_entries = int(before["prefix_kv_cache"]["entries"])

    with ThreadPoolExecutor(max_workers=args.client_workers + 1) as executor:
        cancel_future = executor.submit(
            cancel_stream,
            base_url,
            repeats=args.cancel_repeats,
            prefill_step_size=args.prefill_step_size,
            max_tokens=args.cancel_max_tokens,
        )
        time.sleep(0.05)
        client_futures = [
            executor.submit(
                completion,
                base_url,
                index=index,
                max_tokens=args.client_max_tokens,
            )
            for index in range(1, args.clients + 1)
        ]
        client_rows = [future.result() for future in as_completed(client_futures)]
        cancel_row = cancel_future.result()

    failures = [row for row in client_rows if not row["ok"]]
    successes = [row for row in client_rows if row["ok"]]
    if failures:
        raise AssertionError(f"concurrent clients failed: {failures}")
    if len(successes) != args.clients:
        raise AssertionError(f"expected {args.clients} successful clients: {client_rows}")

    registry = request_json("GET", f"{base_url}/engine/requests")
    completed = registry.get("completed", [])
    cancelled_state = next(
        (
            entry
            for entry in completed
            if entry.get("request_id") == cancel_row["request_id"]
        ),
        None,
    )
    if cancelled_state is None or cancelled_state.get("status") != "cancelled":
        raise AssertionError(f"registry did not retain cancelled state: {cancelled_state}")

    after = request_json("GET", f"{base_url}/health")
    after_scheduler = after["scheduler"]
    after_entries = int(after["prefix_kv_cache"]["entries"])
    if after_entries != before_entries:
        raise AssertionError(
            f"cache entries changed while cache population was off: "
            f"{before_entries} -> {after_entries}"
        )
    if after_scheduler["active_requests"] != 0 or after_scheduler["queued_requests"] != 0:
        raise AssertionError(f"scheduler not idle after pressure probe: {after_scheduler}")

    queue_waits = [
        float(row.get("scheduler_queue_wait_ms") or 0.0) for row in successes
    ]
    if max(queue_waits) <= 0:
        raise AssertionError("pressure clients did not exercise scheduler queueing")

    print(
        "concurrent_cancel",
        cancel_row["request_id"],
        cancel_row["progress_events"],
        cancel_row["token_events"],
        cancel_row["cancel_status"],
        cancelled_state.get("status"),
    )
    for row in sorted(successes, key=lambda item: item["index"]):
        print(
            "concurrent_client",
            row["index"],
            round(float(row["scheduler_queue_wait_ms"] or 0.0), 2),
            round(float(row["engine_lock_wait_ms"] or 0.0), 2),
            round(float(row["service_request_ms"] or 0.0), 2),
            row["generation_tokens"],
        )
    print(
        "concurrent_scheduler",
        before_scheduler["total_admitted"],
        after_scheduler["total_admitted"],
        after_scheduler["total_completed"],
        after_scheduler["total_rejected"],
        round(float(after_scheduler["mean_queue_wait_ms"] or 0.0), 2),
        round(float(after_scheduler["max_observed_queue_wait_ms"] or 0.0), 2),
    )
    request_json(
        "POST",
        f"{base_url}/engine/config",
        {"engine_preset": "sync-safe", "prefix_cache_population_mode": "sync"},
    )
    print("concurrent_cancel_pressure_result PASS")


if __name__ == "__main__":
    main()
