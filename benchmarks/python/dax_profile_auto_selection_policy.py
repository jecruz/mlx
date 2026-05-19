#!/usr/bin/env python3
"""Generate and validate a Dax MLX profile auto-selection policy."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text())


def select_profile(signal: dict[str, Any]) -> tuple[str, str]:
    if signal.get("manual_profile"):
        return str(signal["manual_profile"]), "manual override"
    if signal.get("diagnostics"):
        return "diagnostics", "diagnostics requested"
    if signal.get("interactive") and not signal.get("agentic"):
        return "interactive", "foreground interactive use"
    if signal.get("memory_class_gb") in (16, 24, 32) or signal.get("low_memory"):
        return "agent-workspace-low-memory", "bounded memory mode"
    if signal.get("immediate_second_turn"):
        return "agent-workspace-first-hit", "immediate repeated-context second turn"
    if signal.get("agentic") or signal.get("repeated_workspace"):
        return "agent-workspace-async", "steady-state coding-agent reuse"
    return "interactive", "safe default for unknown foreground work"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--decision-gate",
        type=Path,
        default=Path(
            "artifacts/m101-default-profile-decision-gate/default-profile-decision-gate-m101-qwen-a3b.json"
        ),
    )
    parser.add_argument("--output-json", type=Path, required=True)
    parser.add_argument("--tag", default="m106-qwen-a3b")
    parser.add_argument("--fail-on-fail", action="store_true")
    args = parser.parse_args()

    decision = load_json(args.decision_gate)
    recommended = decision.get("recommended_profiles") or {}
    scenarios = [
        {
            "name": "normal_coding_agent",
            "signal": {"agentic": True, "repeated_workspace": True, "memory_class_gb": 64},
            "expected": recommended.get("default_coding_agent"),
        },
        {
            "name": "immediate_second_turn",
            "signal": {"agentic": True, "immediate_second_turn": True, "memory_class_gb": 64},
            "expected": recommended.get("immediate_second_turn"),
        },
        {
            "name": "lower_memory_mac",
            "signal": {"agentic": True, "repeated_workspace": True, "memory_class_gb": 32},
            "expected": recommended.get("lower_memory_mac"),
        },
        {
            "name": "interactive_foreground",
            "signal": {"interactive": True, "agentic": False, "memory_class_gb": 64},
            "expected": recommended.get("interactive"),
        },
        {
            "name": "diagnostics",
            "signal": {"diagnostics": True},
            "expected": recommended.get("diagnostics"),
        },
        {
            "name": "manual_override",
            "signal": {"manual_profile": "agent-workspace-first-hit", "memory_class_gb": 32},
            "expected": "agent-workspace-first-hit",
        },
    ]

    evaluated = []
    failures: list[str] = []
    if decision.get("verdict") != "PASS":
        failures.append(f"decision gate verdict is {decision.get('verdict')!r}")
    for scenario in scenarios:
        selected, reason = select_profile(scenario["signal"])
        passed = selected == scenario["expected"]
        evaluated.append(
            {
                **scenario,
                "selected": selected,
                "reason": reason,
                "verdict": "PASS" if passed else "FAIL",
            }
        )
        if not passed:
            failures.append(
                f"{scenario['name']}: selected={selected!r} expected={scenario['expected']!r}"
            )

    output = {
        "type": "dax_profile_auto_selection_policy",
        "tag": args.tag,
        "verdict": "PASS" if not failures else "FAIL",
        "failures": failures,
        "decision_gate": str(args.decision_gate),
        "rules": [
            "manual profile overrides all automatic choices",
            "diagnostics requests route to diagnostics",
            "foreground non-agentic interactive work routes to interactive",
            "16GB/24GB/32GB or explicit low-memory mode routes to agent-workspace-low-memory",
            "immediate repeated-context second-turn work routes to agent-workspace-first-hit",
            "agentic repeated-workspace work routes to agent-workspace-async",
            "unknown foreground work falls back to interactive",
        ],
        "scenarios": evaluated,
    }
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n")
    print(
        "dax_profile_auto_selection_policy",
        output["verdict"],
        "scenarios",
        len(evaluated),
        "failures",
        len(failures),
        args.output_json,
        flush=True,
    )
    for scenario in evaluated:
        print(
            "scenario",
            scenario["name"],
            scenario["selected"],
            scenario["verdict"],
            scenario["reason"],
            flush=True,
        )
    return 1 if args.fail_on_fail and failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
