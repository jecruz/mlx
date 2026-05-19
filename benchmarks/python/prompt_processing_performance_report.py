#!/usr/bin/env python3
"""Build a prompt-processing performance report from gated artifacts."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text())


def pct(value: float) -> float:
    return round(value * 100.0, 3)


def write_markdown(path: Path, output: dict[str, Any]) -> None:
    current = output["current"]
    target = output["target"]
    lines = [
        "# M194 Prompt Processing Performance Report",
        "",
        f"Verdict: `{output['verdict']}`",
        f"Readiness: `{output['readiness']}`",
        "",
        "## Current",
        "",
        f"- baseline service request: `{current['baseline_service_request_ms']} ms`",
        f"- mature reusable-turn service request: `{current['mature_hit_service_request_ms']} ms`",
        f"- speedup vs baseline: `{current['speedup_vs_baseline']}x`",
        f"- max active memory: `{current['max_active_memory_gb']} GB`",
        f"- quality threshold: `{current['quality_threshold_verdict']}`",
        "",
        "## Target",
        "",
        f"- mature reusable-turn target: `{target['mature_hit_service_request_ms']} ms`",
        f"- required reduction: `{target['required_reduction_ms']} ms`",
        f"- required reduction percent: `{target['required_reduction_percent']}%`",
        "",
        "## Warnings",
        "",
    ]
    lines.extend([f"- `{warning}`" for warning in output["warnings"]] or ["- none"])
    lines.extend(["", "## Failures", ""])
    lines.extend([f"- `{failure}`" for failure in output["failures"]] or ["- none"])
    lines.append("")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--first-turn-json", type=Path, required=True)
    parser.add_argument("--lower-memory-json", type=Path, required=True)
    parser.add_argument("--quality-threshold-json", type=Path, required=True)
    parser.add_argument("--output-json", type=Path, required=True)
    parser.add_argument("--output-md", type=Path, required=True)
    parser.add_argument("--tag", default="m194-prompt-processing-performance")
    parser.add_argument("--target-mature-hit-ms", type=float, default=175.0)
    parser.add_argument("--min-speedup", type=float, default=4.0)
    parser.add_argument("--fail-on-fail", action="store_true")
    args = parser.parse_args()

    first_turn = load_json(args.first_turn_json)
    lower_memory = load_json(args.lower_memory_json)
    quality = load_json(args.quality_threshold_json)
    lower_metrics = lower_memory.get("metrics") or {}
    baseline_ms = first_turn.get("baseline_service_request_ms")
    mature_ms = first_turn.get("best_hit_service_request_ms") or first_turn.get(
        "mature_hit_service_request_ms"
    )
    speedup = first_turn.get("best_hit_speedup_vs_baseline")
    failures = []
    warnings = []
    if first_turn.get("verdict") != "PASS":
        failures.append(f"first reusable-turn gate is {first_turn.get('verdict')!r}")
    if lower_memory.get("verdict") != "PASS":
        failures.append(f"lower-memory gate is {lower_memory.get('verdict')!r}")
    if quality.get("verdict") != "PASS":
        failures.append(f"quality threshold is {quality.get('verdict')!r}")
    if not isinstance(speedup, int | float) or speedup < args.min_speedup:
        failures.append(f"speedup {speedup!r} is below {args.min_speedup}")
    if isinstance(mature_ms, int | float) and mature_ms > args.target_mature_hit_ms:
        warnings.append(
            f"mature reusable-turn latency is {mature_ms:.3f}ms; target is {args.target_mature_hit_ms:.3f}ms"
        )
    reduction_ms = (mature_ms - args.target_mature_hit_ms) if isinstance(mature_ms, int | float) else None
    reduction_pct = (reduction_ms / mature_ms) if isinstance(reduction_ms, int | float) and mature_ms else None
    output = {
        "type": "prompt_processing_performance_report",
        "tag": args.tag,
        "verdict": "PASS" if not failures else "FAIL",
        "readiness": "prompt-processing-performance-reported" if not failures else "not-ready",
        "current": {
            "baseline_service_request_ms": baseline_ms,
            "mature_hit_service_request_ms": mature_ms,
            "speedup_vs_baseline": speedup,
            "max_active_memory_gb": lower_metrics.get("max_active_memory_gb"),
            "max_peak_memory_gb": lower_metrics.get("max_peak_memory_gb"),
            "memory_source": lower_metrics.get("memory_source"),
            "quality_threshold_verdict": quality.get("verdict"),
        },
        "target": {
            "mature_hit_service_request_ms": args.target_mature_hit_ms,
            "required_reduction_ms": None if reduction_ms is None else round(reduction_ms, 3),
            "required_reduction_percent": None if reduction_pct is None else pct(reduction_pct),
            "minimum_speedup_vs_baseline": args.min_speedup,
        },
        "source_artifacts": {
            "first_turn_json": str(args.first_turn_json),
            "lower_memory_json": str(args.lower_memory_json),
            "quality_threshold_json": str(args.quality_threshold_json),
        },
        "warnings": warnings,
        "failures": failures,
    }
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n")
    write_markdown(args.output_md, output)
    print(
        "prompt_processing_performance_report",
        output["verdict"],
        output["readiness"],
        "warnings",
        len(warnings),
        "failures",
        len(failures),
        args.output_json,
    )
    for warning in warnings:
        print("warning", warning)
    for failure in failures:
        print("failure", failure)
    return 1 if args.fail_on_fail and failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
