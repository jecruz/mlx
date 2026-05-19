#!/usr/bin/env python3
"""Create the next prompt-processing optimization matrix."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


TACTICS = [
    {
        "id": "cache_lookup_fast_path",
        "target": "reduce mature reusable-turn service_request_ms",
        "hypothesis": "avoid redundant cache admission and prefix matching work on exact mature hits",
        "acceptance": "mature hit latency trends toward 175ms with quality threshold PASS",
        "risk": "cache hit correctness or request-scope bleed",
    },
    {
        "id": "tokenized_prompt_reuse",
        "target": "reduce prompt tokenization and hash overhead",
        "hypothesis": "reuse tokenized prompt metadata for identical repeated workspace prompts",
        "acceptance": "actual_prefill_tokens unchanged, service_request_ms reduced, deterministic quality PASS",
        "risk": "incorrect reuse across different request metadata",
    },
    {
        "id": "async_cache_completion_wait",
        "target": "reduce conversion-turn latency",
        "hypothesis": "short bounded wait for completed async prefix builds improves second-turn conversion",
        "acceptance": "conversion service_request_ms decreases without queue wait regression",
        "risk": "foreground request stalls under concurrent load",
    },
    {
        "id": "response_metrics_trim",
        "target": "reduce operator/HTTP overhead",
        "hypothesis": "summarize heavy metrics for hot responses while preserving detailed debug mode",
        "acceptance": "fast-path overhead gate PASS and UI contract still PASS",
        "risk": "operator loses required diagnostics",
    },
]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--performance-report-json", type=Path, required=True)
    parser.add_argument("--output-json", type=Path, required=True)
    parser.add_argument("--tag", default="m195-prompt-processing-optimization-matrix")
    args = parser.parse_args()

    report = json.loads(args.performance_report_json.read_text())
    output = {
        "type": "prompt_processing_optimization_matrix",
        "tag": args.tag,
        "verdict": "PASS" if report.get("verdict") == "PASS" else "FAIL",
        "readiness": "prompt-processing-optimization-matrix-ready"
        if report.get("verdict") == "PASS"
        else "not-ready",
        "performance_report": str(args.performance_report_json),
        "current": report.get("current"),
        "target": report.get("target"),
        "tactics": TACTICS,
        "recommended_first": "cache_lookup_fast_path",
        "failures": [] if report.get("verdict") == "PASS" else ["performance report is not PASS"],
    }
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n")
    print(
        "prompt_processing_optimization_matrix",
        output["verdict"],
        output["readiness"],
        "tactics",
        len(TACTICS),
        args.output_json,
    )
    return 0 if output["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
