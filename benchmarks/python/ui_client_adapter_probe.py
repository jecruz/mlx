#!/usr/bin/env python3
"""Validate the Python UI client adapter for resident MLX engine integrations."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from mlx_engine.ui_client import EngineUiClient


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8765")
    parser.add_argument(
        "--output-json",
        type=Path,
        default=Path("ui-client-adapter-m26.json"),
    )
    args = parser.parse_args()

    client = EngineUiClient(args.base_url)
    profiles = client.profiles()["profiles"]
    expected_profiles = {
        "interactive",
        "agent-workspace",
        "agent-workspace-async",
        "agent-workspace-request",
        "memory-saver",
        "diagnostics",
    }
    if set(profiles) != expected_profiles:
        raise RuntimeError(f"unexpected profile catalog: {profiles.keys()}")

    dry_run = client.apply_profile("agent-workspace", dry_run=True)
    planned = dry_run["planned_state"]
    if planned["runtime_profile"] != "agent-workspace":
        raise RuntimeError(f"dry-run did not plan agent-workspace: {planned}")
    if planned["prefix_cache_policy"]["pending_wait_ms"] <= 0:
        raise RuntimeError(f"agent-workspace pending wait missing: {planned}")

    async_dry_run = client.apply_profile("agent-workspace-async", dry_run=True)
    async_planned = async_dry_run["planned_state"]
    if async_planned["runtime_profile"] != "agent-workspace-async":
        raise RuntimeError(
            f"dry-run did not plan agent-workspace-async: {async_planned}"
        )
    if async_planned["prefix_cache_policy"]["population_mode"] != "async":
        raise RuntimeError(f"agent-workspace-async mode mismatch: {async_planned}")
    if async_planned["prefix_cache_policy"]["pending_wait_ms"] != 0:
        raise RuntimeError(
            f"agent-workspace-async should not wait by default: {async_planned}"
        )

    summary = client.summary()
    if not summary.loaded:
        raise RuntimeError(f"engine not loaded: {summary}")
    if not summary.gpu_ready:
        raise RuntimeError(f"GPU not ready: {summary}")
    if not summary.can_generate:
        raise RuntimeError(f"generation not available: {summary}")
    if summary.cache_strategy not in {
        "direct_cache_reuse",
        "split_prefill_or_async_build",
    }:
        raise RuntimeError(f"unexpected cache strategy: {summary}")

    payload = {
        "ok": True,
        "profiles": sorted(profiles),
        "summary": asdict(summary),
        "agent_workspace_pending_wait_ms": planned["prefix_cache_policy"][
            "pending_wait_ms"
        ],
        "agent_workspace_async_pending_wait_ms": async_planned[
            "prefix_cache_policy"
        ]["pending_wait_ms"],
    }
    args.output_json.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    print(
        "m26_ui_client",
        payload["ok"],
        "loaded",
        summary.loaded,
        "profile",
        summary.runtime_profile,
        "strategy",
        summary.cache_strategy,
        "profiles",
        ",".join(payload["profiles"]),
        args.output_json,
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
