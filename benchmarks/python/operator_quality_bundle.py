#!/usr/bin/env python3
"""Build a compact operator/TUI quality bundle from live and artifact evidence."""

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


def mean_model_ms(model: dict[str, Any]) -> float | None:
    values = [
        artifact.get("mean_service_request_ms")
        for artifact in (model.get("artifacts") or {}).values()
        if isinstance(artifact.get("mean_service_request_ms"), int | float)
    ]
    return round(sum(values) / len(values), 3) if values else None


def status_card(ui_status: dict[str, Any], quality: dict[str, Any], comparison: dict[str, Any]) -> dict[str, Any]:
    readiness = ui_status.get("readiness") or {}
    controls = ui_status.get("controls") or {}
    return {
        "engine": "PASS"
        if ui_status.get("ok") and ui_status.get("loaded") and controls.get("can_generate")
        else "FAIL",
        "gpu": "PASS" if readiness.get("gpu_ready") else "FAIL",
        "warmup": "PASS" if readiness.get("warm") else "WARN",
        "quality": quality.get("verdict"),
        "model_comparison": comparison.get("verdict"),
    }


def model_rows(live_model: str | None, comparison: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for model in comparison.get("models") or []:
        rows.append(
            {
                "label": model.get("label"),
                "model": model.get("model"),
                "active": bool(live_model and model.get("model") == live_model),
                "verdict": model.get("verdict"),
                "failure_count": len(model.get("failures") or []),
                "mean_quality_gate_ms": mean_model_ms(model),
            }
        )
    return rows


def speed_warning(rows: list[dict[str, Any]]) -> str | None:
    active = next((row for row in rows if row["active"]), None)
    if not active or active["mean_quality_gate_ms"] is None:
        return None
    slower = [
        row
        for row in rows
        if not row["active"]
        and row.get("verdict") == "PASS"
        and row.get("mean_quality_gate_ms") is not None
        and row["mean_quality_gate_ms"] > active["mean_quality_gate_ms"]
    ]
    if not slower:
        return None
    labels = ", ".join(str(row["label"]) for row in slower)
    return f"quality-compatible alternate model is slower than active model: {labels}"


def write_markdown(path: Path, output: dict[str, Any]) -> None:
    lines = [
        "# M171 Operator Quality Bundle",
        "",
        f"Verdict: `{output['verdict']}`",
        "",
        "## Status",
        "",
    ]
    for key, value in output["status_card"].items():
        lines.append(f"- {key}: `{value}`")
    lines.extend(["", "## Active Runtime", ""])
    runtime = output["runtime"]
    lines.extend(
        [
            f"- model: `{runtime.get('model')}`",
            f"- profile: `{runtime.get('runtime_profile')}`",
            f"- preset: `{runtime.get('engine_preset')}`",
            f"- cache strategy: `{runtime.get('cache_strategy')}`",
            f"- can generate: `{runtime.get('can_generate')}`",
            "",
            "## Model Comparison",
            "",
            "| Label | Active | Verdict | Mean Quality Gate ms | Failures |",
            "| --- | --- | --- | ---: | ---: |",
        ]
    )
    for row in output["models"]:
        lines.append(
            f"| `{row['label']}` | `{row['active']}` | `{row['verdict']}` | "
            f"{row['mean_quality_gate_ms'] if row['mean_quality_gate_ms'] is not None else ''} | "
            f"{row['failure_count']} |"
        )
    warning_lines = [f"- `{warning}`" for warning in output["warnings"]] or ["- none"]
    failure_lines = [f"- `{failure}`" for failure in output["failures"]] or ["- none"]
    lines.extend(["", "## Warnings", "", *warning_lines, "", "## Failures", "", *failure_lines, ""])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8773")
    parser.add_argument("--quality-summary-json", type=Path, required=True)
    parser.add_argument("--model-comparison-json", type=Path, required=True)
    parser.add_argument("--output-json", type=Path, required=True)
    parser.add_argument("--output-md", type=Path, required=True)
    parser.add_argument("--tag", default="m171-operator-quality-bundle")
    parser.add_argument("--fail-on-fail", action="store_true")
    args = parser.parse_args()

    base_url = args.base_url.rstrip("/")
    ui_status = request_json(f"{base_url}/engine/ui")
    quality = load_json(args.quality_summary_json)
    comparison = load_json(args.model_comparison_json)
    cards = status_card(ui_status, quality, comparison)
    rows = model_rows(ui_status.get("model"), comparison)
    failures = []
    if cards["engine"] != "PASS":
        failures.append(f"engine status is {cards['engine']}")
    if cards["gpu"] != "PASS":
        failures.append(f"gpu status is {cards['gpu']}")
    if cards["quality"] != "PASS":
        failures.append(f"quality summary verdict is {cards['quality']!r}")
    if cards["model_comparison"] != "PASS":
        failures.append(f"model comparison verdict is {cards['model_comparison']!r}")
    active_rows = [row for row in rows if row["active"]]
    if not active_rows:
        failures.append("live model is not present in model comparison rows")
    warnings = []
    if cards["warmup"] != "PASS":
        warnings.append("warmup is not complete")
    speed_note = speed_warning(rows)
    if speed_note:
        warnings.append(speed_note)

    readiness = "operator-quality-ready" if not failures else "operator-quality-blocked"
    output = {
        "type": "operator_quality_bundle",
        "tag": args.tag,
        "verdict": "PASS" if not failures else "FAIL",
        "readiness": readiness,
        "base_url": base_url,
        "runtime": {
            "model": ui_status.get("model"),
            "runtime_profile": ui_status.get("runtime_profile"),
            "engine_preset": ui_status.get("engine_preset"),
            "cache_strategy": (ui_status.get("readiness") or {}).get("strategy"),
            "can_generate": (ui_status.get("controls") or {}).get("can_generate"),
        },
        "status_card": cards,
        "quality_summary": {
            "path": str(args.quality_summary_json),
            "verdict": quality.get("verdict"),
            "quality_gate_count": quality.get("quality_gate_count"),
            "readiness": quality.get("readiness"),
        },
        "model_comparison": {
            "path": str(args.model_comparison_json),
            "verdict": comparison.get("verdict"),
            "readiness": comparison.get("readiness"),
        },
        "models": rows,
        "warnings": warnings,
        "failures": failures,
    }
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n")
    write_markdown(args.output_md, output)
    print("operator_quality_bundle", output["verdict"], readiness, "warnings", len(warnings), "failures", len(failures), args.output_json)
    if args.fail_on_fail and failures:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
