#!/usr/bin/env python3
"""Gate server-side request metadata profile selection."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from mlx_engine.request_profiles import select_runtime_profile_for_request


def source_contains_request_contract(source: str, field: str) -> bool:
    return f"    {field}:" in source


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-json", type=Path, required=True)
    parser.add_argument("--tag", default="m122-qwen-a3b")
    parser.add_argument(
        "--resident-service",
        type=Path,
        default=Path("mlx_engine/resident_service.py"),
    )
    parser.add_argument("--fail-on-fail", action="store_true")
    args = parser.parse_args()

    source = args.resident_service.read_text()
    scenarios = [
        {
            "name": "coding_agent_intent",
            "kwargs": {"workload_intent": "coding-agent"},
            "expected": "agent-workspace-async",
        },
        {
            "name": "first_hit_intent",
            "kwargs": {"workload_intent": "first-hit"},
            "expected": "agent-workspace-first-hit",
        },
        {
            "name": "low_memory_intent",
            "kwargs": {"workload_intent": "low-memory"},
            "expected": "agent-workspace-low-memory",
        },
        {
            "name": "memory_class_32gb",
            "kwargs": {"workload_intent": "coding-agent", "memory_class_gb": 32},
            "expected": "agent-workspace-low-memory",
        },
        {
            "name": "manual_override",
            "kwargs": {
                "manual_profile": "agent-workspace-first-hit",
                "workload_intent": "low-memory",
            },
            "expected": "agent-workspace-first-hit",
        },
        {
            "name": "diagnostics",
            "kwargs": {"diagnostics": True},
            "expected": "diagnostics",
        },
    ]

    results = []
    failures = []
    for scenario in scenarios:
        observed, reason = select_runtime_profile_for_request(**scenario["kwargs"])
        passed = observed == scenario["expected"]
        if not passed:
            failures.append(
                f"{scenario['name']}: observed={observed!r} expected={scenario['expected']!r}"
            )
        results.append(
            {
                "name": scenario["name"],
                "kwargs": scenario["kwargs"],
                "expected_profile": scenario["expected"],
                "observed_profile": observed,
                "reason": reason,
                "verdict": "PASS" if passed else "FAIL",
            }
        )

    required_fields = {
        "runtime_profile",
        "workload_intent",
        "memory_class_gb",
        "immediate_second_turn",
        "low_memory",
        "diagnostics_workload",
        "interactive_workload",
        "agentic_workload",
        "repeated_workspace",
    }
    schema_checks = []
    for name, marker in (
        ("request_profile_hints", "class RequestProfileHints(BaseModel):"),
        ("completion", "class CompletionRequest(RequestProfileHints):"),
        ("chat", "class ChatCompletionRequest(RequestProfileHints):"),
        ("generate", "class GenerateRequest(RequestProfileHints):"),
    ):
        missing = []
        if marker not in source:
            missing.append(marker)
        if name == "request_profile_hints":
            missing.extend(
                sorted(
                    field
                    for field in required_fields
                    if not source_contains_request_contract(source, field)
                )
            )
        if missing:
            failures.append(f"{name}: missing request profile contract {missing}")
        schema_checks.append(
            {
                "name": name,
                "verdict": "PASS" if not missing else "FAIL",
                "missing_fields": missing,
            }
        )

    output = {
        "type": "request_profile_metadata_gate",
        "tag": args.tag,
        "verdict": "PASS" if not failures else "FAIL",
        "resident_service": str(args.resident_service),
        "scenario_count": len(scenarios),
        "scenarios": results,
        "schema_checks": schema_checks,
        "failures": failures,
    }
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n")
    print(
        "request_profile_metadata_gate",
        output["verdict"],
        "scenarios",
        len(scenarios),
        "schema_checks",
        len(schema_checks),
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
