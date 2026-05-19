#!/usr/bin/env python3
"""One-command artifact workflow for model swap quality acceptance."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any


def run(cmd: list[str], *, cwd: Path) -> None:
    print("model_swap_workflow_cmd", " ".join(cmd), flush=True)
    subprocess.run(cmd, cwd=cwd, check=True)


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text())


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--current-label", required=True)
    parser.add_argument("--current-model", required=True)
    parser.add_argument("--current-artifact", type=Path, action="append", required=True)
    parser.add_argument("--candidate-label", required=True)
    parser.add_argument("--candidate-model", required=True)
    parser.add_argument("--candidate-artifact", type=Path, action="append", required=True)
    parser.add_argument("--quality-artifact", type=Path, action="append", required=True)
    parser.add_argument("--operator-bundle-json", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--tag", default="m179-model-swap-workflow")
    parser.add_argument("--max-candidate-slowdown-ratio", type=float, default=1.0)
    parser.add_argument("--allow-warnings", action="store_true")
    parser.add_argument("--fail-on-reject", action="store_true")
    args = parser.parse_args()

    cwd = Path.cwd()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    comparison_json = args.output_dir / f"model-quality-comparison-{args.tag}.json"
    comparison_md = args.output_dir / f"model-quality-comparison-{args.tag}.md"
    threshold_json = args.output_dir / f"quality-threshold-gate-{args.tag}.json"
    acceptance_json = args.output_dir / f"model-swap-acceptance-{args.tag}.json"
    acceptance_md = args.output_dir / f"model-swap-acceptance-{args.tag}.md"
    workflow_json = args.output_dir / f"model-swap-workflow-{args.tag}.json"

    comparison_cmd = [
        sys.executable,
        "benchmarks/python/model_quality_comparison.py",
        "--current-label",
        args.current_label,
        "--current-model",
        args.current_model,
        "--candidate-label",
        args.candidate_label,
        "--candidate-model",
        args.candidate_model,
        "--output-json",
        str(comparison_json),
        "--output-md",
        str(comparison_md),
        "--tag",
        args.tag,
        "--fail-on-fail",
    ]
    for artifact in args.current_artifact:
        comparison_cmd.extend(["--current-artifact", str(artifact)])
    for artifact in args.candidate_artifact:
        comparison_cmd.extend(["--candidate-artifact", str(artifact)])
    run(comparison_cmd, cwd=cwd)

    threshold_cmd = [
        sys.executable,
        "benchmarks/python/quality_threshold_gate.py",
        "--output-json",
        str(threshold_json),
        "--tag",
        args.tag,
        "--fail-on-fail",
    ]
    for artifact in args.quality_artifact:
        threshold_cmd.extend(["--quality-artifact", str(artifact)])
    if args.operator_bundle_json:
        threshold_cmd.extend(["--operator-bundle-json", str(args.operator_bundle_json)])
    if args.allow_warnings:
        threshold_cmd.append("--allow-warnings")
    run(threshold_cmd, cwd=cwd)

    acceptance_cmd = [
        sys.executable,
        "benchmarks/python/model_swap_acceptance_gate.py",
        "--model-comparison-json",
        str(comparison_json),
        "--quality-threshold-json",
        str(threshold_json),
        "--current-label",
        args.current_label,
        "--candidate-label",
        args.candidate_label,
        "--output-json",
        str(acceptance_json),
        "--output-md",
        str(acceptance_md),
        "--tag",
        args.tag,
        "--max-candidate-slowdown-ratio",
        str(args.max_candidate_slowdown_ratio),
    ]
    if args.fail_on_reject:
        acceptance_cmd.append("--fail-on-reject")
    run(acceptance_cmd, cwd=cwd)

    comparison = load_json(comparison_json)
    threshold = load_json(threshold_json)
    acceptance = load_json(acceptance_json)
    output = {
        "type": "model_swap_workflow",
        "tag": args.tag,
        "verdict": "PASS",
        "readiness": acceptance.get("readiness"),
        "swap_decision": acceptance.get("swap_decision"),
        "artifacts": {
            "model_quality_comparison": {
                "path": str(comparison_json),
                "verdict": comparison.get("verdict"),
            },
            "quality_threshold_gate": {
                "path": str(threshold_json),
                "verdict": threshold.get("verdict"),
                "readiness": threshold.get("readiness"),
            },
            "model_swap_acceptance": {
                "path": str(acceptance_json),
                "verdict": acceptance.get("verdict"),
                "swap_decision": acceptance.get("swap_decision"),
            },
        },
        "blockers": acceptance.get("blockers") or [],
    }
    workflow_json.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n")
    print(
        "model_swap_workflow",
        output["verdict"],
        output["swap_decision"],
        output["readiness"],
        "blockers",
        len(output["blockers"]),
        workflow_json,
    )
    if args.fail_on_reject and output["swap_decision"] != "ACCEPT":
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
