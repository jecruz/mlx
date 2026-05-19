#!/usr/bin/env python3
"""Aggregate live M115-M119 product-readiness evidence."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


DEFAULT_ARTIFACTS = {
    "m115_live_resident_client": Path(
        "artifacts/m115-live-resident-client/dax-resident-client-m115-qwen-a3b.json"
    ),
    "m116_fast_path_overhead": Path(
        "artifacts/m116-fast-path-overhead/fast-path-overhead-gate-m116-qwen-a3b.json"
    ),
    "m117_live_prompt_transport_sweep": Path(
        "artifacts/m117-live-extended-prompt-sweep/live-prompt-transport-sweep-m117-qwen-a3b.json"
    ),
    "m118_live_lower_memory_bench": Path(
        "artifacts/m118-live-lower-memory/dax-low-memory-live-m118-qwen-a3b.json"
    ),
    "m118_live_lower_memory_gate": Path(
        "artifacts/m118-live-lower-memory/lower-memory-live-gate-m118-qwen-a3b.json"
    ),
    "m119_auto_selection_runtime_gate": Path(
        "artifacts/m119-auto-selection-runtime/auto-selection-runtime-gate-m119-qwen-a3b.json"
    ),
    "m119_live_auto_selected_bench": Path(
        "artifacts/m119-auto-selection-runtime/dax-auto-selected-m119-qwen-a3b.json"
    ),
}


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text())


def summarize_payload(payload: dict[str, Any]) -> dict[str, Any]:
    summary = {
        "type": payload.get("type"),
        "verdict": payload.get("verdict"),
        "readiness": payload.get("readiness"),
        "row_count": payload.get("row_count") or len(payload.get("rows") or []),
    }
    if "best_hit_speedup_vs_baseline" in payload:
        summary["best_hit_speedup_vs_baseline"] = payload["best_hit_speedup_vs_baseline"]
    if "hit_count" in payload:
        summary["hit_count"] = payload["hit_count"]
    if "metrics" in payload:
        summary["metrics"] = payload["metrics"]
    if "auto_selected_profile" in payload:
        summary["auto_selected_profile"] = payload["auto_selected_profile"]
    return {key: value for key, value in summary.items() if value is not None}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-json", type=Path, required=True)
    parser.add_argument("--tag", default="m120-qwen-a3b")
    parser.add_argument("--fail-on-fail", action="store_true")
    args = parser.parse_args()

    evidence = {}
    failures = []
    for name, path in DEFAULT_ARTIFACTS.items():
        if not path.exists():
            failures.append(f"{name}: missing {path}")
            continue
        payload = load_json(path)
        verdict = payload.get("verdict")
        if verdict != "PASS":
            failures.append(f"{name}: verdict={verdict!r}")
        evidence[name] = {
            "path": str(path),
            **summarize_payload(payload),
        }

    output = {
        "type": "live_product_readiness_bundle",
        "tag": args.tag,
        "verdict": "PASS" if not failures else "FAIL",
        "readiness": "live-validated" if not failures else "not-ready",
        "covered_milestones": ["M115", "M116", "M117", "M118", "M119", "M120"],
        "evidence": evidence,
        "failures": failures,
        "implemented": [
            "resident Dax client benchmark path",
            "resident fast-path overhead gate",
            "live prompt transport sweep",
            "live lower-memory runtime gate",
            "runtime profile auto-selection gate",
        ],
        "known_limitations": [
            "Qwen recurrent-state generic cache continuation still needs model-specific continuation work.",
            "Tensor parallelism is not part of the current single-process resident engine lane.",
        ],
        "next_recommended_milestones": [
            "turn the live readiness bundle into a one-command regression suite",
            "add server-side profile auto-selection from request metadata",
            "profile prompt processing kernels and JIT/warmup timing under Instruments",
        ],
    }
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n")
    print(
        "live_product_readiness_bundle",
        output["verdict"],
        output["readiness"],
        "evidence",
        len(evidence),
        "failures",
        len(failures),
        args.output_json,
        flush=True,
    )
    for failure in failures:
        print("failure", failure, flush=True)
    return 1 if args.fail_on_fail and failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
