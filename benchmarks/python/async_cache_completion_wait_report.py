#!/usr/bin/env python3
"""Build an async cache completion wait recommendation from maturation sweep evidence."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text())


def build_report(
    *,
    sweep_json: Path,
    gate_json: Path,
    performance_report: Path,
    output_live_command: str,
    tag: str,
    max_wait_ms: float,
    max_actual_prefill_tokens: int,
) -> dict[str, Any]:
    sweep = load(sweep_json)
    gate = load(gate_json)
    performance = load(performance_report)
    first_hit = sweep.get("first_hit_best") or {}
    best_mature = sweep.get("best") or {}
    failures: list[str] = []

    if sweep.get("verdict") != "PASS":
        failures.append(f"sweep verdict is {sweep.get('verdict')!r}")
    if gate.get("verdict") != "PASS":
        failures.append(f"gate verdict is {gate.get('verdict')!r}")
    if first_hit.get("cache_pending_wait_result") != "hit":
        failures.append("first-hit candidate did not wait to a cache hit")
    if not first_hit.get("cache_hit"):
        failures.append("first-hit candidate did not reuse completed cache")
    if int(first_hit.get("wait_hit_actual_prefill_tokens") or 1_000_000) > max_actual_prefill_tokens:
        failures.append("first-hit candidate prefills too many tokens")
    if float(first_hit.get("cache_pending_wait_ms") or 1_000_000.0) > max_wait_ms:
        failures.append("first-hit candidate waited longer than the allowed budget")
    policy_deltas = first_hit.get("policy_deltas") or {}
    if int(policy_deltas.get("pending_wait_hits") or 0) < 1:
        failures.append("first-hit candidate did not record a pending wait hit")
    if int(policy_deltas.get("async_builds_completed") or 0) < 1:
        failures.append("first-hit candidate did not complete an async build")

    recommended = {
        "prefix_cache_async_idle_grace_ms": first_hit.get("async_idle_grace_ms"),
        "prefix_cache_pending_wait_ms": first_hit.get("pending_wait_ms"),
        "cache_pending_wait_observed_ms": first_hit.get("cache_pending_wait_ms"),
        "wait_hit_actual_prefill_tokens": first_hit.get("wait_hit_actual_prefill_tokens"),
        "wait_hit_service_request_ms": first_hit.get("wait_hit_service_request_ms"),
        "wait_hit_speedup_vs_baseline": first_hit.get("cache_hit_speedup_vs_baseline"),
        "mature_hit_service_request_ms": first_hit.get("mature_hit_service_request_ms"),
        "mature_hit_speedup_vs_baseline": first_hit.get(
            "mature_cache_hit_speedup_vs_baseline"
        ),
        "policy_deltas": policy_deltas,
    }

    return {
        "type": "async_cache_completion_wait_report",
        "tag": tag,
        "verdict": "PASS" if not failures else "FAIL",
        "readiness": "async-cache-completion-wait-ready" if not failures else "not-ready",
        "failures": failures,
        "source_artifacts": {
            "sweep_json": str(sweep_json),
            "gate_json": str(gate_json),
            "performance_report": str(performance_report),
        },
        "acceptance": {
            "pending_wait_hit": first_hit.get("cache_pending_wait_result") == "hit",
            "cache_hit": bool(first_hit.get("cache_hit")),
            "actual_prefill_tokens_within_budget": (
                int(first_hit.get("wait_hit_actual_prefill_tokens") or 1_000_000)
                <= max_actual_prefill_tokens
            ),
            "wait_within_budget": (
                float(first_hit.get("cache_pending_wait_ms") or 1_000_000.0)
                <= max_wait_ms
            ),
            "gate_passed": gate.get("verdict") == "PASS",
        },
        "recommended_runtime_config": recommended,
        "best_mature_no_wait": {
            "prefix_cache_async_idle_grace_ms": best_mature.get("async_idle_grace_ms"),
            "prefix_cache_pending_wait_ms": best_mature.get("pending_wait_ms"),
            "mature_hit_service_request_ms": best_mature.get("mature_hit_service_request_ms"),
            "mature_hit_speedup_vs_baseline": best_mature.get(
                "mature_cache_hit_speedup_vs_baseline"
            ),
        },
        "performance_baseline": performance.get("current"),
        "performance_target": performance.get("target"),
        "live_rerun_command": output_live_command,
        "decision": (
            "Use a bounded pending wait around 1000 ms for conversion turns when "
            "the async prefix build is already pending. It converts the duplicate "
            "request into a cache hit with low actual prefill while preserving "
            "foreground queue safety through the existing pending-wait accounting."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--sweep-json",
        type=Path,
        default=Path("artifacts/m79-async-maturation/async-maturation-qwen-a3b-m79-stable.json"),
    )
    parser.add_argument(
        "--gate-json",
        type=Path,
        default=Path("artifacts/m80-agent-workspace-async/async-maturation-gate-qwen-a3b-m80.json"),
    )
    parser.add_argument(
        "--performance-report",
        type=Path,
        default=Path(
            "artifacts/m194-performance-report/"
            "prompt-processing-performance-report-m194-qwen-a3b.json"
        ),
    )
    parser.add_argument(
        "--live-rerun-command",
        default=(
            "python3 benchmarks/python/async_maturation_sweep.py "
            "--base-url http://127.0.0.1:8773 "
            "--output-jsonl artifacts/m204-async-cache-completion-wait/"
            "async-cache-completion-wait-live-m204-qwen-a3b.jsonl "
            "--output-json artifacts/m204-async-cache-completion-wait/"
            "async-cache-completion-wait-live-m204-qwen-a3b.json "
            "--grace-ms 0,25,50 --pending-wait-ms 0,500,1000,1500 "
            "--fail-on-no-hit"
        ),
    )
    parser.add_argument(
        "--output-json",
        type=Path,
        default=Path(
            "artifacts/m204-async-cache-completion-wait/"
            "async-cache-completion-wait-m204-qwen-a3b.json"
        ),
    )
    parser.add_argument("--tag", default="m204-qwen-a3b")
    parser.add_argument("--max-wait-ms", type=float, default=1200.0)
    parser.add_argument("--max-actual-prefill-tokens", type=int, default=16)
    parser.add_argument("--fail-on-fail", action="store_true")
    args = parser.parse_args()

    report = build_report(
        sweep_json=args.sweep_json,
        gate_json=args.gate_json,
        performance_report=args.performance_report,
        output_live_command=args.live_rerun_command,
        tag=args.tag,
        max_wait_ms=args.max_wait_ms,
        max_actual_prefill_tokens=args.max_actual_prefill_tokens,
    )
    cfg = report["recommended_runtime_config"]
    print(
        "async_cache_completion_wait",
        report["verdict"],
        "grace_ms",
        cfg["prefix_cache_async_idle_grace_ms"],
        "pending_wait_ms",
        cfg["prefix_cache_pending_wait_ms"],
        "observed_wait_ms",
        round(float(cfg["cache_pending_wait_observed_ms"] or 0.0), 2),
        "actual_prefill",
        cfg["wait_hit_actual_prefill_tokens"],
    )
    for failure in report["failures"]:
        print("async_cache_completion_wait_failure", failure)
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    return 1 if args.fail_on_fail and report["verdict"] != "PASS" else 0


if __name__ == "__main__":
    raise SystemExit(main())
