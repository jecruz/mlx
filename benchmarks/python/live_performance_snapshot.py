#!/usr/bin/env python3
"""Capture a lightweight live performance/readiness snapshot."""

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
    parser.add_argument("--base-url", default="http://127.0.0.1:8773")
    parser.add_argument("--output-json", type=Path, required=True)
    parser.add_argument("--tag", default="m197-live-performance-snapshot")
    parser.add_argument("--fail-on-fail", action="store_true")
    args = parser.parse_args()

    base_url = args.base_url.rstrip("/")
    readiness = request_json(f"{base_url}/engine/operator-readiness")
    metrics = request_json(f"{base_url}/metrics")
    failures = []
    if readiness.get("verdict") != "PASS":
        failures.append(f"readiness verdict is {readiness.get('verdict')!r}")
    if metrics.get("failed_requests", 0) != 0:
        failures.append(f"failed_requests is {metrics.get('failed_requests')}")
    output = {
        "type": "live_performance_snapshot",
        "tag": args.tag,
        "base_url": base_url,
        "verdict": "PASS" if not failures else "FAIL",
        "readiness": "live-performance-snapshot-ready" if not failures else "not-ready",
        "operator_readiness": readiness,
        "metrics": {
            "total_requests": metrics.get("total_requests"),
            "successful_requests": metrics.get("successful_requests"),
            "failed_requests": metrics.get("failed_requests"),
            "mean_run_ms": metrics.get("mean_run_ms"),
            "cache_candidate_requests": metrics.get("cache_candidate_requests"),
        },
        "failures": failures,
    }
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n")
    print(
        "live_performance_snapshot",
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
