#!/usr/bin/env python3
"""Gate the Dax/MLX default profile decision against saved evidence."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text())


def as_float(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


def check(
    checks: list[dict[str, Any]],
    failures: list[str],
    *,
    name: str,
    passed: bool,
    actual: Any = None,
    expected: Any = None,
) -> None:
    checks.append(
        {
            "name": name,
            "verdict": "PASS" if passed else "FAIL",
            "actual": actual,
            "expected": expected,
        }
    )
    if not passed:
        failures.append(f"{name}: actual={actual!r} expected={expected!r}")


def profile_summary(summary: dict[str, Any]) -> dict[str, Any]:
    derived = summary.get("derived") or {}
    return {
        "verdict": summary.get("verdict"),
        "dax_profile": summary.get("dax_profile"),
        "conversion_turn": derived.get("conversion_turn"),
        "conversion_actual_prefill_tokens": derived.get("conversion_actual_prefill_tokens"),
        "conversion_ratio_vs_baseline": derived.get("conversion_ratio_vs_baseline"),
        "mature_hit_service_request_ms": derived.get("mature_hit_service_request_ms"),
        "mature_hit_speedup_vs_baseline": derived.get("mature_hit_speedup_vs_baseline"),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--async-gate",
        type=Path,
        default=Path("artifacts/m80-agent-workspace-async/async-maturation-gate-qwen-a3b-m80.json"),
    )
    parser.add_argument(
        "--first-hit-summary",
        type=Path,
        default=Path(
            "artifacts/m97-direct-first-hit-profile/"
            "dax-product-first-hit-summary-m97-qwen-a3b-first-hit-direct.json"
        ),
    )
    parser.add_argument(
        "--low-memory-summary",
        type=Path,
        default=Path(
            "artifacts/m98-direct-low-memory-profile/"
            "dax-product-first-hit-summary-m98-qwen-a3b-low-memory-direct.json"
        ),
    )
    parser.add_argument(
        "--wall-time-report",
        type=Path,
        default=Path("artifacts/m100-operator-wall-time/dax-operator-wall-time-m100-qwen-a3b.json"),
    )
    parser.add_argument(
        "--decision-report",
        type=Path,
        default=Path("docs/mac-local-inference-platform/performance-decision-report-m91-m96.md"),
    )
    parser.add_argument(
        "--routing-doc",
        type=Path,
        default=Path("docs/mac-local-inference-platform/engine-readiness.md"),
    )
    parser.add_argument("--output-json", type=Path, required=True)
    parser.add_argument("--tag", default="m101-qwen-a3b")
    parser.add_argument("--min-async-speedup", type=float, default=2.0)
    parser.add_argument("--min-first-hit-speedup", type=float, default=2.0)
    parser.add_argument("--min-low-memory-speedup", type=float, default=2.0)
    parser.add_argument("--max-conversion-prefill-tokens", type=float, default=32.0)
    parser.add_argument("--min-wall-speedup", type=float, default=1.4)
    parser.add_argument("--fail-on-fail", action="store_true")
    args = parser.parse_args()

    checks: list[dict[str, Any]] = []
    failures: list[str] = []

    async_gate = load_json(args.async_gate)
    first_hit = load_json(args.first_hit_summary)
    low_memory = load_json(args.low_memory_summary)
    wall_time = load_json(args.wall_time_report)
    decision_text = args.decision_report.read_text()
    routing_text = args.routing_doc.read_text()

    async_speedup = as_float((async_gate.get("best") or {}).get("mature_cache_hit_speedup_vs_baseline"))
    async_prefill = as_float((async_gate.get("best") or {}).get("mature_hit_actual_prefill_tokens"))
    check(
        checks,
        failures,
        name="async_gate_passes",
        passed=async_gate.get("verdict") == "PASS",
        actual=async_gate.get("verdict"),
        expected="PASS",
    )
    check(
        checks,
        failures,
        name="async_mature_speedup",
        passed=async_speedup is not None and async_speedup >= args.min_async_speedup,
        actual=async_speedup,
        expected=f">={args.min_async_speedup}",
    )
    check(
        checks,
        failures,
        name="async_mature_prefill_bounded",
        passed=async_prefill is not None and async_prefill <= args.max_conversion_prefill_tokens,
        actual=async_prefill,
        expected=f"<={args.max_conversion_prefill_tokens}",
    )

    for label, summary, expected_profile, min_speedup in [
        ("first_hit", first_hit, "agent-workspace-first-hit", args.min_first_hit_speedup),
        ("low_memory", low_memory, "agent-workspace-low-memory", args.min_low_memory_speedup),
    ]:
        derived = summary.get("derived") or {}
        speedup = as_float(derived.get("mature_hit_speedup_vs_baseline"))
        prefill = as_float(derived.get("conversion_actual_prefill_tokens"))
        check(
            checks,
            failures,
            name=f"{label}_gate_passes",
            passed=summary.get("verdict") == "PASS",
            actual=summary.get("verdict"),
            expected="PASS",
        )
        check(
            checks,
            failures,
            name=f"{label}_profile",
            passed=summary.get("dax_profile") == expected_profile,
            actual=summary.get("dax_profile"),
            expected=expected_profile,
        )
        check(
            checks,
            failures,
            name=f"{label}_conversion_prefill_bounded",
            passed=prefill is not None and prefill <= args.max_conversion_prefill_tokens,
            actual=prefill,
            expected=f"<={args.max_conversion_prefill_tokens}",
        )
        check(
            checks,
            failures,
            name=f"{label}_mature_speedup",
            passed=speedup is not None and speedup >= min_speedup,
            actual=speedup,
            expected=f">={min_speedup}",
        )

    wall_speedups = [
        as_float((case.get("derived") or {}).get("baseline_to_mature_wall_speedup"))
        for case in wall_time.get("cases", [])
    ]
    valid_wall_speedups = [value for value in wall_speedups if value is not None]
    min_wall_speedup = min(valid_wall_speedups) if valid_wall_speedups else None
    check(
        checks,
        failures,
        name="wall_time_report_passes",
        passed=wall_time.get("verdict") == "PASS",
        actual=wall_time.get("verdict"),
        expected="PASS",
    )
    check(
        checks,
        failures,
        name="wall_time_cases_present",
        passed=wall_time.get("case_count") == 4,
        actual=wall_time.get("case_count"),
        expected=4,
    )
    check(
        checks,
        failures,
        name="wall_time_min_speedup",
        passed=min_wall_speedup is not None and min_wall_speedup >= args.min_wall_speedup,
        actual=min_wall_speedup,
        expected=f">={args.min_wall_speedup}",
    )

    for profile in [
        "agent-workspace-async",
        "agent-workspace-first-hit",
        "agent-workspace-low-memory",
    ]:
        check(
            checks,
            failures,
            name=f"decision_report_mentions_{profile}",
            passed=profile in decision_text,
            actual=profile in decision_text,
            expected=True,
        )
        check(
            checks,
            failures,
            name=f"routing_doc_mentions_{profile}",
            passed=profile in routing_text,
            actual=profile in routing_text,
            expected=True,
        )

    output = {
        "type": "dax_default_profile_decision_gate",
        "tag": args.tag,
        "verdict": "PASS" if not failures else "FAIL",
        "failures": failures,
        "checks": checks,
        "evidence": {
            "async_gate": str(args.async_gate),
            "first_hit_summary": str(args.first_hit_summary),
            "low_memory_summary": str(args.low_memory_summary),
            "wall_time_report": str(args.wall_time_report),
            "decision_report": str(args.decision_report),
            "routing_doc": str(args.routing_doc),
        },
        "recommended_profiles": {
            "default_coding_agent": "agent-workspace-async",
            "immediate_second_turn": "agent-workspace-first-hit",
            "lower_memory_mac": "agent-workspace-low-memory",
            "interactive": "interactive",
            "diagnostics": "diagnostics",
        },
        "summaries": {
            "async": {
                "verdict": async_gate.get("verdict"),
                "mature_cache_hit_speedup_vs_baseline": async_speedup,
                "mature_hit_actual_prefill_tokens": async_prefill,
            },
            "first_hit": profile_summary(first_hit),
            "low_memory": profile_summary(low_memory),
            "wall_time": {
                "verdict": wall_time.get("verdict"),
                "case_count": wall_time.get("case_count"),
                "min_baseline_to_mature_wall_speedup": min_wall_speedup,
            },
        },
    }
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n")
    print(
        "dax_default_profile_decision_gate",
        output["verdict"],
        "checks",
        len(checks),
        "failures",
        len(failures),
        args.output_json,
        flush=True,
    )
    for failure in failures:
        print("failure", failure, flush=True)
    return 1 if args.fail_on_fail and failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
