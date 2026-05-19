#!/usr/bin/env python3
"""Gate request-scoped cache, scheduling, first-turn, memory, and routing evidence."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text())


def write(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--admission", type=Path, required=True)
    parser.add_argument("--repeated", type=Path, required=True)
    parser.add_argument("--low-memory", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--tag", default="m136-m139-qwen-a3b")
    parser.add_argument("--fail-on-fail", action="store_true")
    args = parser.parse_args()

    admission = load(args.admission)
    repeated = load(args.repeated)
    low_memory = load(args.low_memory)
    rows = admission.get("rows") or []
    row_by_case = {row.get("case"): row for row in rows}

    scheduling_failures = []
    async_rows = [row for row in rows if row.get("cache_population_mode") == "async"]
    request_rows = [row for row in rows if row.get("cache_population_mode") == "request"]
    if not async_rows:
        scheduling_failures.append("no request-metadata case selected async cache population")
    if not request_rows:
        scheduling_failures.append("no request-metadata case selected request-derived cache population")
    scheduling = {
        "type": "async_prefix_build_scheduling_profile",
        "tag": args.tag,
        "verdict": "PASS" if not scheduling_failures else "FAIL",
        "readiness": "async-and-request-modes-observed" if not scheduling_failures else "not-ready",
        "async_cases": [row.get("case") for row in async_rows],
        "request_cases": [row.get("case") for row in request_rows],
        "rows": rows,
        "failures": scheduling_failures,
    }

    first_failures = []
    speedup = repeated.get("best_hit_speedup_vs_baseline")
    baseline_prefill = (repeated.get("baseline") or {}).get("actual_prefill_tokens")
    hit_prefill = (repeated.get("best_hit") or {}).get("actual_prefill_tokens")
    if repeated.get("verdict") != "PASS":
        first_failures.append("repeated-context benchmark did not pass")
    if not isinstance(speedup, (int, float)) or speedup < 2.0:
        first_failures.append(f"best-hit speedup too low: {speedup}")
    if not isinstance(baseline_prefill, int) or baseline_prefill < 512:
        first_failures.append(f"baseline prefill too low: {baseline_prefill}")
    if not isinstance(hit_prefill, int) or hit_prefill > 32:
        first_failures.append(f"best-hit prefill too high: {hit_prefill}")
    first_turn = {
        "type": "first_reusable_turn_latency_gate",
        "tag": args.tag,
        "verdict": "PASS" if not first_failures else "FAIL",
        "baseline_service_request_ms": repeated.get("baseline_service_request_ms"),
        "best_hit_service_request_ms": repeated.get("best_hit_service_request_ms"),
        "best_hit_speedup_vs_baseline": speedup,
        "baseline_actual_prefill_tokens": baseline_prefill,
        "best_hit_actual_prefill_tokens": hit_prefill,
        "failures": first_failures,
    }

    memory_failures = []
    low_speedup = low_memory.get("best_hit_speedup_vs_baseline")
    low_hit_prefill = (low_memory.get("best_hit") or {}).get("actual_prefill_tokens")
    low_row = row_by_case.get("low_memory") or {}
    if low_memory.get("verdict") != "PASS":
        memory_failures.append("low-memory repeated-context benchmark did not pass")
    if not isinstance(low_speedup, (int, float)) or low_speedup < 2.0:
        memory_failures.append(f"low-memory speedup too low: {low_speedup}")
    if not isinstance(low_hit_prefill, int) or low_hit_prefill > 32:
        memory_failures.append(f"low-memory hit prefill too high: {low_hit_prefill}")
    if low_row.get("request_runtime_profile") != "agent-workspace-low-memory":
        memory_failures.append(f"metadata low-memory row selected {low_row.get('request_runtime_profile')}")
    memory = {
        "type": "memory_bounded_cache_policy_gate",
        "tag": args.tag,
        "verdict": "PASS" if not memory_failures else "FAIL",
        "low_memory_speedup_vs_baseline": low_speedup,
        "low_memory_best_hit_prefill": low_hit_prefill,
        "metadata_low_memory_row": low_row,
        "failures": memory_failures,
    }

    routing_failures = []
    for case in ("coding_agent", "first_hit", "low_memory", "interactive", "diagnostics"):
        row = row_by_case.get(case)
        if not row:
            routing_failures.append(f"missing routing row: {case}")
            continue
        if row.get("request_runtime_profile_source") != "request_metadata":
            routing_failures.append(f"{case}: source={row.get('request_runtime_profile_source')}")
    scoped_rows = [row for row in rows if row.get("request_runtime_profile_scoped") is True]
    routing = {
        "type": "request_scoped_routing_isolation_gate",
        "tag": args.tag,
        "verdict": "PASS" if not routing_failures else "FAIL",
        "scoped_rows": len(scoped_rows),
        "rows": rows,
        "failures": routing_failures,
    }

    artifacts = {
        "m136_async_prefix_build_scheduling": scheduling,
        "m137_first_reusable_turn_latency": first_turn,
        "m138_memory_bounded_cache_policy": memory,
        "m139_request_scoped_routing_isolation": routing,
    }
    paths: dict[str, str] = {}
    for name, payload in artifacts.items():
        path = args.output_dir / f"{name}-{args.tag}.json"
        write(path, payload)
        paths[name] = str(path)

    failures = [
        f"{name}: {payload['failures']}"
        for name, payload in artifacts.items()
        if payload.get("verdict") != "PASS"
    ]
    manifest = {
        "type": "request_scoped_performance_gates",
        "tag": args.tag,
        "verdict": "PASS" if not failures else "FAIL",
        "artifacts": paths,
        "failures": failures,
    }
    write(args.output_dir / f"request-scoped-performance-gates-{args.tag}.json", manifest)
    print("request_scoped_performance_gates", manifest["verdict"], "artifacts", len(paths), "failures", len(failures), args.output_dir)
    if args.fail_on_fail and manifest["verdict"] != "PASS":
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
