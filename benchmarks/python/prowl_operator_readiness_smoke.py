#!/usr/bin/env python3
"""Smoke a Prowl/UI-style consumer of live operator readiness."""

from __future__ import annotations

import argparse
import json
import urllib.request
from pathlib import Path
from typing import Any


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text())


def request_json(url: str, *, timeout: int = 120) -> dict[str, Any]:
    with urllib.request.urlopen(url, timeout=timeout) as resp:
        return json.loads(resp.read().decode())


def short_model(path: Any) -> str:
    if not path:
        return "unknown"
    return str(path).rstrip("/").rsplit("/", 1)[-1]


def positive_number(value: Any) -> bool:
    return isinstance(value, int | float) and value > 0


def build_prowl_card(
    *,
    readiness: dict[str, Any],
    ui_status: dict[str, Any],
    quality: dict[str, Any],
    live_model_swap: dict[str, Any],
    candidate_workflow: dict[str, Any],
) -> dict[str, Any]:
    runtime = readiness.get("runtime") or {}
    memory = readiness.get("memory") or {}
    status_card = readiness.get("status_card") or {}
    ui_readiness = ui_status.get("readiness") or {}
    ui_controls = ui_status.get("controls") or {}
    return {
        "title": f"MLX Engine {readiness.get('verdict')}",
        "subtitle": short_model(runtime.get("model") or ui_status.get("model")),
        "badges": {
            "runtime": status_card.get("runtime"),
            "gpu": status_card.get("gpu"),
            "warm": status_card.get("warm"),
            "can_generate": status_card.get("can_generate"),
            "quality": quality.get("verdict"),
            "live_model_swap": live_model_swap.get("verdict"),
            "candidate_swap_decision": candidate_workflow.get("swap_decision"),
        },
        "details": {
            "model": runtime.get("model") or ui_status.get("model"),
            "backend": runtime.get("backend") or ui_status.get("backend"),
            "runtime_profile": runtime.get("runtime_profile") or ui_status.get("runtime_profile"),
            "engine_preset": runtime.get("engine_preset") or ui_status.get("engine_preset"),
            "strategy": runtime.get("strategy") or ui_readiness.get("strategy"),
            "can_reload": runtime.get("can_reload") or ui_controls.get("can_reload"),
            "can_unload": runtime.get("can_unload") or ui_controls.get("can_unload"),
        },
        "memory": {
            "source": memory.get("source"),
            "active_memory_bytes": memory.get("active_memory_bytes"),
            "cache_memory_bytes": memory.get("cache_memory_bytes"),
            "peak_memory_bytes": memory.get("peak_memory_bytes"),
        },
        "quality": {
            "source": quality.get("type"),
            "verdict": quality.get("verdict"),
            "readiness": quality.get("readiness"),
            "failures": quality.get("failures") or [],
        },
        "model_swap": {
            "live_source": live_model_swap.get("type"),
            "live_verdict": live_model_swap.get("verdict"),
            "live_readiness": live_model_swap.get("readiness"),
            "restore_model": live_model_swap.get("restore_model"),
            "candidate_source": candidate_workflow.get("type"),
            "candidate_verdict": candidate_workflow.get("verdict"),
            "candidate_readiness": candidate_workflow.get("readiness"),
            "candidate_decision": candidate_workflow.get("swap_decision"),
            "candidate_blockers": candidate_workflow.get("blockers") or [],
        },
        "warnings": readiness.get("warnings") or [],
        "failures": readiness.get("failures") or [],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8773")
    parser.add_argument("--quality-json", type=Path, required=True)
    parser.add_argument("--live-model-swap-json", type=Path, required=True)
    parser.add_argument("--candidate-workflow-json", type=Path, required=True)
    parser.add_argument("--output-json", type=Path, required=True)
    parser.add_argument("--tag", default="m207-prowl-operator-readiness")
    parser.add_argument("--fail-on-fail", action="store_true")
    args = parser.parse_args()

    base_url = args.base_url.rstrip("/")
    readiness = request_json(f"{base_url}/engine/operator-readiness")
    ui_status = request_json(f"{base_url}/engine/ui")
    quality = load_json(args.quality_json)
    live_model_swap = load_json(args.live_model_swap_json)
    candidate_workflow = load_json(args.candidate_workflow_json)
    card = build_prowl_card(
        readiness=readiness,
        ui_status=ui_status,
        quality=quality,
        live_model_swap=live_model_swap,
        candidate_workflow=candidate_workflow,
    )

    failures: list[str] = []
    if readiness.get("verdict") != "PASS":
        failures.append(f"operator readiness verdict is {readiness.get('verdict')!r}")
    if readiness.get("readiness") != "operator-live-ready":
        failures.append(f"operator readiness state is {readiness.get('readiness')!r}")
    if ui_status.get("loaded") is not True:
        failures.append("ui status does not report a loaded model")
    if quality.get("verdict") != "PASS":
        failures.append(f"quality verdict is {quality.get('verdict')!r}")
    if live_model_swap.get("verdict") != "PASS":
        failures.append(f"live model-swap verdict is {live_model_swap.get('verdict')!r}")
    if not candidate_workflow.get("swap_decision"):
        failures.append("candidate model-swap decision is missing")

    if card["badges"].get("quality") != "PASS":
        failures.append("Prowl card lost quality PASS badge")
    if card["badges"].get("live_model_swap") != "PASS":
        failures.append("Prowl card lost live model-swap PASS badge")
    if not card["badges"].get("candidate_swap_decision"):
        failures.append("Prowl card lost candidate model-swap decision")
    if card["memory"].get("source") != "engine_ui":
        failures.append(f"Prowl card memory source is {card['memory'].get('source')!r}")
    for key in ("active_memory_bytes", "peak_memory_bytes"):
        if not positive_number(card["memory"].get(key)):
            failures.append(f"Prowl card memory.{key} is not positive")
    for key in ("runtime", "gpu", "warm", "can_generate"):
        if key not in card["badges"] or card["badges"].get(key) in (None, ""):
            failures.append(f"Prowl card badge {key} is missing")
    for key in ("model", "runtime_profile", "engine_preset", "strategy"):
        if not card["details"].get(key):
            failures.append(f"Prowl card detail {key} is missing")

    output = {
        "type": "prowl_operator_readiness_smoke",
        "tag": args.tag,
        "base_url": base_url,
        "verdict": "PASS" if not failures else "FAIL",
        "readiness": "prowl-operator-readiness-ready" if not failures else "not-ready",
        "consumer": "prowl-ui-card",
        "card": card,
        "evidence": {
            "operator_readiness_endpoint": "/engine/operator-readiness",
            "engine_ui_endpoint": "/engine/ui",
            "quality_json": str(args.quality_json),
            "live_model_swap_json": str(args.live_model_swap_json),
            "candidate_workflow_json": str(args.candidate_workflow_json),
        },
        "failures": failures,
    }
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n")
    print(
        "prowl_operator_readiness_smoke",
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
