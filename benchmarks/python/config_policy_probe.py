#!/usr/bin/env python3
"""Probe resident MLX runtime config changes through HTTP only."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import urllib.request
from typing import Any


def request_json(
    method: str,
    url: str,
    payload: dict[str, Any] | None = None,
    *,
    timeout: int = 120,
) -> dict[str, Any]:
    data = None
    headers = {}
    if payload is not None:
        data = json.dumps(payload).encode()
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode())


def state_tuple(health: dict[str, Any]) -> tuple[Any, ...]:
    return (
        health["engine_preset"],
        health["prefix_cache_policy"]["population_mode"],
        health["prefix_kv_cache"]["max_entries"],
        health["prefix_cache_policy"]["memory_limit_bytes"],
        health["scheduler"]["max_queued_requests"],
    )


def print_state(label: str, health: dict[str, Any]) -> None:
    print(label, *state_tuple(health))


def assert_state(
    health: dict[str, Any],
    *,
    preset: str,
    population_mode: str,
    max_entries: int,
    memory_limit_bytes: int | None,
    max_queued_requests: int,
) -> None:
    actual = state_tuple(health)
    expected = (
        preset,
        population_mode,
        max_entries,
        memory_limit_bytes,
        max_queued_requests,
    )
    if actual != expected:
        raise AssertionError(f"unexpected state: actual={actual!r} expected={expected!r}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8765")
    parser.add_argument(
        "--skip-smoke",
        action="store_true",
        help="Only probe config transitions; do not run smoke_resident_service.py.",
    )
    args = parser.parse_args()
    base_url = args.base_url.rstrip("/")

    initial = request_json("GET", f"{base_url}/health")
    print_state("initial_config", initial)

    dry_run_payload = {
        "dry_run": True,
        "engine_preset": "memory-saver",
        "prefix_cache_max_entries": 3,
    }
    dry_run = request_json("POST", f"{base_url}/engine/config", dry_run_payload)
    after_dry_run = request_json("GET", f"{base_url}/health")
    if state_tuple(after_dry_run) != state_tuple(initial):
        raise AssertionError("dry-run config mutated runtime state")
    planned_state = dry_run["planned_state"]
    print(
        "dry_run_config",
        planned_state["engine_preset"],
        planned_state["prefix_cache_policy"]["population_mode"],
        planned_state["prefix_kv_cache"]["max_entries"],
        planned_state["prefix_cache_policy"]["memory_limit_bytes"],
        planned_state["scheduler"]["max_queued_requests"],
    )

    async_result = request_json(
        "POST",
        f"{base_url}/engine/config",
        {"engine_preset": "async-experimental"},
    )
    async_health = request_json("GET", f"{base_url}/health")
    assert_state(
        async_health,
        preset="async-experimental",
        population_mode="async",
        max_entries=16,
        memory_limit_bytes=None,
        max_queued_requests=16,
    )
    print_state("apply_async", async_health)
    print("apply_async_changes", ",".join(sorted(async_result["changes"].keys())))

    request_result = request_json(
        "POST",
        f"{base_url}/engine/config",
        {"engine_preset": "request-derived"},
    )
    request_health = request_json("GET", f"{base_url}/health")
    assert_state(
        request_health,
        preset="request-derived",
        population_mode="request",
        max_entries=16,
        memory_limit_bytes=None,
        max_queued_requests=16,
    )
    print_state("apply_request_derived", request_health)
    print(
        "apply_request_derived_changes",
        ",".join(sorted(request_result["changes"].keys())),
    )

    memory_result = request_json(
        "POST",
        f"{base_url}/engine/config",
        {"engine_preset": "memory-saver", "prefix_cache_max_entries": 3},
    )
    memory_health = request_json("GET", f"{base_url}/health")
    assert_state(
        memory_health,
        preset="memory-saver",
        population_mode="sync",
        max_entries=3,
        memory_limit_bytes=67108864,
        max_queued_requests=8,
    )
    print_state("apply_memory_saver_override", memory_health)
    print("apply_memory_changes", ",".join(sorted(memory_result["changes"].keys())))

    sync_result = request_json(
        "POST",
        f"{base_url}/engine/config",
        {"engine_preset": "sync-safe"},
    )
    sync_health = request_json("GET", f"{base_url}/health")
    assert_state(
        sync_health,
        preset="sync-safe",
        population_mode="sync",
        max_entries=16,
        memory_limit_bytes=None,
        max_queued_requests=16,
    )
    print_state("restore_sync_safe", sync_health)
    print("restore_changes", ",".join(sorted(sync_result["changes"].keys())))

    if args.skip_smoke:
        return

    smoke_cmd = [
        sys.executable,
        "benchmarks/python/smoke_resident_service.py",
        "--base-url",
        base_url,
        "--skip-lifecycle",
    ]
    completed = subprocess.run(smoke_cmd, check=True, text=True, capture_output=True)
    for line in completed.stdout.splitlines():
        print("smoke_after_config", line)


if __name__ == "__main__":
    main()
