#!/usr/bin/env python3
"""Build a compact registry of active and tested MLX model candidates."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text())


def comparison_from_workflow(workflow: dict[str, Any]) -> dict[str, Any]:
    path = ((workflow.get("artifacts") or {}).get("model_quality_comparison") or {}).get("path")
    return load_json(Path(path)) if path else {}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--operator-readiness-json", type=Path, required=True)
    parser.add_argument("--model-swap-workflow-json", type=Path, required=True)
    parser.add_argument("--output-json", type=Path, required=True)
    parser.add_argument("--tag", default="m189-model-candidate-registry")
    parser.add_argument("--fail-on-fail", action="store_true")
    args = parser.parse_args()

    readiness = load_json(args.operator_readiness_json)
    workflow = load_json(args.model_swap_workflow_json)
    comparison = comparison_from_workflow(workflow)
    active_model = ((readiness.get("model_decision") or {}).get("active_model"))
    blockers = workflow.get("blockers") or []
    candidates = []
    failures = []
    for model in comparison.get("models") or []:
        model_path = model.get("model")
        active = model_path == active_model
        candidates.append(
            {
                "label": model.get("label"),
                "model": model_path,
                "active": active,
                "quality_verdict": model.get("verdict"),
                "swap_decision": "ACCEPT" if active else workflow.get("swap_decision"),
                "readiness": "active" if active else workflow.get("readiness"),
                "blockers": [] if active else blockers,
                "failure_count": len(model.get("failures") or []),
            }
        )
    if not candidates:
        failures.append("no candidates found in model comparison")
    if not any(candidate["active"] for candidate in candidates):
        failures.append("active model missing from candidate registry")
    if any(candidate["quality_verdict"] != "PASS" for candidate in candidates):
        failures.append("one or more candidates failed quality")

    output = {
        "type": "model_candidate_registry",
        "tag": args.tag,
        "verdict": "PASS" if not failures else "FAIL",
        "readiness": "model-candidate-registry-ready" if not failures else "not-ready",
        "active_model": active_model,
        "candidate_count": len(candidates),
        "candidates": candidates,
        "source_artifacts": {
            "operator_readiness_json": str(args.operator_readiness_json),
            "model_swap_workflow_json": str(args.model_swap_workflow_json),
            "model_quality_comparison_json": ((workflow.get("artifacts") or {}).get("model_quality_comparison") or {}).get("path"),
        },
        "failures": failures,
    }
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n")
    print(
        "model_candidate_registry",
        output["verdict"],
        output["readiness"],
        "candidates",
        len(candidates),
        "failures",
        len(failures),
        args.output_json,
    )
    for failure in failures:
        print("failure", failure)
    return 1 if args.fail_on_fail and failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
