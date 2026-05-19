#!/usr/bin/env python3
"""Validate scoped request metadata on live streaming endpoints."""

from __future__ import annotations

import argparse
import json
import urllib.request
from pathlib import Path
from typing import Any


def stream_sse(url: str, payload: dict[str, Any]) -> list[dict[str, Any]]:
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    events: list[dict[str, Any]] = []
    with urllib.request.urlopen(req, timeout=240) as resp:
        for raw in resp:
            line = raw.decode().strip()
            if not line.startswith("data:"):
                continue
            data = line[len("data:") :].strip()
            if not data or data == "[DONE]":
                continue
            events.append(json.loads(data))
    return events


def final_metrics(events: list[dict[str, Any]]) -> dict[str, Any]:
    for event in reversed(events):
        metrics = event.get("engine_metrics")
        if metrics:
            return metrics
    raise RuntimeError("stream did not include final engine_metrics")


def check(metrics: dict[str, Any], name: str, expected: Any) -> dict[str, Any]:
    actual = metrics.get(name)
    return {"name": name, "actual": actual, "expected": expected, "pass": actual == expected}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8773")
    parser.add_argument("--output-json", type=Path, required=True)
    parser.add_argument("--tag", default="m144-qwen-a3b")
    parser.add_argument("--max-tokens", type=int, default=4)
    parser.add_argument("--fail-on-fail", action="store_true")
    args = parser.parse_args()
    base_url = args.base_url.rstrip("/")

    cases = [
        (
            "completion_first_hit",
            f"{base_url}/v1/completions",
            {
                "model": "local-mlx",
                "prompt": f"{args.tag} streaming completion scoped metadata.",
                "max_tokens": args.max_tokens,
                "stream": True,
                "workload_intent": "first-hit",
                "immediate_second_turn": True,
                "agentic_workload": True,
                "repeated_workspace": True,
            },
            "agent-workspace-first-hit",
        ),
        (
            "chat_low_memory",
            f"{base_url}/v1/chat/completions",
            {
                "model": "local-mlx",
                "messages": [{"role": "user", "content": f"{args.tag} streaming chat scoped metadata."}],
                "max_tokens": args.max_tokens,
                "stream": True,
                "workload_intent": "low-memory",
                "low_memory": True,
                "agentic_workload": True,
                "repeated_workspace": True,
            },
            "agent-workspace-low-memory",
        ),
    ]
    rows = []
    failures = []
    for name, url, payload, expected_profile in cases:
        events = stream_sse(url, payload)
        metrics = final_metrics(events)
        checks = [
            check(metrics, "request_runtime_profile_source", "request_metadata"),
            check(metrics, "request_runtime_profile_applied", True),
            check(metrics, "request_runtime_profile_scoped", True),
            check(metrics, "request_runtime_profile", expected_profile),
        ]
        case_failures = [f"{item['name']}: {item['actual']!r} != {item['expected']!r}" for item in checks if not item["pass"]]
        failures.extend(f"{name}: {failure}" for failure in case_failures)
        rows.append(
            {
                "case": name,
                "event_count": len(events),
                "checks": checks,
                "request_runtime_profile": metrics.get("request_runtime_profile"),
                "service_request_ms": metrics.get("service_request_ms"),
                "actual_prefill_tokens": metrics.get("actual_prefill_tokens"),
            }
        )

    output = {
        "type": "streaming_request_metadata_scope_probe",
        "tag": args.tag,
        "base_url": base_url,
        "verdict": "PASS" if not failures else "FAIL",
        "readiness": "streaming-request-scope-parity" if not failures else "not-ready",
        "row_count": len(rows),
        "rows": rows,
        "failures": failures,
    }
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n")
    print("streaming_request_metadata_scope_probe", output["verdict"], "rows", len(rows), "failures", len(failures), args.output_json)
    if args.fail_on_fail and output["verdict"] != "PASS":
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
