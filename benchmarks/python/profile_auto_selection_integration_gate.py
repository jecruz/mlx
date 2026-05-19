#!/usr/bin/env python3
"""Gate product readiness for profile auto-selection integration."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--policy",
        type=Path,
        default=Path("artifacts/m106-profile-auto-selection/profile-auto-selection-m106-qwen-a3b.json"),
    )
    parser.add_argument(
        "--readiness-bundle",
        type=Path,
        default=Path("artifacts/m108-product-readiness-bundle/product-readiness-bundle-m108-qwen-a3b.json"),
    )
    parser.add_argument("--output-json", type=Path, required=True)
    parser.add_argument("--tag", default="m113-qwen-a3b")
    parser.add_argument("--fail-on-fail", action="store_true")
    args = parser.parse_args()

    policy = json.loads(args.policy.read_text())
    bundle = json.loads(args.readiness_bundle.read_text())
    scenario_names = {scenario.get("name") for scenario in policy.get("scenarios", [])}
    required = {
        "normal_coding_agent",
        "immediate_second_turn",
        "lower_memory_mac",
        "interactive_foreground",
        "diagnostics",
        "manual_override",
    }
    checks = [
        ("policy_pass", policy.get("verdict") == "PASS"),
        ("bundle_pass", bundle.get("verdict") == "PASS"),
        ("all_required_scenarios", required.issubset(scenario_names)),
        ("manual_override_covered", "manual_override" in scenario_names),
        (
            "next_lane_mentions_auto_selection",
            any("auto-selection" in item for item in bundle.get("next_implementation_lane", [])),
        ),
    ]
    failures = [name for name, passed in checks if not passed]
    output = {
        "type": "profile_auto_selection_integration_gate",
        "tag": args.tag,
        "verdict": "PASS" if not failures else "FAIL",
        "failures": failures,
        "checks": [{"name": name, "verdict": "PASS" if passed else "FAIL"} for name, passed in checks],
        "policy": str(args.policy),
        "readiness_bundle": str(args.readiness_bundle),
        "required_scenarios": sorted(required),
        "observed_scenarios": sorted(scenario_names),
    }
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n")
    print(
        "profile_auto_selection_integration_gate",
        output["verdict"],
        "checks",
        len(checks),
        "failures",
        len(failures),
        args.output_json,
        flush=True,
    )
    return 1 if args.fail_on_fail and failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
