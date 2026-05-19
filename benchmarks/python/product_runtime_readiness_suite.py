#!/usr/bin/env python3
"""Aggregate M109-M113 product runtime readiness gates."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


DEFAULT_ARTIFACTS = {
    "m109_resident_client": Path(
        "artifacts/m109-resident-dax-client/resident-dax-client-m109-qwen-a3b.json"
    ),
    "m110_overhead_gate": Path(
        "artifacts/m110-overhead-gate/operator-overhead-gate-m110-current-baseline.json"
    ),
    "m111_extended_prompt_sweep": Path(
        "artifacts/m111-extended-prompt-sweep/extended-prompt-sweep-matrix-m111-qwen-a3b.json"
    ),
    "m112_lower_memory_gate": Path(
        "artifacts/m112-lower-memory-gate/lower-memory-runtime-gate-m112-qwen-a3b.json"
    ),
    "m113_auto_selection_integration": Path(
        "artifacts/m113-auto-selection-integration/auto-selection-integration-gate-m113-qwen-a3b.json"
    ),
}


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text())


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-json", type=Path, required=True)
    parser.add_argument("--tag", default="m114-qwen-a3b")
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
            "type": payload.get("type"),
            "verdict": verdict,
        }

    output = {
        "type": "product_runtime_readiness_suite",
        "tag": args.tag,
        "verdict": "PASS" if not failures else "FAIL",
        "readiness": "ready-for-live-resident-client-validation" if not failures else "not-ready",
        "failures": failures,
        "evidence": evidence,
        "covered_milestones": ["M109", "M110", "M111", "M112", "M113"],
        "next_live_commands": [
            (
                "python3 benchmarks/python/dax_repeated_context_bench.py "
                "--client-mode resident --dax-profile agent-workspace-first-hit "
                "--output-jsonl artifacts/live-resident-client/dax-resident.jsonl "
                "--output-json artifacts/live-resident-client/dax-resident.json"
            ),
            (
                "python3 benchmarks/python/dax_operator_overhead_gate.py "
                "artifacts/live-resident-client/dax-resident.jsonl "
                "--max-mean-overhead-ms 500 --fail-on-fail"
            ),
        ],
        "known_limitations": [
            "M110 current artifact gates the CLI baseline at <=2000 ms; the <=500 ms target requires a live resident-client run.",
            "The resident server was not running during M109-M114, so live timing is the next validation step.",
        ],
    }
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n")
    print(
        "product_runtime_readiness_suite",
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
