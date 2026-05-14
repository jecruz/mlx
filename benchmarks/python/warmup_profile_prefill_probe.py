#!/usr/bin/env python3
"""Validate profile-band prefill warmup targets and results."""

from __future__ import annotations

import argparse
import json
import time
import urllib.request
from typing import Any


def request_json(
    method: str,
    url: str,
    payload: dict[str, Any] | None = None,
    *,
    timeout: int = 1200,
) -> dict[str, Any]:
    data = None
    headers = {}
    if payload is not None:
        data = json.dumps(payload).encode()
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode())


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8765")
    parser.add_argument("--warmup-prompt-tokens", default="64,512")
    parser.add_argument("--wait-timeout-s", type=float, default=180.0)
    args = parser.parse_args()

    base_url = args.base_url.rstrip("/")
    reloaded = request_json(
        "POST",
        f"{base_url}/engine/reload",
        {
            "warmup_prompt_tokens": args.warmup_prompt_tokens,
            "warmup_profile_prefill": True,
            "warmup_mode": "async",
        },
    )
    print(
        "warmup_reload",
        reloaded.get("loaded"),
        reloaded.get("warmup", {}).get("profile_prefill"),
        reloaded.get("warmup", {}).get("result_count"),
    )

    deadline = time.time() + args.wait_timeout_s
    health = request_json("GET", f"{base_url}/health")
    while time.time() < deadline:
        warmup = health.get("warmup") or {}
        if warmup.get("completed") or warmup.get("error"):
            break
        time.sleep(0.5)
        health = request_json("GET", f"{base_url}/health")

    warmup = health.get("warmup") or {}
    if warmup.get("error"):
        raise RuntimeError(f"warmup failed: {warmup['error']}")
    if not warmup.get("completed"):
        raise RuntimeError(f"warmup did not complete: {warmup}")
    if not warmup.get("profile_prefill"):
        raise RuntimeError(f"profile prefill warmup was not enabled: {warmup}")

    targets = warmup.get("targets") or []
    results = health.get("warmup_results") or []
    target_sources = {target.get("source") for target in targets}
    result_sources = {row.get("warmup_source") for row in results}
    if "configured" not in target_sources or "profile_band" not in target_sources:
        raise RuntimeError(f"warmup targets did not include both sources: {targets}")
    if "configured" not in result_sources or "profile_band" not in result_sources:
        raise RuntimeError(f"warmup results did not include both sources: {results}")

    profile_band_results = [
        row for row in results if row.get("warmup_source") == "profile_band"
    ]
    if not profile_band_results:
        raise RuntimeError("no profile-band warmup result was recorded")
    if not any(row.get("prefill_selection_source") == "prompt_token_band" for row in results):
        raise RuntimeError(f"warmup did not use prompt-token band selection: {results}")

    print(
        "warmup_profile_prefill",
        "ok",
        "targets",
        len(targets),
        "results",
        len(results),
        "profile_band_results",
        len(profile_band_results),
        "max_prompt_tokens",
        max(int(row.get("warmup_prompt_tokens") or 0) for row in results),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
