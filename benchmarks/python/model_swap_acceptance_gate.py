#!/usr/bin/env python3
"""Decide whether a candidate model/profile swap is acceptable."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text())


def mean_quality_ms(model: dict[str, Any]) -> float | None:
    values = [
        artifact.get("mean_service_request_ms")
        for artifact in (model.get("artifacts") or {}).values()
        if isinstance(artifact.get("mean_service_request_ms"), int | float)
    ]
    return round(sum(values) / len(values), 3) if values else None


def find_model(comparison: dict[str, Any], label: str | None, role: str) -> dict[str, Any]:
    models = comparison.get("models") or []
    if label:
        match = next((model for model in models if model.get("label") == label), None)
        if match is None:
            raise ValueError(f"{role} label not found in comparison: {label}")
        return match
    index = 0 if role == "current" else 1
    if len(models) <= index:
        raise ValueError(f"comparison does not contain {role} model at index {index}")
    return models[index]


def write_markdown(path: Path, output: dict[str, Any]) -> None:
    lines = [
        "# M176 Model Swap Acceptance Gate",
        "",
        f"Verdict: `{output['verdict']}`",
        f"Swap decision: `{output['swap_decision']}`",
        "",
        "## Models",
        "",
        f"- Current: `{output['current']['label']}`",
        f"- Candidate: `{output['candidate']['label']}`",
        f"- Current mean quality gate ms: `{output['current']['mean_quality_gate_ms']}`",
        f"- Candidate mean quality gate ms: `{output['candidate']['mean_quality_gate_ms']}`",
        f"- Candidate slowdown ratio: `{output['derived']['candidate_slowdown_ratio']}`",
        "",
        "## Checks",
        "",
        "| Check | Verdict | Detail |",
        "| --- | --- | --- |",
    ]
    for check in output["checks"]:
        lines.append(f"| `{check['label']}` | `{check['verdict']}` | `{check['detail']}` |")
    blocker_lines = [f"- `{blocker}`" for blocker in output["blockers"]] or ["- none"]
    lines.extend(["", "## Blockers", "", *blocker_lines, ""])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model-comparison-json", type=Path, required=True)
    parser.add_argument("--quality-threshold-json", type=Path, required=True)
    parser.add_argument("--current-label")
    parser.add_argument("--candidate-label")
    parser.add_argument("--output-json", type=Path, required=True)
    parser.add_argument("--output-md", type=Path, required=True)
    parser.add_argument("--tag", default="m176-model-swap-acceptance")
    parser.add_argument("--max-candidate-slowdown-ratio", type=float, default=1.0)
    parser.add_argument("--fail-on-reject", action="store_true")
    args = parser.parse_args()

    comparison = load_json(args.model_comparison_json)
    threshold = load_json(args.quality_threshold_json)
    current = find_model(comparison, args.current_label, "current")
    candidate = find_model(comparison, args.candidate_label, "candidate")
    current_ms = mean_quality_ms(current)
    candidate_ms = mean_quality_ms(candidate)
    slowdown_ratio = (
        round(candidate_ms / current_ms, 6)
        if current_ms is not None and candidate_ms is not None and current_ms > 0
        else None
    )
    checks: list[dict[str, Any]] = []
    blockers: list[str] = []

    def add_check(label: str, verdict: str, detail: str) -> None:
        checks.append({"label": label, "verdict": verdict, "detail": detail})
        if verdict != "PASS":
            blockers.append(f"{label}: {detail}")

    add_check(
        "model_comparison",
        "PASS" if comparison.get("verdict") == "PASS" else "FAIL",
        f"verdict={comparison.get('verdict')!r}",
    )
    add_check(
        "quality_threshold",
        "PASS" if threshold.get("verdict") == "PASS" else "FAIL",
        f"verdict={threshold.get('verdict')!r}",
    )
    add_check(
        "current_quality",
        "PASS" if current.get("verdict") == "PASS" else "FAIL",
        f"verdict={current.get('verdict')!r}",
    )
    add_check(
        "candidate_quality",
        "PASS" if candidate.get("verdict") == "PASS" else "FAIL",
        f"verdict={candidate.get('verdict')!r}",
    )
    if slowdown_ratio is None:
        add_check("candidate_speed", "FAIL", "missing comparable quality gate latency")
    else:
        add_check(
            "candidate_speed",
            "PASS" if slowdown_ratio <= args.max_candidate_slowdown_ratio else "FAIL",
            f"slowdown_ratio={slowdown_ratio}, threshold={args.max_candidate_slowdown_ratio}",
        )

    swap_decision = "ACCEPT" if not blockers else "REJECT"
    output = {
        "type": "model_swap_acceptance_gate",
        "tag": args.tag,
        "verdict": "PASS",
        "swap_decision": swap_decision,
        "readiness": "swap-acceptable" if swap_decision == "ACCEPT" else "swap-blocked",
        "model_comparison": {
            "path": str(args.model_comparison_json),
            "verdict": comparison.get("verdict"),
        },
        "quality_threshold": {
            "path": str(args.quality_threshold_json),
            "verdict": threshold.get("verdict"),
            "readiness": threshold.get("readiness"),
        },
        "current": {
            "label": current.get("label"),
            "model": current.get("model"),
            "verdict": current.get("verdict"),
            "mean_quality_gate_ms": current_ms,
        },
        "candidate": {
            "label": candidate.get("label"),
            "model": candidate.get("model"),
            "verdict": candidate.get("verdict"),
            "mean_quality_gate_ms": candidate_ms,
        },
        "derived": {
            "candidate_slowdown_ratio": slowdown_ratio,
            "max_candidate_slowdown_ratio": args.max_candidate_slowdown_ratio,
        },
        "checks": checks,
        "blockers": blockers,
    }
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n")
    write_markdown(args.output_md, output)
    print(
        "model_swap_acceptance_gate",
        output["verdict"],
        output["swap_decision"],
        output["readiness"],
        "blockers",
        len(blockers),
        args.output_json,
    )
    for blocker in blockers:
        print("swap_blocker", blocker)
    return 1 if args.fail_on_reject and swap_decision != "ACCEPT" else 0


if __name__ == "__main__":
    raise SystemExit(main())
