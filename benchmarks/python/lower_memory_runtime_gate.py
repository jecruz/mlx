#!/usr/bin/env python3
"""Gate lower-memory MLX runtime evidence beyond latency."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from statistics import mean
from typing import Any


def as_float(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


def load_rows(path: Path) -> list[dict[str, Any]]:
    if path.suffix == ".jsonl":
        return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    payload = json.loads(path.read_text())
    if "rows" in payload:
        return payload["rows"]
    raise ValueError(f"unsupported lower-memory input: {path}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "input",
        type=Path,
        nargs="?",
        default=Path(
            "artifacts/m98-direct-low-memory-profile/"
            "dax-product-first-hit-m98-qwen-a3b-low-memory-direct.jsonl"
        ),
    )
    parser.add_argument("--output-json", type=Path, required=True)
    parser.add_argument("--tag", default="m112-qwen-a3b")
    parser.add_argument("--max-peak-memory-gb", type=float, default=32.0)
    parser.add_argument("--max-cache-memory-limit-mb", type=float, default=64.0)
    parser.add_argument("--max-conversion-prefill-tokens", type=float, default=32.0)
    parser.add_argument("--fail-on-fail", action="store_true")
    args = parser.parse_args()

    rows = load_rows(args.input)
    peak_memory = []
    cache_limits = []
    actual_prefill = []
    profiles = set()
    for row in rows:
        metrics = row.get("engine_metrics") or {}
        after = row.get("after") or {}
        if after.get("runtime_profile"):
            profiles.add(after["runtime_profile"])
        if (value := as_float(metrics.get("peak_memory_gb"))) is not None:
            peak_memory.append(value)
        if (value := as_float(metrics.get("memory_prune_limit_bytes"))) is not None:
            cache_limits.append(value / (1024 * 1024))
        if (value := as_float(row.get("actual_prefill_tokens"))) is not None:
            actual_prefill.append(value)

    failures = []
    if "agent-workspace-low-memory" not in profiles:
        failures.append(f"agent-workspace-low-memory not observed in profiles={sorted(profiles)}")
    if not peak_memory:
        failures.append("peak_memory_gb missing")
    elif max(peak_memory) > args.max_peak_memory_gb:
        failures.append(f"peak_memory_gb {max(peak_memory):.3f} > {args.max_peak_memory_gb:.3f}")
    if not cache_limits:
        failures.append("memory_prune_limit_bytes missing")
    elif max(cache_limits) > args.max_cache_memory_limit_mb:
        failures.append(
            f"cache_memory_limit_mb {max(cache_limits):.3f} > {args.max_cache_memory_limit_mb:.3f}"
        )
    conversion_prefill = min((value for value in actual_prefill if value <= 64), default=None)
    if conversion_prefill is None or conversion_prefill > args.max_conversion_prefill_tokens:
        failures.append(
            f"conversion_prefill_tokens {conversion_prefill} > {args.max_conversion_prefill_tokens}"
        )

    output = {
        "type": "lower_memory_runtime_gate",
        "tag": args.tag,
        "verdict": "PASS" if not failures else "FAIL",
        "input": str(args.input),
        "row_count": len(rows),
        "profiles": sorted(profiles),
        "thresholds": {
            "max_peak_memory_gb": args.max_peak_memory_gb,
            "max_cache_memory_limit_mb": args.max_cache_memory_limit_mb,
            "max_conversion_prefill_tokens": args.max_conversion_prefill_tokens,
        },
        "metrics": {
            "max_peak_memory_gb": max(peak_memory) if peak_memory else None,
            "mean_peak_memory_gb": mean(peak_memory) if peak_memory else None,
            "max_cache_memory_limit_mb": max(cache_limits) if cache_limits else None,
            "conversion_prefill_tokens": conversion_prefill,
        },
        "failures": failures,
    }
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n")
    print(
        "lower_memory_runtime_gate",
        output["verdict"],
        "rows",
        len(rows),
        "max_peak_memory_gb",
        output["metrics"]["max_peak_memory_gb"],
        args.output_json,
        flush=True,
    )
    for failure in failures:
        print("failure", failure, flush=True)
    return 1 if args.fail_on_fail and failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
