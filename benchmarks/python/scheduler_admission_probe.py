#!/usr/bin/env python3
"""Probe resident MLX scheduler admission and queue metrics."""

from __future__ import annotations

import argparse
import json
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
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


def generate_one(base_url: str, index: int, max_tokens: int) -> dict[str, Any]:
    started = time.perf_counter()
    try:
        response = request_json(
            "POST",
            f"{base_url}/v1/completions",
            {
                "model": "local-gpt-oss",
                "prompt": (
                    f"Scheduler probe request {index}. "
                    "Answer with a short sentence about local MLX inference."
                ),
                "max_tokens": max_tokens,
                "policy": "auto",
            },
        )
        elapsed_ms = 1e3 * (time.perf_counter() - started)
        metrics = response["engine_metrics"]
        return {
            "ok": True,
            "index": index,
            "elapsed_ms": elapsed_ms,
            "request_id": metrics["request_id"],
        "scheduler_queue_wait_ms": metrics.get("scheduler_queue_wait_ms"),
        "engine_lock_wait_ms": metrics.get("engine_lock_wait_ms"),
            "scheduler_active_requests_at_admit": metrics.get(
                "scheduler_active_requests_at_admit"
            ),
            "scheduler_queued_requests_at_admit": metrics.get(
                "scheduler_queued_requests_at_admit"
            ),
            "service_request_ms": metrics.get("service_request_ms"),
            "run_ms": metrics["run_ms"],
            "prompt_tokens": metrics["prompt_tokens"],
            "generation_tokens": metrics["generation_tokens"],
        }
    except urllib.error.HTTPError as exc:
        elapsed_ms = 1e3 * (time.perf_counter() - started)
        detail = exc.read().decode(errors="replace")
        return {
            "ok": False,
            "index": index,
            "elapsed_ms": elapsed_ms,
            "status": exc.code,
            "detail": detail,
        }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8765")
    parser.add_argument("--requests", type=int, default=3)
    parser.add_argument("--max-workers", type=int, default=3)
    parser.add_argument("--max-tokens", type=int, default=16)
    args = parser.parse_args()

    base_url = args.base_url.rstrip("/")
    before = request_json("GET", f"{base_url}/health")["scheduler"]
    print(
        "scheduler_before",
        before["max_concurrent_requests"],
        before["max_queued_requests"],
        before["active_requests"],
        before["queued_requests"],
        before["total_admitted"],
        before["total_rejected"],
    )

    rows = []
    with ThreadPoolExecutor(max_workers=args.max_workers) as executor:
        futures = [
            executor.submit(generate_one, base_url, index, args.max_tokens)
            for index in range(1, args.requests + 1)
        ]
        for future in as_completed(futures):
            row = future.result()
            rows.append(row)
            if row["ok"]:
                print(
                    "scheduler_probe",
                    row["index"],
                    round(row["scheduler_queue_wait_ms"] or 0.0, 2),
                row["scheduler_active_requests_at_admit"],
                row["scheduler_queued_requests_at_admit"],
                round(row["engine_lock_wait_ms"] or 0.0, 2),
                round(row["service_request_ms"] or 0.0, 2),
                round(row["elapsed_ms"], 2),
            )
            else:
                print(
                    "scheduler_rejected",
                    row["index"],
                    row["status"],
                    round(row["elapsed_ms"], 2),
                    row["detail"],
                )

    after = request_json("GET", f"{base_url}/health")["scheduler"]
    print(
        "scheduler_after",
        after["active_requests"],
        after["queued_requests"],
        after["total_admitted"],
        after["total_completed"],
        after["total_rejected"],
        round(after["mean_queue_wait_ms"], 2),
        round(after["max_observed_queue_wait_ms"], 2),
    )


if __name__ == "__main__":
    main()
