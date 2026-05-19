#!/usr/bin/env python3
"""Create a compact performance report from current milestone artifacts."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from statistics import mean
from typing import Any


def load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text())


def ms(value: Any) -> float | None:
    return float(value) if isinstance(value, int | float) else None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--m64-gate", type=Path, default=Path("artifacts/m64-real-suite/resident-regression-gate-m64-qwen-a3b.json"))
    parser.add_argument("--m148-suite", type=Path, default=Path("artifacts/m148-live-product-mode-suite/live-product-regression-suite-m148-qwen-a3b.json"))
    parser.add_argument("--m148-repeated", type=Path, default=Path("artifacts/m148-live-product-mode-suite/dax-resident-client-m148-qwen-a3b.json"))
    parser.add_argument("--m148-transport", type=Path, default=Path("artifacts/m148-live-product-mode-suite/live-prompt-transport-sweep-m148-qwen-a3b.json"))
    parser.add_argument("--m151-stress", type=Path, required=True)
    parser.add_argument("--output-json", type=Path, required=True)
    parser.add_argument("--output-md", type=Path, required=True)
    parser.add_argument("--tag", default="m158-qwen-a3b")
    parser.add_argument("--fail-on-fail", action="store_true")
    args = parser.parse_args()

    m64_gate = load(args.m64_gate)
    m148_suite = load(args.m148_suite)
    repeated = load(args.m148_repeated)
    transport = load(args.m148_transport)
    stress = load(args.m151_stress)

    repeated_rows = repeated.get("rows", [])
    transport_rows = transport.get("rows", [])
    hit_rows = [row for row in repeated_rows if row.get("cache_hit")]
    baseline = repeated.get("baseline") or (repeated_rows[0] if repeated_rows else {})
    best_hit = repeated.get("best_hit") or (min(hit_rows, key=lambda row: row.get("service_request_ms", 10**9)) if hit_rows else {})
    resident_transport = next((row for row in transport_rows if row.get("transport") == "resident"), {})
    cli_transport = next((row for row in transport_rows if row.get("transport") == "cli"), {})
    stress_service = [ms(row.get("service_request_ms")) for row in stress.get("rows", [])]
    stress_service = [value for value in stress_service if value is not None]

    failures = []
    for name, artifact in [
        ("m64_gate", m64_gate),
        ("m148_suite", m148_suite),
        ("m151_stress", stress),
    ]:
        if artifact.get("verdict") != "PASS":
            failures.append(f"{name}: verdict {artifact.get('verdict')!r}")

    report = {
        "type": "performance_checkpoint_report",
        "tag": args.tag,
        "verdict": "PASS" if not failures else "FAIL",
        "readiness": "performance-report-current" if not failures else "not-ready",
        "summary": {
            "m64_gate_verdict": m64_gate.get("verdict"),
            "m148_suite_verdict": m148_suite.get("verdict"),
            "m148_artifacts": len(m148_suite.get("artifacts", {})),
            "m148_failures": len(m148_suite.get("failures", [])),
            "repeated_baseline_service_ms": baseline.get("service_request_ms"),
            "repeated_best_hit_service_ms": best_hit.get("service_request_ms"),
            "repeated_best_hit_speedup": repeated.get("best_hit_speedup_vs_baseline"),
            "repeated_best_hit_prefill_tokens": best_hit.get("actual_prefill_tokens"),
            "resident_prompt_transport_ms": resident_transport.get("wall_ms"),
            "cli_prompt_transport_ms": cli_transport.get("wall_ms"),
            "stress_iterations": stress.get("iterations"),
            "stress_rows": stress.get("row_count"),
            "stress_mean_service_ms": mean(stress_service) if stress_service else None,
        },
        "inputs": {
            "m64_gate": str(args.m64_gate),
            "m148_suite": str(args.m148_suite),
            "m148_repeated": str(args.m148_repeated),
            "m148_transport": str(args.m148_transport),
            "m151_stress": str(args.m151_stress),
        },
        "failures": failures,
    }
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_md.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    s = report["summary"]
    args.output_md.write_text(
        "\n".join(
            [
                "# M156 Performance Report",
                "",
                f"Verdict: `{report['verdict']}`",
                "",
                "## Current Suite",
                "",
                f"- M148 live suite: `{s['m148_suite_verdict']}`",
                f"- M148 artifacts: `{s['m148_artifacts']}`",
                f"- M148 failures: `{s['m148_failures']}`",
                "",
                "## Prompt Processing",
                "",
                f"- repeated baseline service ms: `{s['repeated_baseline_service_ms']}`",
                f"- repeated best-hit service ms: `{s['repeated_best_hit_service_ms']}`",
                f"- repeated best-hit speedup: `{s['repeated_best_hit_speedup']}`",
                f"- repeated best-hit prefill tokens: `{s['repeated_best_hit_prefill_tokens']}`",
                f"- resident prompt transport wall ms: `{s['resident_prompt_transport_ms']}`",
                f"- CLI prompt transport wall ms: `{s['cli_prompt_transport_ms']}`",
                "",
                "## Concurrency",
                "",
                f"- stress iterations: `{s['stress_iterations']}`",
                f"- stress rows: `{s['stress_rows']}`",
                f"- stress mean service ms: `{s['stress_mean_service_ms']}`",
                "",
                "## Next Recommendation",
                "",
                "- Continue with deeper repeated concurrency stress under higher queue depth.",
                "- Optimize first reusable-turn latency and cache-admission thresholds using the current M148/M151 gates as acceptance criteria.",
            ]
        )
        + "\n"
    )
    print("performance_checkpoint_report", report["verdict"], args.output_json, args.output_md)
    if args.fail_on_fail and report["verdict"] != "PASS":
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
