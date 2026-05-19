#!/usr/bin/env python3
"""Validate the operator readiness bundle contract for UI/TUI consumers."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


REQUIRED_TOP_LEVEL = [
    "type",
    "tag",
    "verdict",
    "readiness",
    "status_card",
    "runtime",
    "model_decision",
    "memory",
    "evidence",
    "warnings",
    "failures",
]

REQUIRED_STATUS_CARD = [
    "runtime",
    "quality",
    "live_suite",
    "lower_memory",
    "memory_source",
    "live_model_swap",
    "candidate_swap",
]

REQUIRED_RUNTIME = [
    "base_url",
    "ok",
    "loaded",
    "model",
    "backend",
    "engine_preset",
    "runtime_profile",
    "strategy",
    "gpu_ready",
    "warm",
    "can_generate",
    "can_reload",
    "can_unload",
]

REQUIRED_MODEL_DECISION = [
    "current_label",
    "active_model",
    "candidate_label",
    "candidate_model",
    "swap_decision",
    "readiness",
    "blockers",
]

REQUIRED_MEMORY = [
    "source",
    "max_active_memory_gb",
    "max_peak_memory_gb",
    "health_active_memory_gb",
]

REQUIRED_EVIDENCE = [
    "suite_json",
    "operator_quality_json",
    "model_swap_workflow_json",
    "lower_memory_json",
    "live_model_swap_json",
]


def require_keys(name: str, obj: dict[str, Any], keys: list[str]) -> list[str]:
    return [f"{name} missing {key}" for key in keys if key not in obj]


def require_status(name: str, value: Any, allowed: set[str]) -> list[str]:
    if value not in allowed:
        return [f"{name} has invalid status {value!r}; expected one of {sorted(allowed)}"]
    return []


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bundle-json", type=Path, required=True)
    parser.add_argument("--output-json", type=Path, required=True)
    parser.add_argument("--tag", default="m183-operator-readiness-contract")
    parser.add_argument("--fail-on-fail", action="store_true")
    args = parser.parse_args()

    bundle = json.loads(args.bundle_json.read_text())
    failures: list[str] = []
    failures.extend(require_keys("bundle", bundle, REQUIRED_TOP_LEVEL))
    if bundle.get("type") != "operator_readiness_bundle":
        failures.append(f"bundle type is {bundle.get('type')!r}")
    failures.extend(require_status("verdict", bundle.get("verdict"), {"PASS", "FAIL"}))
    failures.extend(
        require_status(
            "readiness",
            bundle.get("readiness"),
            {"operator-readiness-ready", "operator-readiness-blocked"},
        )
    )

    status_card = bundle.get("status_card") or {}
    runtime = bundle.get("runtime") or {}
    model_decision = bundle.get("model_decision") or {}
    memory = bundle.get("memory") or {}
    evidence = bundle.get("evidence") or {}
    failures.extend(require_keys("status_card", status_card, REQUIRED_STATUS_CARD))
    failures.extend(require_keys("runtime", runtime, REQUIRED_RUNTIME))
    failures.extend(require_keys("model_decision", model_decision, REQUIRED_MODEL_DECISION))
    failures.extend(require_keys("memory", memory, REQUIRED_MEMORY))
    failures.extend(require_keys("evidence", evidence, REQUIRED_EVIDENCE))

    for key in REQUIRED_STATUS_CARD:
        if key in status_card:
            failures.extend(require_status(f"status_card.{key}", status_card[key], {"PASS", "WARN", "FAIL"}))

    if not isinstance(bundle.get("warnings"), list):
        failures.append("warnings must be a list")
    if not isinstance(bundle.get("failures"), list):
        failures.append("failures must be a list")
    if memory.get("source") != "request_metrics":
        failures.append(f"memory.source is {memory.get('source')!r}; expected 'request_metrics'")
    for key in ("max_active_memory_gb", "max_peak_memory_gb"):
        value = memory.get(key)
        if not isinstance(value, int | float) or value <= 0:
            failures.append(f"memory.{key} must be a positive number")
    if not model_decision.get("active_model"):
        failures.append("model_decision.active_model is required")
    if model_decision.get("swap_decision") not in {"ACCEPT", "REJECT"}:
        failures.append("model_decision.swap_decision must be ACCEPT or REJECT")

    output = {
        "type": "operator_readiness_contract_probe",
        "tag": args.tag,
        "bundle_json": str(args.bundle_json),
        "verdict": "PASS" if not failures else "FAIL",
        "readiness": "operator-readiness-contract-ready" if not failures else "not-ready",
        "required_top_level": REQUIRED_TOP_LEVEL,
        "required_status_card": REQUIRED_STATUS_CARD,
        "required_runtime": REQUIRED_RUNTIME,
        "required_model_decision": REQUIRED_MODEL_DECISION,
        "required_memory": REQUIRED_MEMORY,
        "required_evidence": REQUIRED_EVIDENCE,
        "failures": failures,
    }
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n")
    print(
        "operator_readiness_contract_probe",
        output["verdict"],
        output["readiness"],
        "failures",
        len(failures),
        args.output_json,
    )
    for failure in failures:
        print("failure", failure)
    return 1 if args.fail_on_fail and failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
