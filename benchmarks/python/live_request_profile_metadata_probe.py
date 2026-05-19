#!/usr/bin/env python3
"""Probe live request-level profile selection on the resident MLX server."""

from __future__ import annotations

import argparse
import json
import time
import urllib.request
from pathlib import Path
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


def configure_profile(base_url: str, profile: str) -> None:
    request_json("POST", f"{base_url}/engine/config", {"runtime_profile": profile})


def prompt(name: str) -> str:
    return (
        f"M123 request profile metadata probe {name}. "
        "Answer with one short sentence and do not include code."
    )


def row_for_case(
    *,
    base_url: str,
    name: str,
    route: str,
    payload: dict[str, Any],
    expected_profile: str,
) -> dict[str, Any]:
    started = time.perf_counter()
    response = request_json("POST", f"{base_url}{route}", payload)
    wall_ms = 1e3 * (time.perf_counter() - started)
    metrics = response.get("engine_metrics") or {}
    return {
        "type": "live_request_profile_metadata_probe_row",
        "name": name,
        "route": route,
        "payload_hints": {
            key: payload.get(key)
            for key in (
                "runtime_profile",
                "workload_intent",
                "memory_class_gb",
                "immediate_second_turn",
                "low_memory",
                "diagnostics_workload",
                "interactive_workload",
                "agentic_workload",
                "repeated_workspace",
            )
            if key in payload
        },
        "expected_profile": expected_profile,
        "observed_profile": metrics.get("request_runtime_profile"),
        "profile_source": metrics.get("request_runtime_profile_source"),
        "profile_reason": metrics.get("request_runtime_profile_reason"),
        "profile_applied": metrics.get("request_runtime_profile_applied"),
        "finish_reason": response["choices"][0].get("finish_reason"),
        "wall_ms": wall_ms,
        "service_request_ms": metrics.get("service_request_ms"),
        "actual_prefill_tokens": metrics.get("actual_prefill_tokens"),
        "engine_metrics": metrics,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8773")
    parser.add_argument("--output-json", type=Path, required=True)
    parser.add_argument("--tag", default="m123-qwen-a3b")
    parser.add_argument("--max-tokens", type=int, default=1)
    parser.add_argument("--fail-on-fail", action="store_true")
    args = parser.parse_args()

    base_url = args.base_url.rstrip("/")
    cases = [
        {
            "name": "completion_first_hit_intent",
            "route": "/v1/completions",
            "expected_profile": "agent-workspace-first-hit",
            "payload": {
                "model": "m123-live-request-profile",
                "prompt": prompt("completion_first_hit_intent"),
                "max_tokens": args.max_tokens,
                "workload_intent": "first-hit",
                "immediate_second_turn": True,
            },
        },
        {
            "name": "chat_coding_agent_low_memory",
            "route": "/v1/chat/completions",
            "expected_profile": "agent-workspace-low-memory",
            "payload": {
                "model": "m123-live-request-profile",
                "messages": [
                    {
                        "role": "user",
                        "content": prompt("chat_coding_agent_low_memory"),
                    }
                ],
                "max_tokens": args.max_tokens,
                "workload_intent": "coding-agent",
                "memory_class_gb": 32,
                "repeated_workspace": True,
            },
        },
        {
            "name": "completion_manual_override",
            "route": "/v1/completions",
            "expected_profile": "interactive",
            "payload": {
                "model": "m123-live-request-profile",
                "prompt": prompt("completion_manual_override"),
                "max_tokens": args.max_tokens,
                "runtime_profile": "interactive",
                "workload_intent": "low-memory",
                "low_memory": True,
            },
        },
    ]

    before = request_json("GET", f"{base_url}/health")
    rows = []
    failures = []
    try:
        for case in cases:
            row = row_for_case(
                base_url=base_url,
                name=case["name"],
                route=case["route"],
                payload=case["payload"],
                expected_profile=case["expected_profile"],
            )
            rows.append(row)
            if row["observed_profile"] != row["expected_profile"]:
                failures.append(
                    f"{row['name']}: observed={row['observed_profile']!r} "
                    f"expected={row['expected_profile']!r}"
                )
            if row["profile_source"] != "request_metadata":
                failures.append(
                    f"{row['name']}: profile_source={row['profile_source']!r}"
                )
            if row["profile_applied"] is not True:
                failures.append(
                    f"{row['name']}: profile_applied={row['profile_applied']!r}"
                )
            print(
                "live_request_profile_metadata",
                row["name"],
                row["observed_profile"],
                row["profile_source"],
                "service_ms",
                round(float(row["service_request_ms"] or 0.0), 2),
                flush=True,
            )
    finally:
        configure_profile(base_url, "interactive")
    after = request_json("GET", f"{base_url}/health")

    output = {
        "type": "live_request_profile_metadata_probe",
        "tag": args.tag,
        "base_url": base_url,
        "verdict": "PASS" if not failures else "FAIL",
        "before": {
            "loaded": before.get("loaded"),
            "model": before.get("model"),
            "runtime_profile": before.get("runtime_profile"),
            "device": before.get("device"),
        },
        "after": {
            "loaded": after.get("loaded"),
            "model": after.get("model"),
            "runtime_profile": after.get("runtime_profile"),
            "device": after.get("device"),
        },
        "row_count": len(rows),
        "rows": rows,
        "failures": failures,
    }
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n")
    print(
        "live_request_profile_metadata_result",
        output["verdict"],
        "rows",
        len(rows),
        "failures",
        len(failures),
        args.output_json,
        flush=True,
    )
    for failure in failures:
        print("failure", failure, flush=True)
    return 1 if args.fail_on_fail and failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
