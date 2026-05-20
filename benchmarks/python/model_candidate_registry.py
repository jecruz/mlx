#!/usr/bin/env python3
"""Build a compact registry of active and tested MLX model candidates."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


DEFAULT_BLOCKER = "requires model-swap quality and speed acceptance before activation"


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text())


def optional_json(path: Path | None) -> dict[str, Any]:
    if path is None:
        return {}
    return load_json(path)


def comparison_from_workflow(workflow: dict[str, Any]) -> dict[str, Any]:
    path = ((workflow.get("artifacts") or {}).get("model_quality_comparison") or {}).get("path")
    return load_json(Path(path)) if path else {}


def active_model_from_readiness(readiness: dict[str, Any]) -> str | None:
    model_decision = readiness.get("model_decision") or {}
    runtime = readiness.get("runtime") or {}
    card = readiness.get("card") or {}
    card_details = card.get("details") or {}
    return (
        model_decision.get("active_model")
        or runtime.get("model")
        or card_details.get("model")
        or readiness.get("active_model")
    )


def model_size_gb(path: Path) -> float | None:
    if not path.exists():
        return None
    total = 0
    for child in path.rglob("*.safetensors"):
        if child.is_file():
            total += child.stat().st_size
    if total <= 0:
        return None
    return round(total / 1_000_000_000, 3)


def config_summary(path: Path) -> dict[str, Any]:
    config_path = path / "config.json"
    if not config_path.exists():
        return {"exists": path.exists(), "config_exists": False}
    config = load_json(config_path)
    quant = config.get("quantization") or config.get("quantization_config") or {}
    if isinstance(quant, dict):
        quantization = {
            "bits": quant.get("bits"),
            "group_size": quant.get("group_size"),
            "mode": quant.get("mode"),
        }
    else:
        quantization = {}
    return {
        "exists": path.exists(),
        "config_exists": True,
        "model_type": config.get("model_type"),
        "architectures": config.get("architectures") or [],
        "hidden_size": config.get("hidden_size"),
        "num_hidden_layers": config.get("num_hidden_layers"),
        "num_attention_heads": config.get("num_attention_heads"),
        "num_key_value_heads": config.get("num_key_value_heads"),
        "quantization": quantization,
        "size_gb": model_size_gb(path),
    }


def label_for_path(path: Path) -> str:
    return path.name.replace(".", "-").replace("_", "-").lower()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--operator-readiness-json", type=Path, required=True)
    parser.add_argument("--model-swap-workflow-json", type=Path)
    parser.add_argument("--candidate-model", action="append", type=Path, default=[])
    parser.add_argument("--candidate-blocker", default=DEFAULT_BLOCKER)
    parser.add_argument("--output-json", type=Path, required=True)
    parser.add_argument("--tag", default="m189-model-candidate-registry")
    parser.add_argument("--fail-on-fail", action="store_true")
    args = parser.parse_args()

    readiness = load_json(args.operator_readiness_json)
    workflow = optional_json(args.model_swap_workflow_json)
    comparison = comparison_from_workflow(workflow)
    active_model = active_model_from_readiness(readiness)
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
                "candidate_failures": model.get("failures") or [],
                "metadata": config_summary(Path(model_path)) if model_path else {},
            }
        )
    known_models = {candidate["model"] for candidate in candidates}
    for candidate_path in args.candidate_model:
        model_path = str(candidate_path)
        if model_path in known_models:
            continue
        active = model_path == active_model
        summary = config_summary(candidate_path)
        candidate_failures = []
        if not summary["exists"]:
            candidate_failures.append("model path missing")
        if not summary["config_exists"]:
            candidate_failures.append("config.json missing")
        candidates.append(
            {
                "label": label_for_path(candidate_path),
                "model": model_path,
                "active": active,
                "quality_verdict": "PASS" if active else "UNTESTED",
                "swap_decision": "ACCEPT" if active else "PENDING",
                "readiness": "active" if active else "candidate-needs-acceptance",
                "blockers": [] if active else [args.candidate_blocker],
                "failure_count": len(candidate_failures),
                "candidate_failures": candidate_failures,
                "metadata": summary,
            }
        )
        known_models.add(model_path)
    if not candidates:
        failures.append("no candidates found in model comparison")
    if not any(candidate["active"] for candidate in candidates):
        failures.append("active model missing from candidate registry")
    failed_candidates = [
        candidate
        for candidate in candidates
        if candidate.get("quality_verdict") not in {"PASS", "UNTESTED"}
        or candidate.get("failure_count", 0) > 0
    ]
    if failed_candidates:
        failures.append("one or more candidates failed registry validation")

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
            "model_swap_workflow_json": str(args.model_swap_workflow_json)
            if args.model_swap_workflow_json
            else None,
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
