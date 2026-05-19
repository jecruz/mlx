#!/usr/bin/env python3
"""Gate runtime profile auto-selection against the benchmark implementation."""

from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path
from typing import Any


def load_benchmark_module(path: Path) -> Any:
    spec = importlib.util.spec_from_file_location("dax_repeated_context_bench", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"could not load benchmark module from {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--benchmark",
        type=Path,
        default=Path("benchmarks/python/dax_repeated_context_bench.py"),
    )
    parser.add_argument("--output-json", type=Path, required=True)
    parser.add_argument("--tag", default="m119-qwen-a3b")
    parser.add_argument("--fail-on-fail", action="store_true")
    args = parser.parse_args()

    module = load_benchmark_module(args.benchmark)
    scenarios = [
        {
            "name": "normal_coding_agent",
            "kwargs": {"agentic": True},
            "expected_profile": "agent-workspace-async",
        },
        {
            "name": "immediate_second_turn",
            "kwargs": {"agentic": True, "immediate_second_turn": True},
            "expected_profile": "agent-workspace-first-hit",
        },
        {
            "name": "lower_memory_mac_32gb",
            "kwargs": {"agentic": True, "memory_class_gb": 32},
            "expected_profile": "agent-workspace-low-memory",
        },
        {
            "name": "interactive_foreground",
            "kwargs": {"interactive": True},
            "expected_profile": "interactive",
        },
        {
            "name": "diagnostics",
            "kwargs": {"diagnostics": True},
            "expected_profile": "diagnostics",
        },
        {
            "name": "manual_override",
            "kwargs": {
                "manual_profile": "agent-workspace-first-hit",
                "agentic": True,
                "memory_class_gb": 32,
            },
            "expected_profile": "agent-workspace-first-hit",
        },
    ]

    results = []
    failures = []
    for scenario in scenarios:
        profile, reason = module.auto_select_runtime_profile(**scenario["kwargs"])
        passed = profile == scenario["expected_profile"]
        if not passed:
            failures.append(
                f"{scenario['name']}: profile={profile!r} "
                f"expected={scenario['expected_profile']!r}"
            )
        results.append(
            {
                "name": scenario["name"],
                "kwargs": scenario["kwargs"],
                "expected_profile": scenario["expected_profile"],
                "observed_profile": profile,
                "reason": reason,
                "verdict": "PASS" if passed else "FAIL",
            }
        )

    output = {
        "type": "profile_auto_selection_runtime_gate",
        "tag": args.tag,
        "verdict": "PASS" if not failures else "FAIL",
        "benchmark": str(args.benchmark),
        "scenario_count": len(scenarios),
        "failures": failures,
        "scenarios": results,
    }
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n")
    print(
        "profile_auto_selection_runtime_gate",
        output["verdict"],
        "scenarios",
        len(scenarios),
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
