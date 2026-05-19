#!/usr/bin/env python3
"""Build an operator-facing readiness bundle from current milestone evidence."""

from __future__ import annotations

import argparse
import json
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text())


def request_json(url: str, *, timeout: int = 30) -> dict[str, Any]:
    with urllib.request.urlopen(url, timeout=timeout) as resp:
        return json.loads(resp.read().decode())


def status_from_verdict(verdict: Any) -> str:
    return "PASS" if verdict == "PASS" else "FAIL"


def runtime_status(base_url: str | None) -> tuple[dict[str, Any] | None, list[str]]:
    if not base_url:
        return None, []
    try:
        ui_status = request_json(f"{base_url.rstrip('/')}/engine/ui")
    except (OSError, TimeoutError, urllib.error.URLError) as exc:
        return None, [f"runtime status unavailable: {exc}"]
    readiness = ui_status.get("readiness") or {}
    controls = ui_status.get("controls") or {}
    return (
        {
            "base_url": base_url.rstrip("/"),
            "ok": ui_status.get("ok"),
            "loaded": ui_status.get("loaded"),
            "model": ui_status.get("model"),
            "backend": ui_status.get("backend"),
            "engine_preset": ui_status.get("engine_preset"),
            "runtime_profile": ui_status.get("runtime_profile"),
            "strategy": readiness.get("strategy"),
            "gpu_ready": readiness.get("gpu_ready"),
            "warm": readiness.get("warm"),
            "can_generate": controls.get("can_generate"),
            "can_reload": controls.get("can_reload"),
            "can_unload": controls.get("can_unload"),
        },
        [],
    )


def write_markdown(path: Path, output: dict[str, Any]) -> None:
    lines = [
        "# M182 Operator Readiness Bundle",
        "",
        f"Verdict: `{output['verdict']}`",
        f"Readiness: `{output['readiness']}`",
        "",
        "## Status Card",
        "",
    ]
    for key, value in output["status_card"].items():
        lines.append(f"- {key}: `{value}`")
    runtime = output.get("runtime") or {}
    lines.extend(
        [
            "",
            "## Runtime",
            "",
            f"- model: `{runtime.get('model')}`",
            f"- backend: `{runtime.get('backend')}`",
            f"- preset: `{runtime.get('engine_preset')}`",
            f"- profile: `{runtime.get('runtime_profile')}`",
            f"- strategy: `{runtime.get('strategy')}`",
            f"- can generate: `{runtime.get('can_generate')}`",
            "",
            "## Model Decision",
            "",
            f"- active model: `{output['model_decision'].get('active_model')}`",
            f"- candidate model: `{output['model_decision'].get('candidate_model')}`",
            f"- swap decision: `{output['model_decision'].get('swap_decision')}`",
            f"- readiness: `{output['model_decision'].get('readiness')}`",
            f"- blockers: `{len(output['model_decision'].get('blockers') or [])}`",
            "",
            "## Memory",
            "",
            f"- source: `{output['memory'].get('source')}`",
            f"- max active GB: `{output['memory'].get('max_active_memory_gb')}`",
            f"- max peak GB: `{output['memory'].get('max_peak_memory_gb')}`",
            f"- health fallback GB: `{output['memory'].get('health_active_memory_gb')}`",
            "",
            "## Evidence",
            "",
        ]
    )
    for key, value in output["evidence"].items():
        lines.append(f"- {key}: `{value}`")
    warnings = output.get("warnings") or []
    failures = output.get("failures") or []
    lines.extend(["", "## Warnings", ""])
    lines.extend([f"- `{warning}`" for warning in warnings] or ["- none"])
    lines.extend(["", "## Failures", ""])
    lines.extend([f"- `{failure}`" for failure in failures] or ["- none"])
    lines.append("")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines))


