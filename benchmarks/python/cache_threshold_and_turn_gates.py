#!/usr/bin/env python3
"""Build M145/M146 gates from live repeated-context and admission artifacts."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text())


def write(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repeated", type=Path, required=True)
    parser.add_argument("--admission", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--tag", default="m145-m146-qwen-a3b")
    parser.add_argument("--fail-on-fail", action="store_true")
    args = parser.parse_args()
    repeated = load(args.repeated)
    admission = load(args.admission)

    rows = admission.get("rows") or []
    repeated_failures = []
    conversion = repeated.get("rows", [None, None])[1] if len(repeated.get("rows", [])) > 1 else None
    mature_hit = repeated.get("best_hit") or {}
    baseline = repeated.get("baseline") or {}
    if repeated.get("verdict") != "PASS":
        repeated_failures.append("repeated-context report did not pass")
    if not conversion or conversion.get("actual_prefill_tokens", 10**9) > 32:
        repeated_failures.append("conversion turn did not reduce prefill to <=32")
    if mature_hit.get("actual_prefill_tokens", 10**9) > 32:
        repeated_failures.append("mature hit prefill did not stay <=32")
    if (repeated.get("best_hit_speedup_vs_baseline") or 0) < 2.0:
        repeated_failures.append("mature hit speedup below 2x")
    first_turn = {
        "type": "first_reusable_turn_reduction_probe",
        "tag": args.tag,
        "verdict": "PASS" if not repeated_failures else "FAIL",
        "baseline_service_request_ms": baseline.get("service_request_ms"),
        "conversion_service_request_ms": conversion.get("service_request_ms") if conversion else None,
        "mature_hit_service_request_ms": mature_hit.get("service_request_ms"),
        "baseline_actual_prefill_tokens": baseline.get("actual_prefill_tokens"),
        "conversion_actual_prefill_tokens": conversion.get("actual_prefill_tokens") if conversion else None,
        "mature_hit_actual_prefill_tokens": mature_hit.get("actual_prefill_tokens"),
        "best_hit_speedup_vs_baseline": repeated.get("best_hit_speedup_vs_baseline"),
        "failures": repeated_failures,
    }

    threshold_failures = []
    if admission.get("verdict") != "PASS":
        threshold_failures.append("admission probe did not pass")
    for row in rows:
        if row.get("actual_prefill_tokens", 0) < 128:
            threshold_failures.append(f"{row.get('case')}: prompt below admission threshold")
        if row.get("request_runtime_profile_source") != "request_metadata":
            threshold_failures.append(f"{row.get('case')}: missing request metadata source")
    modes = sorted({row.get("cache_population_mode") for row in rows})
    if "async" not in modes or "request" not in modes or "sync" not in modes:
        threshold_failures.append(f"expected async, request, and sync modes, got {modes}")
    threshold = {
        "type": "cache_admission_threshold_tuning_gate",
        "tag": args.tag,
        "verdict": "PASS" if not threshold_failures else "FAIL",
        "observed_population_modes": modes,
        "min_actual_prefill_tokens": min((row.get("actual_prefill_tokens") or 0) for row in rows),
        "rows": rows,
        "failures": threshold_failures,
    }

    paths = {
        "m145_first_reusable_turn_reduction": args.output_dir / f"m145_first_reusable_turn_reduction-{args.tag}.json",
        "m146_cache_admission_thresholds": args.output_dir / f"m146_cache_admission_thresholds-{args.tag}.json",
    }
    write(paths["m145_first_reusable_turn_reduction"], first_turn)
    write(paths["m146_cache_admission_thresholds"], threshold)
    failures = []
    if first_turn["verdict"] != "PASS":
        failures.append("m145 failed")
    if threshold["verdict"] != "PASS":
        failures.append("m146 failed")
    manifest = {
        "type": "cache_threshold_and_turn_gates",
        "tag": args.tag,
        "verdict": "PASS" if not failures else "FAIL",
        "artifacts": {name: str(path) for name, path in paths.items()},
        "failures": failures,
    }
    write(args.output_dir / f"cache-threshold-and-turn-gates-{args.tag}.json", manifest)
    print("cache_threshold_and_turn_gates", manifest["verdict"], "failures", len(failures), args.output_dir)
    if args.fail_on_fail and manifest["verdict"] != "PASS":
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
