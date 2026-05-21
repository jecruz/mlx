#!/usr/bin/env python3
"""Gate lower-memory default-routing policy against current evidence."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text())


def add_check(
    checks: list[dict[str, Any]],
    failures: list[str],
    *,
    label: str,
    passed: bool,
    detail: str,
) -> None:
    checks.append(
        {
            "label": label,
            "verdict": "PASS" if passed else "FAIL",
            "detail": detail,
        }
    )
    if not passed:
        failures.append(f"{label}: {detail}")


def scenario(auto_selection: dict[str, Any], name: str) -> dict[str, Any] | None:
    for row in auto_selection.get("scenarios") or []:
        if row.get("name") == name:
            return row
    return None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--auto-selection-json", type=Path, required=True)
    parser.add_argument("--model-swap-json", type=Path, required=True)
    parser.add_argument("--quality-threshold-json", type=Path, required=True)
    parser.add_argument("--memory-guard-json", type=Path, required=True)
    parser.add_argument("--promotion-gate-json", type=Path, required=True)
    parser.add_argument("--output-json", type=Path, required=True)
    parser.add_argument("--output-md", type=Path, required=True)
    parser.add_argument("--tag", default="m234-lower-memory-default-routing")
    parser.add_argument("--fail-on-fail", action="store_true")
    args = parser.parse_args()

    auto_selection = load_json(args.auto_selection_json)
    swap = load_json(args.model_swap_json)
    quality = load_json(args.quality_threshold_json)
    memory_guard = load_json(args.memory_guard_json)
    promotion = load_json(args.promotion_gate_json)
    promotion_metrics = promotion.get("metrics") or {}

    checks: list[dict[str, Any]] = []
    failures: list[str] = []
    add_check(
        checks,
        failures,
        label="auto_selection_gate",
        passed=auto_selection.get("verdict") == "PASS",
        detail=f"verdict={auto_selection.get('verdict')!r}",
    )
    for name, expected in [
        ("lower_memory_mac_32gb", "agent-workspace-low-memory"),
        ("manual_override", "agent-workspace-first-hit"),
        ("normal_coding_agent", "agent-workspace-async"),
        ("immediate_second_turn", "agent-workspace-first-hit"),
        ("interactive_foreground", "interactive"),
        ("diagnostics", "diagnostics"),
    ]:
        row = scenario(auto_selection, name)
        add_check(
            checks,
            failures,
            label=f"route.{name}",
            passed=row is not None and row.get("observed_profile") == expected,
            detail=(
                f"observed={None if row is None else row.get('observed_profile')!r}, "
                f"expected={expected!r}"
            ),
        )
    add_check(
        checks,
        failures,
        label="model_swap_acceptance",
        passed=swap.get("swap_decision") == "ACCEPT" and swap.get("readiness") == "swap-acceptable",
        detail=f"decision={swap.get('swap_decision')!r}, readiness={swap.get('readiness')!r}",
    )
    add_check(
        checks,
        failures,
        label="quality_threshold",
        passed=quality.get("verdict") == "PASS" and quality.get("readiness") == "ci-quality-ready",
        detail=f"verdict={quality.get('verdict')!r}, readiness={quality.get('readiness')!r}",
    )
    add_check(
        checks,
        failures,
        label="memory_guard",
        passed=memory_guard.get("verdict") == "PASS",
        detail=f"verdict={memory_guard.get('verdict')!r}",
    )
    add_check(
        checks,
        failures,
        label="first_duplicate_service_budget",
        passed=float(promotion_metrics.get("first_duplicate_service_ms") or 0) <= 250.0,
        detail=f"first_duplicate_service_ms={promotion_metrics.get('first_duplicate_service_ms')!r}",
    )
    add_check(
        checks,
        failures,
        label="first_duplicate_cache_hit",
        passed=promotion_metrics.get("first_duplicate_cache_hit") is True,
        detail=f"cache_hit={promotion_metrics.get('first_duplicate_cache_hit')!r}",
    )

    output = {
        "type": "lower_memory_default_routing_policy_gate",
        "tag": args.tag,
        "verdict": "PASS" if not failures else "FAIL",
        "readiness": "lower-memory-default-routing-ready" if not failures else "not-ready",
        "routing_policy": {
            "default_low_memory_profile": "agent-workspace-low-memory",
            "default_when": [
                "explicit low_memory=true",
                "memory_class_gb is 16, 24, or 32",
                "workload_intent is low-memory or coding-agent-low-memory",
            ],
            "do_not_default_when": [
                "manual profile override is present",
                "interactive foreground work is non-agentic",
                "diagnostics workload is requested",
                "64GB+ agentic work without low-memory signal should use agent-workspace-async",
                "immediate second-turn work without low-memory signal should use agent-workspace-first-hit",
            ],
        },
        "inputs": {
            "auto_selection": str(args.auto_selection_json),
            "model_swap": str(args.model_swap_json),
            "quality_threshold": str(args.quality_threshold_json),
            "memory_guard": str(args.memory_guard_json),
            "promotion_gate": str(args.promotion_gate_json),
        },
        "carried_forward_performance": {
            "first_duplicate_service_ms": promotion_metrics.get("first_duplicate_service_ms"),
            "first_duplicate_prefill_tokens": promotion_metrics.get("first_duplicate_prefill_tokens"),
            "first_duplicate_cache_hit": promotion_metrics.get("first_duplicate_cache_hit"),
            "mature_hit_speedup_vs_baseline": promotion_metrics.get("mature_hit_speedup_vs_baseline"),
            "max_peak_memory_gb": promotion_metrics.get("max_peak_memory_gb"),
        },
        "checks": checks,
        "failures": failures,
    }
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n")
    write_markdown(args.output_md, output)
    print(
        "lower_memory_default_routing_policy_gate",
        output["verdict"],
        output["readiness"],
        "checks",
        len(checks),
        "failures",
        len(failures),
        args.output_json,
    )
    for failure in failures:
        print("failure", failure)
    return 1 if args.fail_on_fail and failures else 0


def write_markdown(path: Path, output: dict[str, Any]) -> None:
    lines = [
        "# M234 Lower-Memory Default-Routing Policy Gate",
        "",
        f"Verdict: `{output['verdict']}`",
        f"Readiness: `{output['readiness']}`",
        "",
        "## Default When",
        "",
    ]
    lines.extend(f"- {item}" for item in output["routing_policy"]["default_when"])
    lines.extend(["", "## Do Not Default When", ""])
    lines.extend(f"- {item}" for item in output["routing_policy"]["do_not_default_when"])
    lines.extend(["", "## Checks", "", "| Check | Verdict | Detail |", "| --- | --- | --- |"])
    for check in output["checks"]:
        lines.append(f"| `{check['label']}` | `{check['verdict']}` | `{check['detail']}` |")
    failures = [f"- `{failure}`" for failure in output["failures"]] or ["- none"]
    lines.extend(["", "## Failures", "", *failures, ""])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines))


if __name__ == "__main__":
    raise SystemExit(main())
