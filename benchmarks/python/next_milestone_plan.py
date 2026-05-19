#!/usr/bin/env python3
"""Generate the next milestone plan after the current batch."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


NEXT = [
    {
        "milestone": "M202",
        "title": "Cache lookup fast-path implementation",
        "acceptance": "mature reusable-turn latency improves while quality threshold stays PASS",
    },
    {
        "milestone": "M203",
        "title": "Tokenized prompt reuse probe",
        "acceptance": "identical repeated workspace prompts reduce prompt overhead without route bleed",
    },
    {
        "milestone": "M204",
        "title": "Async cache completion wait sweep",
        "acceptance": "conversion-turn latency improves without queue wait regression",
    },
    {
        "milestone": "M205",
        "title": "Response metrics trim experiment",
        "acceptance": "hot response overhead drops and operator debug mode preserves full metrics",
    },
    {
        "milestone": "M206",
        "title": "Live performance suite rerun",
        "acceptance": "M180-equivalent suite stays PASS with quality threshold PASS",
    },
    {
        "milestone": "M207",
        "title": "Prowl/UI readiness endpoint smoke",
        "acceptance": "Prowl or UI-side probe consumes /engine/operator-readiness",
    },
    {
        "milestone": "M208",
        "title": "Candidate model registry refresh",
        "acceptance": "registry includes any new smaller/lower-memory candidates",
    },
    {
        "milestone": "M209",
        "title": "Performance report refresh",
        "acceptance": "new report shows latency delta versus M194 baseline",
    },
]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--performance-report-json", type=Path, required=True)
    parser.add_argument("--output-json", type=Path, required=True)
    parser.add_argument("--tag", default="m200-next-milestones")
    args = parser.parse_args()

    report = json.loads(args.performance_report_json.read_text())
    output = {
        "type": "next_milestone_plan",
        "tag": args.tag,
        "verdict": "PASS" if report.get("verdict") == "PASS" else "FAIL",
        "readiness": "next-milestones-planned" if report.get("verdict") == "PASS" else "not-ready",
        "performance_baseline": report.get("current"),
        "performance_target": report.get("target"),
        "next_milestones": NEXT,
        "failures": [] if report.get("verdict") == "PASS" else ["performance report is not PASS"],
    }
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n")
    print(
        "next_milestone_plan",
        output["verdict"],
        output["readiness"],
        "milestones",
        len(NEXT),
        args.output_json,
    )
    return 0 if output["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
