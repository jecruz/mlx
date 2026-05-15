#!/usr/bin/env python3
"""Report low-level prompt-cache continuation readiness from /health."""

from __future__ import annotations

import argparse
import json
import urllib.request
from pathlib import Path
from typing import Any


def request_json(url: str, *, timeout: int = 120) -> dict[str, Any]:
    with urllib.request.urlopen(url, timeout=timeout) as resp:
        return json.loads(resp.read().decode())


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8765")
    parser.add_argument(
        "--output-json",
        type=Path,
        default=Path("cache-continuation-capabilities-m22.json"),
    )
    args = parser.parse_args()

    health = request_json(f"{args.base_url.rstrip('/')}/health")
    continuation = health["prompt_cache_continuation"]
    capabilities = health["prompt_cache_capabilities"]
    payload = {
        "model": health["model"],
        "mlx_lm_version": continuation.get("mlx_lm_version"),
        "entry_count": continuation["entry_count"],
        "native_replay_free_prefix_store_supported": continuation[
            "native_replay_free_prefix_store_supported"
        ],
        "replay_free_supported_entries": continuation[
            "replay_free_supported_entries"
        ],
        "blocked_entries": continuation["blocked_entries"],
        "blocked_classes": continuation["blocked_classes"],
        "blocker_reasons": continuation["blocker_reasons"],
        "safe_request_prefix_store_strategy": continuation[
            "safe_request_prefix_store_strategy"
        ],
        "required_lower_level_work": continuation["required_lower_level_work"],
        "capability_classes": capabilities["classes"],
        "non_trimmable_entries": capabilities["non_trimmable_entries"],
    }
    args.output_json.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")

    if payload["entry_count"] <= 0:
        raise RuntimeError(f"no prompt-cache entries reported: {payload}")
    if payload["blocked_entries"] != payload["non_trimmable_entries"]:
        raise RuntimeError(
            "continuation blocker count diverged from non-trimmable count: "
            f"{payload}"
        )
    if "ArraysCache" in payload["blocked_classes"]:
        expected = "model_specific_recurrent_state_continuation_for_arrays_cache"
        if payload["required_lower_level_work"] != expected:
            raise RuntimeError(f"missing ArraysCache lower-level work marker: {payload}")
        if (
            "arrays_cache_has_recurrent_state_without_offset_or_trim"
            not in payload["blocker_reasons"]
        ):
            raise RuntimeError(f"missing ArraysCache blocker reason: {payload}")

    print(
        "m22_continuation",
        "mlx_lm",
        payload["mlx_lm_version"],
        "entries",
        payload["entry_count"],
        "native_replay_free",
        payload["native_replay_free_prefix_store_supported"],
        "supported",
        payload["replay_free_supported_entries"],
        "blocked",
        payload["blocked_entries"],
        "blocked_classes",
        ",".join(payload["blocked_classes"]),
        "strategy",
        payload["safe_request_prefix_store_strategy"],
        args.output_json,
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
