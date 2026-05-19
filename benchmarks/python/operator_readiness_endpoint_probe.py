#!/usr/bin/env python3
"""Validate the live /engine/operator-readiness endpoint contract."""

from __future__ import annotations

import argparse
import json
import urllib.request
from pathlib import Path
from typing import Any


REQUIRED_TOP_LEVEL = [
    "type",
    "verdict",
    "readiness",
    "status_card",
    "runtime",
    "memory",
    "warnings",
    "failures",
]
REQUIRED_STATUS_CARD = ["runtime", "gpu", "warm", "can_generate", "live_controls"]
REQUIRED_RUNTIME = [
    "model",
    "backend",
    "engine_preset",
    "runtime_profile",
    "strategy",
    "gpu_ready",
    "warm",
    "can_generate",
    "can_reload",
    "can_unload",
]
REQUIRED_MEMORY = [
    "source",
    "active_memory_bytes",
    "cache_memory_bytes",
    "peak_memory_bytes",
]


def request_json(url: str, *, timeout: int = 120) -> dict[str, Any]:
    with urllib.request.urlopen(url, timeout=timeout) as resp:
        return json.loads(resp.read().decode())


def missing_keys(name: str, obj: dict[str, Any], keys: list[str]) -> list[str]:
    return [f"{name} missing {key}" for key in keys if key not in obj]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8773")
    parser.add_argument("--output-json", type=Path, required=True)
    parser.add_argument("--tag", default="m187-operator-readiness-endpoint")
    parser.add_argument("--fail-on-fail", action="store_true")
    args = parser.parse_args()

    base_url = args.base_url.rstrip("/")
    payload = request_json(f"{base_url}/engine/operator-readiness")
    failures = []
    failures.extend(missing_keys("endpoint", payload, REQUIRED_TOP_LEVEL))
    if payload.get("type") != "operator_readiness_live_status":
        failures.append(f"unexpected type {payload.get('type')!r}")
    if payload.get("verdict") != "PASS":
        failures.append(f"verdict is {payload.get('verdict')!r}")
    if payload.get("readiness") != "operator-live-ready":
        failures.append(f"readiness is {payload.get('readiness')!r}")

    status_card = payload.get("status_card") or {}
    runtime = payload.get("runtime") or {}
    memory = payload.get("memory") or {}
    failures.extend(missing_keys("status_card", status_card, REQUIRED_STATUS_CARD))
    failures.extend(missing_keys("runtime", runtime, REQUIRED_RUNTIME))
    failures.extend(missing_keys("memory", memory, REQUIRED_MEMORY))
    if runtime.get("gpu_ready") is not True:
        failures.append("runtime.gpu_ready is not true")
    if runtime.get("can_generate") is not True:
        failures.append("runtime.can_generate is not true")
    if memory.get("source") != "engine_ui":
        failures.append(f"memory.source is {memory.get('source')!r}")
    for key in ("active_memory_bytes", "peak_memory_bytes"):
        value = memory.get(key)
        if not isinstance(value, int | float) or value <= 0:
            failures.append(f"memory.{key} must be positive")
    if not isinstance(payload.get("warnings"), list):
        failures.append("warnings must be a list")
    if not isinstance(payload.get("failures"), list):
        failures.append("failures must be a list")

    output = {
        "type": "operator_readiness_endpoint_probe",
        "tag": args.tag,
        "base_url": base_url,
        "verdict": "PASS" if not failures else "FAIL",
        "readiness": "operator-readiness-endpoint-ready" if not failures else "not-ready",
        "endpoint": "/engine/operator-readiness",
        "payload": payload,
        "failures": failures,
    }
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n")
    print(
        "operator_readiness_endpoint_probe",
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
