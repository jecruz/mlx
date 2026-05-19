#!/usr/bin/env python3
"""Live probe for per-request MLX memory metrics."""

from __future__ import annotations

import argparse
import json
import urllib.request
from pathlib import Path
from typing import Any


REQUIRED_FIELDS = [
    "active_memory_gb",
    "active_memory_bytes",
    "cache_memory_gb",
    "cache_memory_bytes",
    "mlx_peak_memory_gb",
    "peak_memory_bytes",
]


def request_json(method: str, url: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    data = json.dumps(payload).encode() if payload is not None else None
    headers = {"Content-Type": "application/json"} if payload is not None else {}
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=180) as resp:
        return json.loads(resp.read().decode())


def stream_metrics(url: str, payload: dict[str, Any]) -> dict[str, Any]:
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    metrics: dict[str, Any] = {}
    with urllib.request.urlopen(req, timeout=180) as resp:
        for raw in resp:
            line = raw.decode().strip()
            if not line.startswith("data:"):
                continue
            data = line[len("data:") :].strip()
            if not data or data == "[DONE]":
                continue
            event = json.loads(data)
            if event.get("engine_metrics"):
                metrics = event["engine_metrics"]
    return metrics


def validate_metrics(name: str, metrics: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    failures = []
    fields = {}
    for field in REQUIRED_FIELDS:
        value = metrics.get(field)
        fields[field] = value
        if not isinstance(value, int | float):
            failures.append(f"{name}: missing numeric {field}")
    if isinstance(metrics.get("active_memory_gb"), int | float) and metrics["active_memory_gb"] <= 0:
        failures.append(f"{name}: active_memory_gb must be positive")
    return fields, failures


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8773")
    parser.add_argument("--output-json", type=Path, required=True)
    parser.add_argument("--tag", default="m178-request-memory-live")
    parser.add_argument("--fail-on-fail", action="store_true")
    args = parser.parse_args()

    base_url = args.base_url.rstrip("/")
    payload = {
        "model": "local-mlx",
        "prompt": "Output only: MEMORY_METRICS_OK\n/no_think",
        "max_tokens": 8,
        "stop": ["<|endoftext|>", "<|im_start|>", "<|im_end|>"],
        "runtime_profile": "interactive",
    }
    completion = request_json("POST", f"{base_url}/v1/completions", payload)
    nonstream_metrics = completion["engine_metrics"]
    stream_payload = dict(payload)
    stream_payload["stream"] = True
    stream_final_metrics = stream_metrics(f"{base_url}/v1/completions", stream_payload)

    nonstream_fields, nonstream_failures = validate_metrics("nonstream", nonstream_metrics)
    stream_fields, stream_failures = validate_metrics("stream", stream_final_metrics)
    failures = nonstream_failures + stream_failures
    output = {
        "type": "request_memory_metrics_live_probe",
        "tag": args.tag,
        "base_url": base_url,
        "verdict": "PASS" if not failures else "FAIL",
        "readiness": "request-memory-metrics-live" if not failures else "not-ready",
        "required_fields": REQUIRED_FIELDS,
        "nonstream": {
            "request_id": nonstream_metrics.get("request_id"),
            "fields": nonstream_fields,
        },
        "stream": {
            "request_id": stream_final_metrics.get("request_id"),
            "fields": stream_fields,
        },
        "failures": failures,
    }
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n")
    print(
        "request_memory_metrics_live_probe",
        output["verdict"],
        output["readiness"],
        "failures",
        len(failures),
        args.output_json,
    )
    for failure in failures:
        print("failure", failure)
    return 1 if args.fail_on_fail and failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
