#!/usr/bin/env python3
"""Generate a lower-memory Mac runtime strategy from validated MLX evidence."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text())


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--low-memory-summary",
        type=Path,
        default=Path(
            "artifacts/m98-direct-low-memory-profile/"
            "dax-product-first-hit-summary-m98-qwen-a3b-low-memory-direct.json"
        ),
    )
    parser.add_argument(
        "--auto-selection",
        type=Path,
        default=Path("artifacts/m106-profile-auto-selection/profile-auto-selection-m106-qwen-a3b.json"),
    )
    parser.add_argument("--output-json", type=Path, required=True)
    parser.add_argument("--tag", default="m107-qwen-a3b")
    parser.add_argument("--fail-on-fail", action="store_true")
    args = parser.parse_args()

    low_memory = load_json(args.low_memory_summary)
    auto_selection = load_json(args.auto_selection)
    derived = low_memory.get("derived") or {}
    failures: list[str] = []
    if low_memory.get("verdict") != "PASS":
        failures.append("low-memory profile evidence did not pass")
    if low_memory.get("dax_profile") != "agent-workspace-low-memory":
        failures.append(f"unexpected low-memory profile: {low_memory.get('dax_profile')!r}")
    if auto_selection.get("verdict") != "PASS":
        failures.append("auto-selection policy did not pass")

    tiers = [
        {
            "memory_gb": "16-24",
            "runtime_profile": "agent-workspace-low-memory",
            "model_guidance": "Prefer smaller MoE active-parameter models or 4-bit MLX models; avoid large bf16 dense models.",
            "cache_policy": "Small cache entry cap and explicit memory limit; aggressive pruning.",
            "status": "planned",
        },
        {
            "memory_gb": "32",
            "runtime_profile": "agent-workspace-low-memory",
            "model_guidance": "Use low-memory profile by default for 20B-35B class quantized models.",
            "cache_policy": "Bounded request-derived cache with first-hit conversion acceptance.",
            "status": "validated-profile",
        },
        {
            "memory_gb": "64+",
            "runtime_profile": "agent-workspace-async",
            "model_guidance": "Use async steady-state profile unless immediate second-turn or memory pressure is detected.",
            "cache_policy": "Prefer mature async reuse with manual low-memory override.",
            "status": "validated-default",
        },
    ]

    output = {
        "type": "mlx_lower_memory_mac_strategy",
        "tag": args.tag,
        "verdict": "PASS" if not failures else "FAIL",
        "failures": failures,
        "inputs": {
            "low_memory_summary": str(args.low_memory_summary),
            "auto_selection": str(args.auto_selection),
        },
        "validated_low_memory_profile": {
            "profile": low_memory.get("dax_profile"),
            "conversion_turn": derived.get("conversion_turn"),
            "conversion_actual_prefill_tokens": derived.get("conversion_actual_prefill_tokens"),
            "conversion_ratio_vs_baseline": derived.get("conversion_ratio_vs_baseline"),
            "mature_hit_speedup_vs_baseline": derived.get("mature_hit_speedup_vs_baseline"),
        },
        "strategy": {
            "default_low_memory_profile": "agent-workspace-low-memory",
            "auto_selection_signal": "memory_class_gb in 16/24/32 or explicit low_memory=true",
            "manual_override": "/profile low-memory",
            "future_feature": "layer/offload mode for lower-memory Macs, informed by the AirLLM sidequest",
        },
        "tiers": tiers,
        "acceptance": {
            "must_load_without_gpu_fallback": True,
            "must_keep_conversion_actual_prefill_tokens": "<=32",
            "must_report_peak_memory_gb": True,
            "must_report_cache_memory_limit_mb": True,
            "must_preserve_manual_override": True,
        },
    }
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n")
    print(
        "mlx_lower_memory_mac_strategy",
        output["verdict"],
        "profile",
        output["validated_low_memory_profile"]["profile"],
        "tiers",
        len(tiers),
        args.output_json,
        flush=True,
    )
    for failure in failures:
        print("failure", failure, flush=True)
    return 1 if args.fail_on_fail and failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
