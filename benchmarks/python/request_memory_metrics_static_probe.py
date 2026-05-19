#!/usr/bin/env python3
"""Static contract probe for per-request MLX memory metrics."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


REQUIRED_FIELDS = [
    "active_memory_gb",
    "active_memory_bytes",
    "cache_memory_gb",
    "cache_memory_bytes",
    "mlx_peak_memory_gb",
    "peak_memory_bytes",
]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, default=Path("mlx_engine/resident_service.py"))
    parser.add_argument("--output-json", type=Path, required=True)
    parser.add_argument("--tag", default="m177-request-memory-metrics")
    parser.add_argument("--fail-on-fail", action="store_true")
    args = parser.parse_args()

    source = args.source.read_text()
    helper_present = "def mlx_request_memory_metrics" in source
    helper_fields = {field: field in source for field in REQUIRED_FIELDS}
    metric_injections = source.count("**self.mlx_request_memory_metrics()")
    failures = []
    if not helper_present:
        failures.append("missing mlx_request_memory_metrics helper")
    for field, present in helper_fields.items():
        if not present:
            failures.append(f"missing memory metric field: {field}")
    if metric_injections < 3:
        failures.append(
            f"expected at least 3 request metric injections, observed {metric_injections}"
        )

    output = {
        "type": "request_memory_metrics_static_probe",
        "tag": args.tag,
        "verdict": "PASS" if not failures else "FAIL",
        "readiness": "request-memory-metrics-ready" if not failures else "not-ready",
        "source": str(args.source),
        "helper_present": helper_present,
        "required_fields": helper_fields,
        "metric_injections": metric_injections,
        "failures": failures,
    }
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n")
    print(
        "request_memory_metrics_static_probe",
        output["verdict"],
        output["readiness"],
        "injections",
        metric_injections,
        "failures",
        len(failures),
        args.output_json,
    )
    for failure in failures:
        print("failure", failure)
    return 1 if args.fail_on_fail and failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
