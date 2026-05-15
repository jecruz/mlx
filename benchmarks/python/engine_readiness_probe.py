#!/usr/bin/env python3
"""Validate the resident MLX engine exposes the M20-M22 readiness surface."""

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


def require_keys(name: str, obj: dict[str, Any], keys: list[str]) -> None:
    missing = [key for key in keys if key not in obj]
    if missing:
        raise RuntimeError(f"{name} is missing keys: {missing}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8765")
    parser.add_argument(
        "--output-json",
        type=Path,
        default=Path("engine-readiness-m23.json"),
    )
    args = parser.parse_args()

    base_url = args.base_url.rstrip("/")
    health = request_json("GET", f"{base_url}/health")
    dry_run = request_json(
        "POST",
        f"{base_url}/engine/config",
        {
            "dry_run": True,
            "engine_preset": "async-experimental",
            "prefix_cache_pending_wait_ms": 1000,
        },
    )

    policy = health["prefix_cache_policy"]
    continuation = health["prompt_cache_continuation"]
    device = health["device"]
    require_keys(
        "prefix_cache_policy",
        policy,
        [
            "existing_build_reuses",
            "pending_build_deduplications",
            "pending_wait_ms",
            "pending_waits",
            "pending_wait_hits",
            "pending_wait_timeouts",
            "pending_wait_misses",
            "pending_wait_total_ms",
        ],
    )
    require_keys(
        "prompt_cache_continuation",
        continuation,
        [
            "mlx_lm_version",
            "native_replay_free_prefix_store_supported",
            "replay_free_supported_entries",
            "blocked_entries",
            "blocked_classes",
            "blocker_reasons",
            "safe_request_prefix_store_strategy",
            "required_lower_level_work",
        ],
    )
    planned_policy = dry_run["planned_state"]["prefix_cache_policy"]
    require_keys(
        "dry_run planned prefix policy",
        planned_policy,
        [
            "population_mode",
            "async_idle_timeout_ms",
            "async_idle_grace_ms",
            "pending_wait_ms",
        ],
    )
    if not health["ok"]:
        raise RuntimeError(f"health is not ok: {health}")
    if not device.get("metal_available") or "gpu" not in device.get(
        "default_device",
        "",
    ):
        raise RuntimeError(f"MLX is not using Metal GPU: {device}")
    if dry_run["dry_run"] is not True:
        raise RuntimeError(f"config dry-run did not stay dry: {dry_run}")
    if planned_policy["pending_wait_ms"] != 1000:
        raise RuntimeError(f"pending wait dry-run did not plan correctly: {dry_run}")

    payload = {
        "ok": True,
        "model": health["model"],
        "backend": health["backend"],
        "device": device,
        "engine_preset": health["engine_preset"],
        "mlx_lm_version": continuation["mlx_lm_version"],
        "policy_controls_present": True,
        "continuation_report_present": True,
        "dry_run_config_present": True,
        "native_replay_free_prefix_store_supported": continuation[
            "native_replay_free_prefix_store_supported"
        ],
        "safe_request_prefix_store_strategy": continuation[
            "safe_request_prefix_store_strategy"
        ],
        "required_lower_level_work": continuation["required_lower_level_work"],
    }
    args.output_json.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    print(
        "m23_readiness",
        payload["ok"],
        "backend",
        payload["backend"],
        "device",
        payload["device"]["default_device"],
        "mlx_lm",
        payload["mlx_lm_version"],
        "strategy",
        payload["safe_request_prefix_store_strategy"],
        args.output_json,
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
