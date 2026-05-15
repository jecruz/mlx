#!/usr/bin/env python3
"""Validate product-facing runtime profiles for the resident MLX engine."""

from __future__ import annotations

import argparse
import json
import urllib.request
from pathlib import Path
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


def planned_profile(base_url: str, profile: str) -> dict[str, Any]:
    return request_json(
        "POST",
        f"{base_url}/engine/config",
        {"dry_run": True, "runtime_profile": profile},
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8765")
    parser.add_argument(
        "--output-json",
        type=Path,
        default=Path("runtime-profiles-m24.json"),
    )
    args = parser.parse_args()

    base_url = args.base_url.rstrip("/")
    catalog = request_json("GET", f"{base_url}/engine/profiles")
    profiles = catalog["profiles"]
    expected = {"interactive", "agent-workspace", "memory-saver", "diagnostics"}
    if set(profiles) != expected:
        raise RuntimeError(f"unexpected runtime profile catalog: {profiles.keys()}")

    planned = {name: planned_profile(base_url, name) for name in sorted(expected)}
    agent_policy = planned["agent-workspace"]["planned_state"]["prefix_cache_policy"]
    interactive_policy = planned["interactive"]["planned_state"][
        "prefix_cache_policy"
    ]
    memory_policy = planned["memory-saver"]["planned_state"]["prefix_cache_policy"]
    diagnostics_policy = planned["diagnostics"]["planned_state"][
        "prefix_cache_policy"
    ]
    if agent_policy["pending_wait_ms"] <= 0:
        raise RuntimeError(f"agent-workspace did not plan pending wait: {agent_policy}")
    if interactive_policy["pending_wait_ms"] != 0:
        raise RuntimeError(
            f"interactive should not wait for pending builds: {interactive_policy}"
        )
    if memory_policy["memory_limit_bytes"] != 64 * 1024 * 1024:
        raise RuntimeError(f"memory-saver memory limit mismatch: {memory_policy}")
    if diagnostics_policy["population_mode"] != "sync":
        raise RuntimeError(f"diagnostics should use sync cache mode: {diagnostics_policy}")

    applied = request_json(
        "POST",
        f"{base_url}/engine/config",
        {"runtime_profile": "agent-workspace"},
    )
    health = request_json("GET", f"{base_url}/health")
    if health.get("runtime_profile") != "agent-workspace":
        raise RuntimeError(f"runtime profile not applied: {health.get('runtime_profile')}")
    if health["prefix_cache_policy"].get("pending_wait_ms", 0) <= 0:
        raise RuntimeError(f"pending wait not applied: {health['prefix_cache_policy']}")

    request_json("POST", f"{base_url}/engine/config", {"runtime_profile": "interactive"})
    restored = request_json("GET", f"{base_url}/health")
    if restored.get("runtime_profile") != "interactive":
        raise RuntimeError(f"runtime profile not restored: {restored.get('runtime_profile')}")
    if restored["prefix_cache_policy"].get("pending_wait_ms") != 0:
        raise RuntimeError(f"interactive restore did not clear pending wait: {restored}")

    payload = {
        "ok": True,
        "profiles": sorted(profiles),
        "agent_workspace_pending_wait_ms": agent_policy["pending_wait_ms"],
        "interactive_pending_wait_ms": interactive_policy["pending_wait_ms"],
        "memory_saver_memory_limit_bytes": memory_policy["memory_limit_bytes"],
        "diagnostics_population_mode": diagnostics_policy["population_mode"],
        "applied_runtime_profile": applied["engine"]["runtime_profile"],
        "restored_runtime_profile": restored["runtime_profile"],
    }
    args.output_json.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    print(
        "m24_profiles",
        payload["ok"],
        "profiles",
        ",".join(payload["profiles"]),
        "agent_wait",
        payload["agent_workspace_pending_wait_ms"],
        "restored",
        payload["restored_runtime_profile"],
        args.output_json,
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
