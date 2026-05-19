#!/usr/bin/env python3
"""Probe streaming and non-stream request metadata parity across routes."""

from __future__ import annotations

import argparse
import json
import urllib.request
from pathlib import Path
from typing import Any


def request_json(method: str, url: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    data = json.dumps(payload).encode() if payload is not None else None
    headers = {"Content-Type": "application/json"} if payload is not None else {}
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=240) as resp:
        return json.loads(resp.read().decode())


def stream_sse(url: str, payload: dict[str, Any]) -> dict[str, Any]:
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=240) as resp:
        for raw in resp:
            line = raw.decode().strip()
            if not line.startswith("data:"):
                continue
            data = line[len("data:") :].strip()
            if not data or data == "[DONE]":
                continue
            event = json.loads(data)
            if event.get("engine_metrics"):
                return event["engine_metrics"]
    raise RuntimeError("stream did not include engine_metrics")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8773")
    parser.add_argument("--output-json", type=Path, required=True)
    parser.add_argument("--tag", default="m153-qwen-a3b")
    parser.add_argument("--max-tokens", type=int, default=3)
    parser.add_argument("--fail-on-fail", action="store_true")
    args = parser.parse_args()
    base_url = args.base_url.rstrip("/")
    common = {
        "workload_intent": "first-hit",
        "immediate_second_turn": True,
        "agentic_workload": True,
        "repeated_workspace": True,
    }
    cases = [
        (
            "completion_nonstream",
            lambda: request_json(
                "POST",
                f"{base_url}/v1/completions",
                {
                    "model": "local-mlx",
                    "prompt": f"{args.tag} completion nonstream parity.",
                    "max_tokens": args.max_tokens,
                    "stream": False,
                    **common,
                },
            )["engine_metrics"],
        ),
        (
            "completion_stream",
            lambda: stream_sse(
                f"{base_url}/v1/completions",
                {
                    "model": "local-mlx",
                    "prompt": f"{args.tag} completion stream parity.",
                    "max_tokens": args.max_tokens,
                    "stream": True,
                    **common,
                },
            ),
        ),
        (
            "chat_nonstream",
            lambda: request_json(
                "POST",
                f"{base_url}/v1/chat/completions",
                {
                    "model": "local-mlx",
                    "messages": [{"role": "user", "content": f"{args.tag} chat nonstream parity."}],
                    "max_tokens": args.max_tokens,
                    "stream": False,
                    **common,
                },
            )["engine_metrics"],
        ),
        (
            "chat_stream",
            lambda: stream_sse(
                f"{base_url}/v1/chat/completions",
                {
                    "model": "local-mlx",
                    "messages": [{"role": "user", "content": f"{args.tag} chat stream parity."}],
                    "max_tokens": args.max_tokens,
                    "stream": True,
                    **common,
                },
            ),
        ),
        (
            "generate_json",
            lambda: request_json(
                "POST",
                f"{base_url}/generate",
                {
                    "prompt": f"{args.tag} generate json parity.",
                    "max_tokens": args.max_tokens,
                    "stream": False,
                    **common,
                },
            ),
        ),
    ]
    rows = []
    failures = []
    for name, run in cases:
        metrics = run()
        row = {
            "case": name,
            "request_runtime_profile": metrics.get("request_runtime_profile"),
            "request_runtime_profile_source": metrics.get("request_runtime_profile_source"),
            "request_runtime_profile_applied": metrics.get("request_runtime_profile_applied"),
            "request_runtime_profile_scoped": metrics.get("request_runtime_profile_scoped"),
            "actual_prefill_tokens": metrics.get("actual_prefill_tokens"),
            "service_request_ms": metrics.get("service_request_ms"),
        }
        rows.append(row)
        if row["request_runtime_profile"] != "agent-workspace-first-hit":
            failures.append(f"{name}: profile {row['request_runtime_profile']!r}")
        if row["request_runtime_profile_source"] != "request_metadata":
            failures.append(f"{name}: source {row['request_runtime_profile_source']!r}")
        if row["request_runtime_profile_applied"] is not True:
            failures.append(f"{name}: applied {row['request_runtime_profile_applied']!r}")
        if row["request_runtime_profile_scoped"] is not True:
            failures.append(f"{name}: scoped {row['request_runtime_profile_scoped']!r}")
    output = {
        "type": "route_parity_probe",
        "tag": args.tag,
        "base_url": base_url,
        "verdict": "PASS" if not failures else "FAIL",
        "readiness": "stream-and-nonstream-route-parity" if not failures else "not-ready",
        "rows": rows,
        "failures": failures,
    }
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n")
    print("route_parity_probe", output["verdict"], "rows", len(rows), "failures", len(failures), args.output_json)
    if args.fail_on_fail and output["verdict"] != "PASS":
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
