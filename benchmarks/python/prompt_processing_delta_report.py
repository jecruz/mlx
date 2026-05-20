#!/usr/bin/env python3
"""Compare current prompt-processing performance against prior baselines."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text())


def delta(current: float | None, baseline: float | None) -> float | None:
    if not isinstance(current, int | float) or not isinstance(baseline, int | float):
        return None
    return current - baseline


def ratio(current: float | None, baseline: float | None) -> float | None:
    if not isinstance(current, int | float) or not isinstance(baseline, int | float) or baseline == 0:
        return None
    return current / baseline


def pct(current: float | None, baseline: float | None) -> float | None:
    value = ratio(current, baseline)
    if value is None:
        return None
    return round((value - 1.0) * 100.0, 3)


def rounded(value: Any, digits: int = 3) -> Any:
    return round(value, digits) if isinstance(value, int | float) else value


def repeated_summary(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "verdict": payload.get("verdict"),
        "baseline_service_request_ms": payload.get("baseline_service_request_ms"),
        "best_hit_service_request_ms": payload.get("best_hit_service_request_ms"),
        "best_hit_speedup_vs_baseline": payload.get("best_hit_speedup_vs_baseline"),
        "hit_count": payload.get("hit_count"),
        "baseline_actual_prefill_tokens": (payload.get("baseline") or {}).get("actual_prefill_tokens"),
        "best_hit_actual_prefill_tokens": (payload.get("best_hit") or {}).get("actual_prefill_tokens"),
    }


def overhead_summary(payload: dict[str, Any]) -> dict[str, Any]:
    metrics = payload.get("metrics") or {}
    return {
        "verdict": payload.get("verdict"),
        "mean_overhead_ms": metrics.get("mean_overhead_ms"),
        "p95_overhead_ms": metrics.get("p95_overhead_ms"),
        "max_overhead_ms": metrics.get("max_overhead_ms"),
    }


def prompt_transport_summary(payload: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for row in payload.get("rows") or []:
        if row.get("transport") != "resident":
            continue
        rows.append(
            {
                "target_prompt_tokens": row.get("target_prompt_tokens"),
                "actual_prefill_tokens": row.get("actual_prefill_tokens"),
                "service_request_ms": row.get("service_request_ms"),
                "wall_ms": row.get("wall_ms"),
                "prompt_tps": (row.get("engine_metrics") or {}).get("prompt_tps"),
            }
        )
    return rows


def compare_numeric(current: dict[str, Any], baseline: dict[str, Any], key: str) -> dict[str, Any]:
    current_value = current.get(key)
    baseline_value = baseline.get(key)
    return {
        "baseline": baseline_value,
        "current": current_value,
        "delta": rounded(delta(current_value, baseline_value)),
        "ratio": rounded(ratio(current_value, baseline_value)),
        "percent_delta": pct(current_value, baseline_value),
    }


def write_markdown(path: Path, output: dict[str, Any]) -> None:
    repeated = output["comparisons"]["repeated_context_vs_m180"]
    overhead = output["comparisons"]["operator_overhead_vs_m180"]
    m194 = output["comparisons"]["prompt_report_vs_m194"]
    lines = [
        "# M209 Prompt Processing Delta Report",
        "",
        f"Verdict: `{output['verdict']}`",
        f"Readiness: `{output['readiness']}`",
        "",
        "## Repeated Context",
        "",
        f"- baseline service request: `{repeated['baseline_service_request_ms']['baseline']}` -> `{repeated['baseline_service_request_ms']['current']}` ms",
        f"- best-hit service request: `{repeated['best_hit_service_request_ms']['baseline']}` -> `{repeated['best_hit_service_request_ms']['current']}` ms",
        f"- best-hit service delta: `{repeated['best_hit_service_request_ms']['delta']}` ms",
        f"- speedup: `{repeated['best_hit_speedup_vs_baseline']['baseline']}` -> `{repeated['best_hit_speedup_vs_baseline']['current']}` x",
        "",
        "## Operator Overhead",
        "",
        f"- mean overhead: `{overhead['mean_overhead_ms']['baseline']}` -> `{overhead['mean_overhead_ms']['current']}` ms",
        f"- p95 overhead: `{overhead['p95_overhead_ms']['baseline']}` -> `{overhead['p95_overhead_ms']['current']}` ms",
        "",
        "## M194 Target",
        "",
        f"- M194 mature-hit latency: `{m194['mature_hit_service_request_ms']['baseline']}` ms",
        f"- M206 mature-hit latency: `{m194['mature_hit_service_request_ms']['current']}` ms",
        f"- target mature-hit latency: `{output['target']['mature_hit_service_request_ms']}` ms",
        f"- target gap: `{output['target']['current_gap_ms']}` ms",
        "",
        "## Quality",
        "",
        f"- quality threshold: `{output['quality']['threshold_verdict']}`",
        f"- live suite: `{output['quality']['live_suite_verdict']}`",
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
    parser.add_argument("--baseline-repeated-json", type=Path, required=True)
    parser.add_argument("--current-repeated-json", type=Path, required=True)
    parser.add_argument("--baseline-overhead-json", type=Path, required=True)
    parser.add_argument("--current-overhead-json", type=Path, required=True)
    parser.add_argument("--baseline-prompt-report-json", type=Path, required=True)
    parser.add_argument("--current-prompt-transport-json", type=Path, required=True)
    parser.add_argument("--current-live-suite-json", type=Path, required=True)
    parser.add_argument("--current-quality-threshold-json", type=Path, required=True)
    parser.add_argument("--output-json", type=Path, required=True)
    parser.add_argument("--output-md", type=Path, required=True)
    parser.add_argument("--tag", default="m209-prompt-processing-delta")
    parser.add_argument("--target-mature-hit-ms", type=float, default=175.0)
    parser.add_argument("--fail-on-fail", action="store_true")
    args = parser.parse_args()

    baseline_repeated = repeated_summary(load_json(args.baseline_repeated_json))
    current_repeated = repeated_summary(load_json(args.current_repeated_json))
    baseline_overhead = overhead_summary(load_json(args.baseline_overhead_json))
    current_overhead = overhead_summary(load_json(args.current_overhead_json))
    baseline_prompt_report = load_json(args.baseline_prompt_report_json)
    current_live_suite = load_json(args.current_live_suite_json)
    current_quality = load_json(args.current_quality_threshold_json)
    baseline_current = baseline_prompt_report.get("current") or {}
    mature_current = current_repeated.get("best_hit_service_request_ms")
    target_gap = (
        None
        if not isinstance(mature_current, int | float)
        else round(mature_current - args.target_mature_hit_ms, 3)
    )

    failures: list[str] = []
    warnings: list[str] = []
    for name, summary in {
        "baseline repeated": baseline_repeated,
        "current repeated": current_repeated,
        "baseline overhead": baseline_overhead,
        "current overhead": current_overhead,
    }.items():
        if summary.get("verdict") != "PASS":
            failures.append(f"{name} verdict is {summary.get('verdict')!r}")
    if current_live_suite.get("verdict") != "PASS":
        failures.append(f"current live suite verdict is {current_live_suite.get('verdict')!r}")
    if current_quality.get("verdict") != "PASS":
        failures.append(f"current quality threshold verdict is {current_quality.get('verdict')!r}")
    if isinstance(target_gap, int | float) and target_gap > 0:
        warnings.append(
            f"current mature-hit latency is {mature_current:.3f}ms; target is {args.target_mature_hit_ms:.3f}ms"
        )
    mature_delta = delta(
        current_repeated.get("best_hit_service_request_ms"),
        baseline_repeated.get("best_hit_service_request_ms"),
    )
    if isinstance(mature_delta, int | float) and mature_delta > 0:
        warnings.append(f"mature repeated-context latency regressed by {mature_delta:.3f}ms vs M180")

    output = {
        "type": "prompt_processing_delta_report",
        "tag": args.tag,
        "verdict": "PASS" if not failures else "FAIL",
        "readiness": "prompt-processing-delta-reported" if not failures else "not-ready",
        "comparisons": {
            "repeated_context_vs_m180": {
                "baseline_service_request_ms": compare_numeric(
                    current_repeated, baseline_repeated, "baseline_service_request_ms"
                ),
                "best_hit_service_request_ms": compare_numeric(
                    current_repeated, baseline_repeated, "best_hit_service_request_ms"
                ),
                "best_hit_speedup_vs_baseline": compare_numeric(
                    current_repeated, baseline_repeated, "best_hit_speedup_vs_baseline"
                ),
            },
            "operator_overhead_vs_m180": {
                "mean_overhead_ms": compare_numeric(
                    current_overhead, baseline_overhead, "mean_overhead_ms"
                ),
                "p95_overhead_ms": compare_numeric(
                    current_overhead, baseline_overhead, "p95_overhead_ms"
                ),
            },
            "prompt_report_vs_m194": {
                "mature_hit_service_request_ms": {
                    "baseline": baseline_current.get("mature_hit_service_request_ms"),
                    "current": mature_current,
                    "delta": rounded(delta(mature_current, baseline_current.get("mature_hit_service_request_ms"))),
                    "percent_delta": pct(mature_current, baseline_current.get("mature_hit_service_request_ms")),
                },
                "speedup_vs_baseline": {
                    "baseline": baseline_current.get("speedup_vs_baseline"),
                    "current": current_repeated.get("best_hit_speedup_vs_baseline"),
                    "delta": rounded(
                        delta(
                            current_repeated.get("best_hit_speedup_vs_baseline"),
                            baseline_current.get("speedup_vs_baseline"),
                        )
                    ),
                    "percent_delta": pct(
                        current_repeated.get("best_hit_speedup_vs_baseline"),
                        baseline_current.get("speedup_vs_baseline"),
                    ),
                },
            },
        },
        "target": {
            "mature_hit_service_request_ms": args.target_mature_hit_ms,
            "current_gap_ms": target_gap,
        },
        "current_prompt_transport": prompt_transport_summary(load_json(args.current_prompt_transport_json)),
        "quality": {
            "live_suite_verdict": current_live_suite.get("verdict"),
            "live_suite_readiness": current_live_suite.get("readiness"),
            "threshold_verdict": current_quality.get("verdict"),
            "threshold_readiness": current_quality.get("readiness"),
        },
        "source_artifacts": {
            "baseline_repeated_json": str(args.baseline_repeated_json),
            "current_repeated_json": str(args.current_repeated_json),
            "baseline_overhead_json": str(args.baseline_overhead_json),
            "current_overhead_json": str(args.current_overhead_json),
            "baseline_prompt_report_json": str(args.baseline_prompt_report_json),
            "current_prompt_transport_json": str(args.current_prompt_transport_json),
            "current_live_suite_json": str(args.current_live_suite_json),
            "current_quality_threshold_json": str(args.current_quality_threshold_json),
        },
        "warnings": warnings,
        "failures": failures,
    }
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n")
    write_markdown(args.output_md, output)
    print(
        "prompt_processing_delta_report",
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
