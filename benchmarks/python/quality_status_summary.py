#!/usr/bin/env python3
"""Create a compact operator-facing quality status summary."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


QUALITY_ARTIFACTS = [
    "quality_golden_set",
    "quality_deterministic",
    "quality_cache",
    "quality_streaming",
    "quality_loop",
    "quality_long_context",
    "quality_cross_engine",
    "quality_checkpoint",
]


def load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text())


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--suite-json", type=Path, required=True)
    parser.add_argument("--output-json", type=Path, required=True)
    parser.add_argument("--tag", default="m168-qwen-a3b")
    parser.add_argument("--fail-on-fail", action="store_true")
    args = parser.parse_args()

    suite = load(args.suite_json)
    artifacts = suite.get("artifacts", {})
    rows = []
    failures = []
    for name in QUALITY_ARTIFACTS:
        entry = artifacts.get(name)
        if not entry:
            failures.append(f"missing {name}")
            rows.append({"name": name, "verdict": "MISSING"})
            continue
        verdict = entry.get("verdict")
        rows.append(
            {
                "name": name,
                "type": entry.get("type"),
                "path": entry.get("path"),
                "verdict": verdict,
                "row_count": entry.get("row_count"),
            }
        )
        if verdict != "PASS":
            failures.append(f"{name}: {verdict!r}")

    output = {
        "type": "quality_status_summary",
        "tag": args.tag,
        "suite": str(args.suite_json),
        "verdict": "PASS" if not failures else "FAIL",
        "readiness": "quality-status-ready" if not failures else "not-ready",
        "quality_gate_count": len(rows),
        "rows": rows,
        "failures": failures,
        "operator_summary": {
            "quality": "PASS" if not failures else "FAIL",
            "performance": suite.get("verdict"),
            "artifact_count": len(artifacts),
            "suite_failures": len(suite.get("failures", [])),
        },
    }
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n")
    print("quality_status_summary", output["verdict"], "gates", len(rows), "failures", len(failures), args.output_json)
    if args.fail_on_fail and output["verdict"] != "PASS":
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
