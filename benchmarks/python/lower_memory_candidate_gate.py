#!/usr/bin/env python3
"""Gate lower-memory model candidate readiness from registry and memory evidence."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text())


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidate-registry-json", type=Path, required=True)
    parser.add_argument("--lower-memory-json", type=Path, required=True)
    parser.add_argument("--output-json", type=Path, required=True)
    parser.add_argument("--tag", default="m190-lower-memory-candidate")
    parser.add_argument("--max-active-memory-gb", type=float, default=24.0)
    parser.add_argument("--fail-on-fail", action="store_true")
    args = parser.parse_args()

    registry = load_json(args.candidate_registry_json)
    lower_memory = load_json(args.lower_memory_json)
    metrics = lower_memory.get("metrics") or {}
    active_memory = metrics.get("max_active_memory_gb")
    candidates = registry.get("candidates") or []
    active = next((candidate for candidate in candidates if candidate.get("active")), None)
    alternates = [candidate for candidate in candidates if not candidate.get("active")]
    failures = []
    warnings = []
    if registry.get("verdict") != "PASS":
        failures.append(f"candidate registry verdict is {registry.get('verdict')!r}")
    if lower_memory.get("verdict") != "PASS":
        failures.append(f"lower-memory verdict is {lower_memory.get('verdict')!r}")
    if metrics.get("memory_source") != "request_metrics":
        failures.append("lower-memory gate did not use request_metrics")
    if not isinstance(active_memory, int | float):
        failures.append("max_active_memory_gb is missing")
    elif active_memory > args.max_active_memory_gb:
        failures.append(
            f"active model memory {active_memory}GB exceeds {args.max_active_memory_gb}GB"
        )
    if not active:
        failures.append("active model missing")
    for candidate in alternates:
        if candidate.get("swap_decision") != "ACCEPT":
            warnings.append(
                f"{candidate.get('label')} is not promotable: {candidate.get('swap_decision')}"
            )

    output = {
        "type": "lower_memory_candidate_gate",
        "tag": args.tag,
        "verdict": "PASS" if not failures else "FAIL",
        "readiness": "lower-memory-candidate-gated" if not failures else "not-ready",
        "active_model": None if active is None else active.get("model"),
        "max_active_memory_gb": active_memory,
        "max_active_memory_threshold_gb": args.max_active_memory_gb,
        "memory_source": metrics.get("memory_source"),
        "alternate_count": len(alternates),
        "warnings": warnings,
        "failures": failures,
    }
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n")
    print(
        "lower_memory_candidate_gate",
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
