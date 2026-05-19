#!/usr/bin/env python3
"""Validate product-facing workload intents map to expected runtime profiles."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from mlx_engine.request_profiles import select_runtime_profile_for_request


CASES = [
    ("chat", {"interactive": True}, "interactive"),
    ("coding-agent", {"workload_intent": "coding-agent"}, "agent-workspace-async"),
    ("coding-agent-first-hit", {"workload_intent": "coding-agent-first-hit"}, "agent-workspace-first-hit"),
    ("coding-agent-low-memory", {"workload_intent": "coding-agent-low-memory"}, "agent-workspace-low-memory"),
    ("diagnostics", {"workload_intent": "diagnostics"}, "diagnostics"),
    ("manual-override", {"manual_profile": "memory-saver"}, "memory-saver"),
]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-json", type=Path, required=True)
    parser.add_argument("--tag", default="m154-qwen-a3b")
    parser.add_argument("--fail-on-fail", action="store_true")
    args = parser.parse_args()
    rows = []
    failures = []
    for name, kwargs, expected in CASES:
        profile, reason = select_runtime_profile_for_request(**kwargs)
        ok = profile == expected
        if not ok:
            failures.append(f"{name}: {profile!r} != {expected!r}")
        rows.append(
            {
                "case": name,
                "expected_profile": expected,
                "actual_profile": profile,
                "reason": reason,
                "pass": ok,
            }
        )
    output = {
        "type": "product_profile_policy_gate",
        "tag": args.tag,
        "verdict": "PASS" if not failures else "FAIL",
        "readiness": "product-profile-policy-stable" if not failures else "not-ready",
        "rows": rows,
        "failures": failures,
    }
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n")
    print("product_profile_policy_gate", output["verdict"], "rows", len(rows), "failures", len(failures), args.output_json)
    if args.fail_on_fail and output["verdict"] != "PASS":
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