def model_decision_from_workflow(model_swap: dict[str, Any]) -> dict[str, Any]:
    comparison_path = ((model_swap.get("artifacts") or {}).get("model_quality_comparison") or {}).get(
        "path"
    )
    current_model = None
    candidate_model = None
    current_label = None
    candidate_label = None
    if comparison_path:
        comparison_file = Path(comparison_path)
        if comparison_file.exists():
            comparison = load_json(comparison_file)
            models = comparison.get("models") or []
            if models:
                current = models[0]
                current_model = current.get("model")
                current_label = current.get("label")
            if len(models) > 1:
                candidate = models[1]
                candidate_model = candidate.get("model")
                candidate_label = candidate.get("label")
    return {
        "current_label": current_label,
        "active_model": current_model,
        "candidate_label": candidate_label,
        "candidate_model": candidate_model,
        "swap_decision": model_swap.get("swap_decision"),
        "readiness": model_swap.get("readiness"),
        "blockers": model_swap.get("blockers") or [],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8773")
    parser.add_argument("--suite-json", type=Path, required=True)
    parser.add_argument("--operator-quality-json", type=Path, required=True)
    parser.add_argument("--model-swap-workflow-json", type=Path, required=True)
    parser.add_argument("--lower-memory-json", type=Path, required=True)
    parser.add_argument("--live-model-swap-json", type=Path, required=True)
    parser.add_argument("--output-json", type=Path, required=True)
    parser.add_argument("--output-md", type=Path, required=True)
    parser.add_argument("--tag", default="m182-operator-readiness")
    parser.add_argument("--fail-on-fail", action="store_true")
    args = parser.parse_args()

    suite = load_json(args.suite_json)
    operator_quality = load_json(args.operator_quality_json)
    model_swap = load_json(args.model_swap_workflow_json)
    lower_memory = load_json(args.lower_memory_json)
    live_model_swap = load_json(args.live_model_swap_json)
    runtime, runtime_warnings = runtime_status(args.base_url)

    failures: list[str] = []
    warnings: list[str] = list(runtime_warnings)
    if suite.get("verdict") != "PASS":
        failures.append(f"live suite verdict is {suite.get('verdict')!r}")
    if operator_quality.get("verdict") != "PASS":
        failures.append(f"operator quality verdict is {operator_quality.get('verdict')!r}")
    if lower_memory.get("verdict") != "PASS":
        failures.append(f"lower-memory verdict is {lower_memory.get('verdict')!r}")
    if live_model_swap.get("verdict") != "PASS":
        failures.append(f"live model swap verdict is {live_model_swap.get('verdict')!r}")
    if model_swap.get("verdict") != "PASS":
        failures.append(f"model swap workflow verdict is {model_swap.get('verdict')!r}")
    if model_swap.get("swap_decision") != "ACCEPT":
        warnings.append(f"model swap decision is {model_swap.get('swap_decision')}")
    if (lower_memory.get("metrics") or {}).get("memory_source") != "request_metrics":
        failures.append("lower-memory gate did not use request_metrics")
    if runtime and not runtime.get("can_generate"):
        failures.append("live runtime cannot generate")
    if runtime and not runtime.get("gpu_ready"):
        failures.append("live runtime GPU is not ready")

    status_card = {
        "runtime": "PASS" if runtime and runtime.get("can_generate") else "WARN",
        "quality": status_from_verdict(operator_quality.get("verdict")),
        "live_suite": status_from_verdict(suite.get("verdict")),
        "lower_memory": status_from_verdict(lower_memory.get("verdict")),
        "memory_source": "PASS"
        if (lower_memory.get("metrics") or {}).get("memory_source") == "request_metrics"
        else "FAIL",
        "live_model_swap": status_from_verdict(live_model_swap.get("verdict")),
        "candidate_swap": "PASS" if model_swap.get("swap_decision") == "ACCEPT" else "WARN",
    }
    if failures:
        verdict = "FAIL"
        readiness = "operator-readiness-blocked"
    else:
        verdict = "PASS"
        readiness = "operator-readiness-ready"

    lower_metrics = lower_memory.get("metrics") or {}
    model_decision = model_decision_from_workflow(model_swap)
    if live_model_swap.get("restore_model"):
        model_decision["active_model"] = live_model_swap.get("restore_model")
    output = {
        "type": "operator_readiness_bundle",
        "tag": args.tag,
        "verdict": verdict,
        "readiness": readiness,
        "status_card": status_card,
        "runtime": runtime,
        "model_decision": model_decision,
        "memory": {
            "source": lower_metrics.get("memory_source"),
            "max_active_memory_gb": lower_metrics.get("max_active_memory_gb"),
            "max_peak_memory_gb": lower_metrics.get("max_peak_memory_gb"),
            "health_active_memory_gb": lower_metrics.get("health_active_memory_gb"),
        },
        "evidence": {
            "suite_json": str(args.suite_json),
            "operator_quality_json": str(args.operator_quality_json),
            "model_swap_workflow_json": str(args.model_swap_workflow_json),
            "lower_memory_json": str(args.lower_memory_json),
            "live_model_swap_json": str(args.live_model_swap_json),
        },
        "warnings": warnings,
        "failures": failures,
    }
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n")
    write_markdown(args.output_md, output)
    print(
        "operator_readiness_bundle",
        verdict,
        readiness,
        "warnings",
        len(warnings),
        "failures",
        len(failures),
        args.output_json,
    )
    if args.fail_on_fail and failures:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
