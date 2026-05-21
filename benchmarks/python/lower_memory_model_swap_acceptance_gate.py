#!/usr/bin/env python3
"""Accept a lower-memory model swap from promotion-gate evidence."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text())


def add_check(
    checks: list[dict[str, Any]],
    blockers: list[str],
    *,
    label: str,
    verdict: bool,
    detail: str,
) -> None:
    checks.append(
        {
            "label": label,
            "verdict": "PASS" if verdict else "FAIL",
            "detail": detail,
        }
    )
    if not verdict:
        blockers.append(f"{label}: {detail}")


def write_markdown(path: Path, output: dict[str, Any]) -> None:
    lines = [
        "# M231 Lower-Memory Model Swap Acceptance",
        "",
        f"Verdict: `{output['verdict']}`",
        f"Swap decision: `{output['swap_decision']}`",
        f"Readiness: `{output['readiness']}`",
        "",
        "## Candidate",
        "",
        f"- Model: `{output['candidate']['model']}`",
        f"- Promotion gate: `{output['promotion_gate']['path']}`",
        f"- Quality threshold: `{output['quality_threshold']['path']}`",
        "",
        "## Metrics",
        "",
        "| Metric | Value |",
        "| --- | ---: |",
    ]
    for key, value in output["metrics"].items():
        lines.append(f"| `{key}` | `{value}` |")
    lines.extend(
        [
            "",
            "## Checks",
            "",
            "| Check | Verdict | Detail |",
            "| --- | --- | --- |",
        ]
    )
    for check in output["checks"]:
        lines.append(f"| `{check['label']}` | `{check['verdict']}` | `{check['detail']}` |")
    blocker_lines = [f"- `{blocker}`" for blocker in output["blockers"]] or ["- none"]
    lines.extend(["", "## Blockers", "", *blocker_lines, ""])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines))


def gate(args: argparse.Namespace) -> dict[str, Any]:
    promotion = load_json(args.promotion_gate_json)
    quality = load_json(args.quality_threshold_json)
    metrics = promotion.get("metrics") or {}
    checks: list[dict[str, Any]] = []
    blockers: list[str] = []

    promotion_failures = promotion.get("failures") or []
    quality_failures = quality.get("failures") or []

    add_check(
        checks,
        blockers,
        label="promotion_gate.verdict",
        verdict=promotion.get("verdict") == "PASS",
        detail=f"verdict={promotion.get('verdict')!r}",
    )
    add_check(
        checks,
        blockers,
        label="promotion_gate.readiness",
        verdict=promotion.get("readiness") == "lower-memory-profile-promotable",
        detail=f"readiness={promotion.get('readiness')!r}",
    )
    add_check(
        checks,
        blockers,
        label="promotion_gate.failure_count",
        verdict=len(promotion_failures) == 0,
        detail=f"failures={len(promotion_failures)}",
    )
    add_check(
        checks,
        blockers,
        label="quality_threshold.verdict",
        verdict=quality.get("verdict") == "PASS",
        detail=f"verdict={quality.get('verdict')!r}",
    )
    add_check(
        checks,
        blockers,
        label="quality_threshold.readiness",
        verdict=quality.get("readiness") == "ci-quality-ready",
        detail=f"readiness={quality.get('readiness')!r}",
    )
    add_check(
        checks,
        blockers,
        label="quality_threshold.failure_count",
        verdict=len(quality_failures) == 0,
        detail=f"failures={len(quality_failures)}",
    )
    add_check(
        checks,
        blockers,
        label="candidate.first_duplicate_cache_hit",
        verdict=metrics.get("first_duplicate_cache_hit") is True,
        detail=f"cache_hit={metrics.get('first_duplicate_cache_hit')!r}",
    )
    add_check(
        checks,
        blockers,
        label="candidate.first_duplicate_service_ms",
        verdict=float(metrics.get("first_duplicate_service_ms") or 0) <= args.max_first_duplicate_service_ms,
        detail=(
            f"actual={metrics.get('first_duplicate_service_ms')!r}, "
            f"threshold={args.max_first_duplicate_service_ms}"
        ),
    )
    add_check(
        checks,
        blockers,
        label="candidate.max_peak_memory_gb",
        verdict=float(metrics.get("max_peak_memory_gb") or 0) <= args.max_peak_memory_gb,
        detail=f"actual={metrics.get('max_peak_memory_gb')!r}, threshold={args.max_peak_memory_gb}",
    )
    add_check(
        checks,
        blockers,
        label="candidate.mature_hit_speedup",
        verdict=float(metrics.get("mature_hit_speedup_vs_baseline") or 0) >= args.min_mature_hit_speedup,
        detail=(
            f"actual={metrics.get('mature_hit_speedup_vs_baseline')!r}, "
            f"threshold={args.min_mature_hit_speedup}"
        ),
    )

    swap_decision = "ACCEPT" if not blockers else "REJECT"
    return {
        "type": "lower_memory_model_swap_acceptance_gate",
        "tag": args.tag,
        "verdict": "PASS",
        "swap_decision": swap_decision,
        "readiness": "swap-acceptable" if swap_decision == "ACCEPT" else "swap-blocked",
        "candidate": {
            "model": promotion.get("model") or args.candidate_model,
            "profile": "agent-workspace-first-hit",
        },
        "promotion_gate": {
            "path": str(args.promotion_gate_json),
            "verdict": promotion.get("verdict"),
            "readiness": promotion.get("readiness"),
        },
        "quality_threshold": {
            "path": str(args.quality_threshold_json),
            "verdict": quality.get("verdict"),
            "readiness": quality.get("readiness"),
        },
        "thresholds": {
            "max_first_duplicate_service_ms": args.max_first_duplicate_service_ms,
            "max_peak_memory_gb": args.max_peak_memory_gb,
            "min_mature_hit_speedup": args.min_mature_hit_speedup,
        },
        "metrics": metrics,
        "checks": checks,
        "blockers": blockers,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--promotion-gate-json", type=Path, required=True)
    parser.add_argument("--quality-threshold-json", type=Path, required=True)
    parser.add_argument("--output-json", type=Path, required=True)
    parser.add_argument("--output-md", type=Path, required=True)
    parser.add_argument("--tag", default="m231-lower-memory-model-swap-acceptance")
    parser.add_argument("--candidate-model", default="Qwen2.5-Coder-14B-Instruct-4bit")
    parser.add_argument("--max-first-duplicate-service-ms", type=float, default=250.0)
    parser.add_argument("--max-peak-memory-gb", type=float, default=12.0)
    parser.add_argument("--min-mature-hit-speedup", type=float, default=5.0)
    parser.add_argument("--fail-on-reject", action="store_true")
    args = parser.parse_args()

    output = gate(args)
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n")
    write_markdown(args.output_md, output)
    print(
        "lower_memory_model_swap_acceptance_gate",
        output["verdict"],
        output["swap_decision"],
        output["readiness"],
        "checks",
        len(output["checks"]),
        "blockers",
        len(output["blockers"]),
        args.output_json,
    )
    for blocker in output["blockers"]:
        print("swap_blocker", blocker)
    return 1 if args.fail_on_reject and output["swap_decision"] != "ACCEPT" else 0


if __name__ == "__main__":
    raise SystemExit(main())
