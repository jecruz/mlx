#!/usr/bin/env python3
"""Audit milestone artifacts for a completed milestone batch."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def load_json(path: Path) -> dict:
    return json.loads(path.read_text())


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--milestone", action="append", required=True, help="Name=artifact.json")
    parser.add_argument("--output-json", type=Path, required=True)
    parser.add_argument("--tag", default="m193-completion-audit")
    parser.add_argument("--fail-on-fail", action="store_true")
    args = parser.parse_args()

    rows = []
    failures = []
    for raw in args.milestone:
        if "=" not in raw:
            failures.append(f"invalid milestone argument {raw!r}")
            continue
        name, path_raw = raw.split("=", 1)
        path = Path(path_raw)
        if not path.exists():
            failures.append(f"{name}: artifact missing at {path}")
            rows.append({"milestone": name, "path": str(path), "exists": False})
            continue
        payload = load_json(path)
        verdict = payload.get("verdict")
        readiness = payload.get("readiness")
        row_failures = payload.get("failures") or []
        passed = verdict == "PASS" and not row_failures
        if not passed:
            failures.append(f"{name}: verdict={verdict!r} failures={len(row_failures)}")
        rows.append(
            {
                "milestone": name,
                "path": str(path),
                "exists": True,
                "type": payload.get("type"),
                "verdict": verdict,
                "readiness": readiness,
                "failure_count": len(row_failures),
                "passed": passed,
            }
        )

    output = {
        "type": "milestone_completion_audit",
        "tag": args.tag,
        "verdict": "PASS" if not failures else "FAIL",
        "readiness": "milestone-batch-complete" if not failures else "not-ready",
        "audited_count": len(rows),
        "rows": rows,
        "failures": failures,
    }
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n")
    print(
        "milestone_completion_audit",
        output["verdict"],
        output["readiness"],
        "audited",
        len(rows),
        "failures",
        len(failures),
        args.output_json,
    )
    for failure in failures:
        print("failure", failure)
    return 1 if args.fail_on_fail and failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
