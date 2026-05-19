#!/usr/bin/env python3
"""Gate the next prompt-processing performance target against quality evidence."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text())


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--first-turn-json", type=Path, required=True)
    parser.add_argument("--quality-threshold-json", type=Path, required=True)
    parser.add_argument("--output-json", type=Path, required=True)
    parser.add_argument("--tag", default="m192-prompt-processing-next-target")
    parser.add_argument("--min-speedup", type=float, default=4.0)
    parser.add_argument("--target-mature-hit-ms", type=float, default=175.0)
    parser.add_argument("--fail-on-fail", action="store_true")
    args = parser.parse_args()

    first_turn = load_json(args.first_turn_json)
    quality = load_json(args.quality_threshold_json)
    speedup = first_turn.get("best_hit_speedup_vs_baseline")
    mature_ms = first_turn.get("best_hit_service_request_ms") or first_turn.get(
        "mature_hit_service_request_ms"
    )
    failures = []
    warnings = []
    if first_turn.get("verdict") != "PASS":
        failures.append(f"first reusable-turn gate is {first_turn.get('verdict')!r}")
    if quality.get("verdict") != "PASS":
        failures.append(f"quality threshold is {quality.get('verdict')!r}")
    if not isinstance(speedup, int | float) or speedup < args.min_speedup:
        failures.append(f"speedup {speedup!r} is below {args.min_speedup}")
    if isinstance(mature_ms, int | float) and mature_ms > args.target_mature_hit_ms:
        warnings.append(
            f"mature hit {mature_ms:.3f}ms is above next target {args.target_mature_hit_ms:.3f}ms"
        )

    output = {
        "type": "prompt_processing_next_target_gate",
        "tag": args.tag,
        "verdict": "PASS" if not failures else "FAIL",
        "readiness": "prompt-processing-next-target-ready" if not failures else "not-ready",
        "current": {
            "baseline_service_request_ms": first_turn.get("baseline_service_request_ms"),
            "best_hit_service_request_ms": mature_ms,
            "best_hit_speedup_vs_baseline": speedup,
            "quality_threshold_verdict": quality.get("verdict"),
        },
        "next_target": {
            "mature_hit_service_request_ms": args.target_mature_hit_ms,
            "maintain_min_speedup": args.min_speedup,
            "maintain_quality_threshold": "PASS",
            "focus": "reduce mature reusable-turn latency without quality regression",
        },
        "warnings": warnings,
        "failures": failures,
    }
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n")
    print(
        "prompt_processing_next_target_gate",
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
