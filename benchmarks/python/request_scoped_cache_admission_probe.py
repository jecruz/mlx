#!/usr/bin/env python3
"""Probe cache-admission signals for request-metadata-routed product calls."""

from __future__ import annotations

import argparse
import json
import time
import urllib.request
from pathlib import Path
from typing import Any


CASES: list[tuple[str, dict[str, Any]]] = [
    ("coding_agent", {"workload_intent": "coding-agent", "agentic_workload": True, "repeated_workspace": True}),
    ("first_hit", {"workload_intent": "first-hit", "immediate_second_turn": True, "agentic_workload": True, "repeated_workspace": True}),
    ("low_memory", {"workload_intent": "low-memory", "low_memory": True, "agentic_workload": True, "repeated_workspace": True}),
    ("interactive", {"workload_intent": "interactive", "interactive_workload": True}),
    ("diagnostics", {"workload_intent": "diagnostics", "diagnostics_workload": True}),
]


def request_json(method: str, url: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    data = json.dumps(payload).encode() if payload is not None else None
    headers = {"Content-Type": "application/json"} if payload is not None else {}
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=240) as resp:
        return json.loads(resp.read().decode())


def prompt_for(tag: str, case: str) -> str:
    shared = (
        f"{tag} request-scoped cache admission case {case}. "
        "Repository context includes MLX request metadata routing, Dax product modes, "
        "prefix cache admission, async prefix builds, low-memory bounds, and operator gates. "
    )
    return (shared * 20) + "\nReply with two words."


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8773")
    parser.add_argument("--output-json", type=Path, required=True)
    parser.add_argument("--tag", default="m135-qwen-a3b")
    parser.add_argument("--max-tokens", type=int, default=1)
    parser.add_argument("--fail-on-fail", action="store_true")
    args = parser.parse_args()
    base_url = args.base_url.rstrip("/")

    rows = []
    failures = []
    try:
        request_json("POST", f"{base_url}/engine/cache/prune", {"target_entries": 0, "clear_mlx_cache": False})
    except Exception as exc:  # pragma: no cover - live diagnostic
        failures.append(f"cache prune failed: {exc}")

    for case, metadata in CASES:
        payload = {
            "model": "local-mlx",
            "prompt": prompt_for(args.tag, case),
            "max_tokens": args.max_tokens,
            "stream": False,
            **metadata,
        }
        started = time.perf_counter()
        response = request_json("POST", f"{base_url}/v1/completions", payload)
        wall_ms = 1e3 * (time.perf_counter() - started)
        metrics = response["engine_metrics"]
        row = {
            "case": case,
            "wall_ms": wall_ms,
            "request_runtime_profile": metrics.get("request_runtime_profile"),
            "request_runtime_profile_source": metrics.get("request_runtime_profile_source"),
            "request_runtime_profile_applied": metrics.get("request_runtime_profile_applied"),
            "request_runtime_profile_scoped": metrics.get("request_runtime_profile_scoped"),
            "cache_population_mode": metrics.get("cache_population_mode"),
            "cache_candidate": metrics.get("cache_candidate"),
            "cache_scheduled": metrics.get("cache_scheduled"),
            "cache_pending": metrics.get("cache_pending"),
            "cache_created": metrics.get("cache_created"),
            "cache_reuse_enabled": metrics.get("cache_reuse_enabled"),
            "cache_hit": metrics.get("cache_hit"),
            "generated_prefix_cache_recorded": metrics.get("generated_prefix_cache_recorded"),
            "actual_prefill_tokens": metrics.get("actual_prefill_tokens"),
            "service_request_ms": metrics.get("service_request_ms"),
            "peak_memory_gb": metrics.get("peak_memory_gb"),
        }
        rows.append(row)

    for row in rows:
        if row["request_runtime_profile_source"] != "request_metadata":
            failures.append(f"{row['case']}: request metadata was not applied")
        if row["actual_prefill_tokens"] is None or row["actual_prefill_tokens"] < 128:
            failures.append(f"{row['case']}: prompt too small for admission signal")

    output = {
        "type": "request_scoped_cache_admission_probe",
        "tag": args.tag,
        "base_url": base_url,
        "verdict": "PASS" if not failures else "FAIL",
        "readiness": "cache-admission-measured" if not failures else "not-ready",
        "row_count": len(rows),
        "rows": rows,
        "failures": failures,
    }
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n")
    print("request_scoped_cache_admission_probe", output["verdict"], "rows", len(rows), "failures", len(failures), args.output_json)
    if args.fail_on_fail and output["verdict"] != "PASS":
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
