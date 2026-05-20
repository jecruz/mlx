#!/usr/bin/env python3
"""Probe exact repeated-prompt prefix lookup fast path."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from mlx_engine.prefix_cache import PrefixOpportunityTracker


def build_report(*, performance_report: Path, tag: str) -> dict[str, Any]:
    tracker = PrefixOpportunityTracker(max_recent=2, min_match_tokens=32)
    tokens = list(range(2048))
    near_match = tokens[:-1] + [999_999]

    cold = tracker.inspect(prompt="cold", tokens=tokens)
    tracker.record(request_id="req_1", prompt="cold", tokens=tokens)
    exact = tracker.inspect(prompt="cold", tokens=tokens)
    scanned = tracker.inspect(prompt="near", tokens=near_match)
    tracker.record(request_id="req_2", prompt="near", tokens=near_match)
    tracker.record(request_id="req_3", prompt="third", tokens=list(range(3000, 5048)))
    evicted = tracker.inspect(prompt="cold", tokens=tokens)

    failures: list[str] = []
    if cold["prefix_lookup_fast_path"]:
        failures.append("cold lookup unexpectedly used the exact fast path")
    if exact["longest_prefix_match_tokens"] != len(tokens):
        failures.append("exact repeated prompt did not match the full token count")
    if not exact["prefix_lookup_fast_path"]:
        failures.append("exact repeated prompt did not use the fast path")
    if exact["prefix_lookup_path"] != "exact_token_hash":
        failures.append(f"unexpected exact lookup path: {exact['prefix_lookup_path']}")
    if exact["prefix_scan_candidates"] != 0:
        failures.append("exact fast path still scanned recent prompt candidates")
    if scanned["prefix_lookup_fast_path"]:
        failures.append("near-match prompt incorrectly used the exact fast path")
    if scanned["longest_prefix_match_tokens"] != len(tokens) - 1:
        failures.append("near-match scan did not preserve longest-prefix behavior")
    if evicted["matched_request_id"] == "req_1":
        failures.append("evicted exact prompt remained in the recent prompt index")

    baseline = json.loads(performance_report.read_text())
    current = baseline["current"]
    target = baseline["target"]

    return {
        "type": "cache_lookup_fast_path_probe",
        "tag": tag,
        "verdict": "PASS" if not failures else "FAIL",
        "readiness": "cache-lookup-fast-path-ready" if not failures else "not-ready",
        "failures": failures,
        "acceptance": {
            "exact_repeated_prompt_uses_fast_path": exact["prefix_lookup_fast_path"],
            "exact_scan_candidates": exact["prefix_scan_candidates"],
            "near_match_preserves_prefix_scan": (
                scanned["longest_prefix_match_tokens"] == len(tokens) - 1
            ),
            "recent_index_respects_eviction": evicted["matched_request_id"] != "req_1",
        },
        "observations": {
            "cold": cold,
            "exact": exact,
            "near_match": scanned,
            "after_eviction": evicted,
        },
        "performance_baseline": {
            "baseline_service_request_ms": current["baseline_service_request_ms"],
            "mature_hit_service_request_ms": current[
                "mature_hit_service_request_ms"
            ],
            "speedup_vs_baseline": current["speedup_vs_baseline"],
            "quality_threshold_verdict": current["quality_threshold_verdict"],
        },
        "target": {
            "mature_hit_service_request_ms": target[
                "mature_hit_service_request_ms"
            ],
            "required_reduction_ms": target["required_reduction_ms"],
            "required_reduction_percent": target["required_reduction_percent"],
        },
        "expected_latency_effect": (
            "Exact mature prompt-cache hits skip the recent-prompt prefix scan. "
            "This removes redundant admission analysis work before the cache lookup "
            "while preserving scan behavior for non-exact prefix matches."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--performance-report",
        type=Path,
        default=Path(
            "artifacts/m194-performance-report/"
            "prompt-processing-performance-report-m194-qwen-a3b.json"
        ),
    )
    parser.add_argument(
        "--output-json",
        type=Path,
        default=Path(
            "artifacts/m202-cache-lookup-fast-path/"
            "cache-lookup-fast-path-m202-qwen-a3b.json"
        ),
    )
    parser.add_argument("--tag", default="m202-qwen-a3b")
    parser.add_argument("--fail-on-fail", action="store_true")
    args = parser.parse_args()

    report = build_report(performance_report=args.performance_report, tag=args.tag)
    print(
        "cache_lookup_fast_path",
        report["verdict"],
        "exact_fast_path",
        report["acceptance"]["exact_repeated_prompt_uses_fast_path"],
        "exact_scan_candidates",
        report["acceptance"]["exact_scan_candidates"],
        "near_match_scan",
        report["acceptance"]["near_match_preserves_prefix_scan"],
    )
    for failure in report["failures"]:
        print("cache_lookup_fast_path_failure", failure)
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    return 1 if args.fail_on_fail and report["verdict"] != "PASS" else 0


if __name__ == "__main__":
    raise SystemExit(main())
