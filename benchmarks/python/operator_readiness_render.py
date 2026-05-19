#!/usr/bin/env python3
"""Render an operator readiness bundle for terminal/UI consumers."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


ORDERED_STATUS_KEYS = [
    "runtime",
    "quality",
    "live_suite",
    "lower_memory",
    "memory_source",
    "live_model_swap",
    "candidate_swap",
]


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text())


def short_model(path: Any) -> str:
    if not path:
        return "unknown"
    return str(path).rstrip("/").rsplit("/", 1)[-1]


def status_line(status_card: dict[str, Any]) -> str:
    parts = []
    for key in ORDERED_STATUS_KEYS:
        value = status_card.get(key, "MISSING")
        parts.append(f"{key}={value}")
    return " ".join(parts)


def build_summary(bundle: dict[str, Any]) -> dict[str, Any]:
    runtime = bundle.get("runtime") or {}
    model_decision = bundle.get("model_decision") or {}
    memory = bundle.get("memory") or {}
    status_card = bundle.get("status_card") or {}
    warnings = bundle.get("warnings") or []
    failures = bundle.get("failures") or []
    return {
        "type": "operator_readiness_render",
        "source_type": bundle.get("type"),
        "tag": bundle.get("tag"),
        "verdict": bundle.get("verdict"),
        "readiness": bundle.get("readiness"),
        "status_card": status_card,
        "active_model": model_decision.get("active_model") or runtime.get("model"),
        "active_model_name": short_model(model_decision.get("active_model") or runtime.get("model")),
        "candidate_model": model_decision.get("candidate_model"),
        "candidate_model_name": short_model(model_decision.get("candidate_model")),
        "candidate_label": model_decision.get("candidate_label"),
        "swap_decision": model_decision.get("swap_decision"),
        "swap_readiness": model_decision.get("readiness"),
        "swap_blockers": model_decision.get("blockers") or [],
        "memory_source": memory.get("source"),
        "max_active_memory_gb": memory.get("max_active_memory_gb"),
        "max_peak_memory_gb": memory.get("max_peak_memory_gb"),
        "runtime_profile": runtime.get("runtime_profile"),
        "engine_preset": runtime.get("engine_preset"),
        "strategy": runtime.get("strategy"),
        "warnings": warnings,
        "failures": failures,
        "display": {
            "title": f"MLX Operator Readiness: {bundle.get('verdict')}",
            "subtitle": f"{bundle.get('readiness')} | {short_model(model_decision.get('active_model') or runtime.get('model'))}",
            "status_line": status_line(status_card),
            "memory_line": (
                f"memory={memory.get('source')} "
                f"active={memory.get('max_active_memory_gb')}GB "
                f"peak={memory.get('max_peak_memory_gb')}GB"
            ),
            "model_line": (
                f"active={short_model(model_decision.get('active_model') or runtime.get('model'))} "
                f"candidate={short_model(model_decision.get('candidate_model'))} "
                f"swap={model_decision.get('swap_decision')}"
            ),
            "runtime_line": (
                f"profile={runtime.get('runtime_profile')} "
                f"preset={runtime.get('engine_preset')} "
                f"strategy={runtime.get('strategy')}"
            ),
        },
    }


def render_text(summary: dict[str, Any]) -> str:
    lines = [
        summary["display"]["title"],
        summary["display"]["subtitle"],
        summary["display"]["status_line"],
        summary["display"]["runtime_line"],
        summary["display"]["memory_line"],
        summary["display"]["model_line"],
    ]
    blockers = summary.get("swap_blockers") or []
    warnings = summary.get("warnings") or []
    failures = summary.get("failures") or []
    if blockers:
        lines.append("swap_blockers:")
        lines.extend(f"- {blocker}" for blocker in blockers)
    if warnings:
        lines.append("warnings:")
        lines.extend(f"- {warning}" for warning in warnings)
    if failures:
        lines.append("failures:")
        lines.extend(f"- {failure}" for failure in failures)
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bundle-json", type=Path, required=True)
    parser.add_argument("--output-json", type=Path)
    parser.add_argument("--output-text", type=Path)
    parser.add_argument("--format", choices=["text", "json"], default="text")
    parser.add_argument("--fail-on-fail", action="store_true")
    args = parser.parse_args()

    bundle = load_json(args.bundle_json)
    summary = build_summary(bundle)
    text = render_text(summary)
    if args.output_json:
        args.output_json.parent.mkdir(parents=True, exist_ok=True)
        args.output_json.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    if args.output_text:
        args.output_text.parent.mkdir(parents=True, exist_ok=True)
        args.output_text.write_text(text)
    if args.format == "json":
        print(json.dumps(summary, indent=2, sort_keys=True))
    else:
        print(text, end="")
    if args.fail_on_fail and summary.get("verdict") != "PASS":
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
