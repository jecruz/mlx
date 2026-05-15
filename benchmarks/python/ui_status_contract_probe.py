#!/usr/bin/env python3
"""Validate the UI-facing resident engine status contract."""

from __future__ import annotations

import argparse
import json
import urllib.request
from pathlib import Path
from typing import Any


def request_json(url: str, *, timeout: int = 120) -> dict[str, Any]:
    with urllib.request.urlopen(url, timeout=timeout) as resp:
        return json.loads(resp.read().decode())


def require_keys(name: str, obj: dict[str, Any], keys: list[str]) -> None:
    missing = [key for key in keys if key not in obj]
    if missing:
        raise RuntimeError(f"{name} missing keys: {missing}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8765")
    parser.add_argument(
        "--output-json",
        type=Path,
        default=Path("ui-status-contract-m25.json"),
    )
    args = parser.parse_args()

    status = request_json(f"{args.base_url.rstrip('/')}/engine/ui")
    require_keys(
        "ui status",
        status,
        [
            "ok",
            "loaded",
            "model",
            "runtime_profile",
            "engine_preset",
            "profiles",
            "readiness",
            "controls",
            "cache",
            "scheduler",
            "memory",
            "metrics",
        ],
    )
    require_keys(
        "readiness",
        status["readiness"],
        [
            "loaded",
            "gpu_ready",
            "warm",
            "continuation_ready",
            "strategy",
            "blockers",
            "required_lower_level_work",
        ],
    )
    require_keys(
        "controls",
        status["controls"],
        ["can_reload", "can_unload", "can_configure", "can_generate"],
    )
    require_keys(
        "cache",
        status["cache"],
        [
            "population_mode",
            "pending_wait_ms",
            "pending_wait_hits",
            "pending_build_deduplications",
            "entries",
            "max_entries",
            "memory_limit_bytes",
        ],
    )
    expected_profiles = {
        "interactive",
        "agent-workspace",
        "memory-saver",
        "diagnostics",
    }
    if set(status["profiles"]) != expected_profiles:
        raise RuntimeError(f"unexpected profile catalog: {status['profiles'].keys()}")
    if not status["loaded"]:
        raise RuntimeError(f"engine is not loaded: {status}")
    if not status["readiness"]["gpu_ready"]:
        raise RuntimeError(f"GPU is not ready: {status['readiness']}")
    if status["readiness"]["strategy"] not in {
        "direct_cache_reuse",
        "split_prefill_or_async_build",
    }:
        raise RuntimeError(f"unexpected cache strategy: {status['readiness']}")

    payload = {
        "ok": True,
        "loaded": status["loaded"],
        "runtime_profile": status["runtime_profile"],
        "engine_preset": status["engine_preset"],
        "gpu_ready": status["readiness"]["gpu_ready"],
        "warm": status["readiness"]["warm"],
        "strategy": status["readiness"]["strategy"],
        "profiles": sorted(status["profiles"]),
        "can_generate": status["controls"]["can_generate"],
    }
    args.output_json.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    print(
        "m25_ui_status",
        payload["ok"],
        "loaded",
        payload["loaded"],
        "profile",
        payload["runtime_profile"],
        "strategy",
        payload["strategy"],
        "profiles",
        ",".join(payload["profiles"]),
        args.output_json,
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
