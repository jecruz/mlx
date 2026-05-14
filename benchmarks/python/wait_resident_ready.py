#!/usr/bin/env python3
"""Wait for resident MLX service readiness."""

from __future__ import annotations

import argparse
import json
import time
import urllib.error
import urllib.request
from typing import Any


def request_json(url: str, *, timeout: float) -> dict[str, Any]:
    with urllib.request.urlopen(url, timeout=timeout) as resp:
        return json.loads(resp.read().decode())


def warmup_state(health: dict[str, Any]) -> dict[str, Any]:
    warmup = health.get("warmup")
    if isinstance(warmup, dict):
        return warmup

    # Backward-compatible inference for services started before /health.warmup
    # existed. Those services only reported warmup_results.
    results = health.get("warmup_results")
    if isinstance(results, list) and results:
        return {
            "mode": "legacy",
            "running": False,
            "completed": True,
            "error": None,
            "result_count": len(results),
        }
    return {
        "mode": "unknown",
        "running": False,
        "completed": False,
        "error": None,
        "result_count": 0,
    }


def readiness_status(
    health: dict[str, Any],
    *,
    require_gpu: bool,
    require_warmup: bool,
) -> tuple[bool, str, dict[str, Any]]:
    if not health.get("ok"):
        return False, "health_not_ok", {}
    if not health.get("loaded", True):
        return False, "model_not_loaded", {}

    device = health.get("device") or {}
    default_device = str(device.get("default_device", ""))
    if require_gpu and "gpu" not in default_device:
        return False, "gpu_not_active", {"default_device": default_device}

    warmup = warmup_state(health)
    if warmup.get("error"):
        return False, "warmup_error", warmup
    if require_warmup and not warmup.get("completed"):
        return False, "warmup_not_complete", warmup

    return True, "ready", warmup


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8765")
    parser.add_argument("--timeout-s", type=float, default=120.0)
    parser.add_argument("--poll-interval-s", type=float, default=0.25)
    parser.add_argument("--request-timeout-s", type=float, default=2.0)
    parser.add_argument("--require-gpu", action="store_true")
    parser.add_argument("--require-warmup", action="store_true")
    parser.add_argument("--json", action="store_true", help="Print final health JSON.")
    args = parser.parse_args()

    base_url = args.base_url.rstrip("/")
    deadline = time.time() + args.timeout_s
    last_reason = "not_checked"
    last_detail: dict[str, Any] = {}
    last_error = None

    while time.time() < deadline:
        try:
            health = request_json(
                f"{base_url}/health",
                timeout=args.request_timeout_s,
            )
            ready, reason, detail = readiness_status(
                health,
                require_gpu=args.require_gpu,
                require_warmup=args.require_warmup,
            )
            last_reason = reason
            last_detail = detail
            if ready:
                warmup = warmup_state(health)
                if args.json:
                    print(json.dumps(health, sort_keys=True))
                print(
                    "resident_ready",
                    True,
                    health.get("engine_preset"),
                    (health.get("device") or {}).get("default_device"),
                    warmup.get("mode"),
                    warmup.get("completed"),
                    warmup.get("result_count"),
                    flush=True,
                )
                return 0
        except (urllib.error.URLError, TimeoutError, ConnectionError) as exc:
            last_error = str(exc)
            last_reason = "request_failed"
        time.sleep(args.poll_interval_s)

    print(
        "resident_ready",
        False,
        last_reason,
        json.dumps(last_detail, sort_keys=True),
        last_error or "",
        flush=True,
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
