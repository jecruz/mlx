# Copyright © 2023-2024 Apple Inc.

import argparse
import json
import statistics
from pathlib import Path


def parse_args():
    parser = argparse.ArgumentParser(
        description="Create an engine prefill profile from prompt sweep JSONL files."
    )
    parser.add_argument(
        "--input-jsonl",
        type=Path,
        action="append",
        required=True,
        help="One or more JSONL files from inprocess_prompt_sweep.py.",
    )
    parser.add_argument(
        "--output-json",
        type=Path,
        required=True,
        help="Where to write the engine-consumable profile.",
    )
    parser.add_argument(
        "--memory-headroom-gb",
        type=float,
        default=0.5,
        help="Prefer lower-memory candidates within this throughput headroom.",
    )
    return parser.parse_args()


def load_rows(paths):
    rows = []
    for path in paths:
        if not path.exists():
            raise SystemExit(f"{path}: file not found")
        for line_no, line in enumerate(path.read_text().splitlines(), start=1):
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise SystemExit(f"{path}:{line_no}: invalid JSON: {exc}") from exc
    if not rows:
        raise SystemExit("no benchmark rows found")
    return rows


def group_candidates(rows):
    candidates = {}
    for row in rows:
        key = (
            row.get("prefill_step_size"),
            int(row["requested_prompt_tokens"]),
        )
        candidates.setdefault(key, []).append(row)

    grouped = []
    for (step_size, prompt_tokens), group in sorted(
        candidates.items(), key=lambda item: ((item[0][0] is None, item[0][0] or 0), item[0][1])
    ):
        grouped.append(
            {
                "prefill_step_size": step_size,
                "prompt_tokens": prompt_tokens,
                "samples": len(group),
                "mean_prompt_tps": statistics.fmean(
                    float(row["prompt_tps"]) for row in group
                ),
                "median_prompt_tps": statistics.median(
                    float(row["prompt_tps"]) for row in group
                ),
                "mean_run_ms": statistics.fmean(float(row["run_ms"]) for row in group),
                "max_peak_memory_gb": max(float(row["peak_memory_gb"]) for row in group),
            }
        )
    return grouped


def select_profiles(candidates, memory_headroom_gb):
    throughput_default = max(candidates, key=lambda row: row["mean_prompt_tps"])
    memory_saver = min(candidates, key=lambda row: row["max_peak_memory_gb"])

    allowed_memory = memory_saver["max_peak_memory_gb"] + memory_headroom_gb
    balanced_pool = [
        row for row in candidates if row["max_peak_memory_gb"] <= allowed_memory
    ]
    balanced = max(balanced_pool, key=lambda row: row["mean_prompt_tps"])
    return {
        "throughput_default": throughput_default,
        "memory_saver": memory_saver,
        "balanced": balanced,
    }


def select_prompt_token_bands(candidates, memory_headroom_gb):
    by_prompt_tokens = {}
    for row in candidates:
        by_prompt_tokens.setdefault(int(row["prompt_tokens"]), []).append(row)

    bands = []
    previous_max = 0
    for prompt_tokens, group in sorted(by_prompt_tokens.items()):
        bands.append(
            {
                "min_prompt_tokens": previous_max + 1,
                "max_prompt_tokens": prompt_tokens,
                "candidate_count": len(group),
                "policy": select_profiles(group, memory_headroom_gb),
            }
        )
        previous_max = prompt_tokens
    return bands


def select_global_fallback_policy(candidates, memory_headroom_gb):
    largest_prompt_tokens = max(int(row["prompt_tokens"]) for row in candidates)
    largest_prompt_candidates = [
        row
        for row in candidates
        if int(row["prompt_tokens"]) == largest_prompt_tokens
    ]
    return select_profiles(largest_prompt_candidates, memory_headroom_gb)


def main():
    args = parse_args()
    rows = load_rows(args.input_jsonl)
    candidates = group_candidates(rows)
    model = rows[0].get("model")
    backend = rows[0].get("backend")
    device = rows[0].get("default_device")
    metal = rows[0].get("metal_available")
    profile = {
        "model": model,
        "backend": backend,
        "default_device": device,
        "metal_available": metal,
        "policy": select_global_fallback_policy(candidates, args.memory_headroom_gb),
        "prompt_token_bands": select_prompt_token_bands(
            candidates,
            args.memory_headroom_gb,
        ),
        "candidates": candidates,
        "source_files": [str(path) for path in args.input_jsonl],
    }
    args.output_json.write_text(json.dumps(profile, indent=2, sort_keys=True) + "\n")
    policy = profile["policy"]
    print(f"wrote {args.output_json}")
    print(
        "throughput_default: "
        f"prefill_step_size={policy['throughput_default']['prefill_step_size']} "
        f"prompt_tps={policy['throughput_default']['mean_prompt_tps']:.3f} "
        f"peak_memory_gb={policy['throughput_default']['max_peak_memory_gb']:.3f}"
    )
    print(
        "memory_saver: "
        f"prefill_step_size={policy['memory_saver']['prefill_step_size']} "
        f"prompt_tps={policy['memory_saver']['mean_prompt_tps']:.3f} "
        f"peak_memory_gb={policy['memory_saver']['max_peak_memory_gb']:.3f}"
    )
    print(
        "balanced: "
        f"prefill_step_size={policy['balanced']['prefill_step_size']} "
        f"prompt_tps={policy['balanced']['mean_prompt_tps']:.3f} "
        f"peak_memory_gb={policy['balanced']['max_peak_memory_gb']:.3f}"
    )


if __name__ == "__main__":
    main()
