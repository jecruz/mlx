#!/usr/bin/env python3
"""Probe compact/off/full response metrics shaping."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from mlx_engine.response_metrics import attach_engine_metrics, shape_engine_metrics


def sample_row() -> dict[str, Any]:
    return {
        "request_id": "req_metrics",
        "created": 123,
        "model": "local-mlx",
        "backend": "text",
        "effective_policy": "throughput_default",
        "prefill_step_size": 512,
        "prompt_tokens": 2048,
        "actual_prefill_tokens": 10,
        "generation_tokens": 8,
        "run_ms": 123.4,
        "service_request_ms": 150.0,
        "engine_lock_wait_ms": 1.0,
        "scheduler_queue_wait_ms": 0.0,
        "cache_reuse_enabled": True,
        "cache_hit": True,
        "cache_created": False,
        "cache_scheduled": False,
        "cache_pending": False,
        "cache_prepare_ms": 4.5,
        "cached_prefix_tokens": 2038,
        "cache_pending_wait_ms": 0.0,
        "cache_pending_wait_result": None,
        "prefix_lookup_fast_path": True,
        "prefix_lookup_path": "exact_token_hash",
        "tokenized_prompt_cache_hit": True,
        "tokenized_prompt_cache_ms": 0.2,
        "stop_reason": "length",
        "prompt_progress_trace": [{"processed_tokens": i} for i in range(16)],
        "heavy_debug_blob": "x" * 4096,
    }


def build_report(*, performance_report: Path, tag: str) -> dict[str, Any]:
    row = sample_row()
    full = shape_engine_metrics(row, requested="full", diagnostics_workload=False)
    compact = shape_engine_metrics(row, requested="compact", diagnostics_workload=False)
    off = shape_engine_metrics(row, requested="off", diagnostics_workload=False)
    diagnostics = shape_engine_metrics(
        row,
        requested="compact",
        diagnostics_workload=True,
    )
    payload: dict[str, Any] = {"id": "cmpl-test"}
    attach_engine_metrics(
        payload,
        row,
        requested="compact",
        diagnostics_workload=False,
    )

    full_json_bytes = len(json.dumps(full, sort_keys=True).encode("utf-8"))
    compact_json_bytes = len(json.dumps(compact, sort_keys=True).encode("utf-8"))
    reduction = (
        1.0 - compact_json_bytes / full_json_bytes if full_json_bytes > 0 else 0.0
    )
    failures: list[str] = []
    if full is None or full.get("metrics_detail") != "full":
        failures.append("full metrics detail did not preserve full row")
    if compact is None or compact.get("metrics_detail") != "compact":
        failures.append("compact metrics detail did not return compact metrics")
    if compact and "heavy_debug_blob" in compact:
        failures.append("compact metrics retained heavy debug blob")
    if compact and "prompt_progress_trace" in compact:
        failures.append("compact metrics retained prompt progress trace")
    if off is not None:
        failures.append("off metrics detail returned metrics")
    if diagnostics is None or diagnostics.get("metrics_detail") != "full":
        failures.append("diagnostics workload did not force full metrics")
    if "engine_metrics" not in payload:
        failures.append("attach_engine_metrics did not attach compact metrics")
    if reduction < 0.25:
        failures.append(f"compact reduction too small: {reduction:.3f}")

    performance = json.loads(performance_report.read_text())
    return {
        "type": "response_metrics_trim_probe",
        "tag": tag,
        "verdict": "PASS" if not failures else "FAIL",
        "readiness": "response-metrics-trim-ready" if not failures else "not-ready",
        "failures": failures,
        "acceptance": {
            "compact_metrics_available": compact is not None,
            "off_metrics_omits_payload": off is None,
            "diagnostics_forces_full_metrics": (
                diagnostics is not None and diagnostics.get("metrics_detail") == "full"
            ),
            "compact_drops_heavy_fields": (
                compact is not None
                and "heavy_debug_blob" not in compact
                and "prompt_progress_trace" not in compact
            ),
            "compact_reduction_ratio": reduction,
        },
        "sizes": {
            "full_json_bytes": full_json_bytes,
            "compact_json_bytes": compact_json_bytes,
            "reduction_ratio": reduction,
        },
        "performance_baseline": performance.get("current"),
        "performance_target": performance.get("target"),
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
            "artifacts/m205-response-metrics-trim/"
            "response-metrics-trim-m205-qwen-a3b.json"
        ),
    )
    parser.add_argument("--tag", default="m205-qwen-a3b")
    parser.add_argument("--fail-on-fail", action="store_true")
    args = parser.parse_args()

    report = build_report(performance_report=args.performance_report, tag=args.tag)
    print(
        "response_metrics_trim",
        report["verdict"],
        "full_bytes",
        report["sizes"]["full_json_bytes"],
        "compact_bytes",
        report["sizes"]["compact_json_bytes"],
        "reduction",
        round(report["sizes"]["reduction_ratio"], 3),
    )
    for failure in report["failures"]:
        print("response_metrics_trim_failure", failure)
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    return 1 if args.fail_on_fail and report["verdict"] != "PASS" else 0


if __name__ == "__main__":
    raise SystemExit(main())
