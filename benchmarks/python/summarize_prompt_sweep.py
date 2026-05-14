# Copyright © 2023-2024 Apple Inc.

import argparse
import json
import statistics
from pathlib import Path


def parse_args():
    parser = argparse.ArgumentParser(
        description="Summarize JSONL output from run_prompt_sweep.sh."
    )
    parser.add_argument("jsonl", type=Path, help="Prompt sweep JSONL file.")
    parser.add_argument(
        "--min-gpu-prompt-tps",
        type=float,
        default=1.0,
        help="Warn if GPU prompt throughput is below this threshold.",
    )
    return parser.parse_args()


def load_rows(path: Path):
    if not path.exists():
        raise SystemExit(
            f"{path}: file not found; run run_prompt_sweep.sh successfully first"
        )
    rows = []
    for line_no, line in enumerate(path.read_text().splitlines(), start=1):
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError as exc:
            raise SystemExit(f"{path}:{line_no}: invalid JSON: {exc}") from exc
    if not rows:
        raise SystemExit(f"{path}: no benchmark rows found")
    return rows


def fmt_float(value, precision=2):
    if value is None:
        return "-"
    return f"{float(value):.{precision}f}"


def main():
    args = parse_args()
    rows = load_rows(args.jsonl)
    rows.sort(key=lambda row: row.get("requested_prompt_tokens") or row["prompt_tokens"])

    model = rows[0].get("model", "-")
    backend = rows[0].get("backend", "-")
    device = rows[0].get("default_device", "-")
    metal = rows[0].get("metal_available", False)
    prompt_tps_values = [float(row["prompt_tps"]) for row in rows]
    run_ms_values = [float(row["run_ms"]) for row in rows]

    print(f"model: {model}")
    print(f"backend: {backend}")
    print(f"device: {device}")
    print(f"metal_available: {metal}")
    print()
    print(
        "requested_tokens prompt_tokens load_ms run_ms prompt_tps generation_tps peak_memory_gb"
    )
    for row in rows:
        print(
            " ".join(
                [
                    str(row.get("requested_prompt_tokens") or "-"),
                    str(row["prompt_tokens"]),
                    fmt_float(row["load_ms"]),
                    fmt_float(row["run_ms"]),
                    fmt_float(row["prompt_tps"], 3),
                    fmt_float(row["generation_tps"], 3),
                    fmt_float(row["peak_memory_gb"], 3),
                ]
            )
        )

    print()
    print(f"mean_prompt_tps: {statistics.fmean(prompt_tps_values):.3f}")
    print(f"median_prompt_tps: {statistics.median(prompt_tps_values):.3f}")
    print(f"mean_run_ms: {statistics.fmean(run_ms_values):.2f}")

    if not (metal and "gpu" in str(device)):
        print("verdict: invalid_gpu_sweep")
        print("reason: MLX did not report a Metal GPU device.")
    elif statistics.fmean(prompt_tps_values) < args.min_gpu_prompt_tps:
        print("verdict: gpu_prompt_processing_bottleneck")
        print(
            "reason: prompt throughput is below the configured GPU threshold; inspect prefill path, chunking, and graph compilation."
        )
    else:
        print("verdict: gpu_sweep_collected")
        print("reason: results are GPU-backed and ready for comparison.")


if __name__ == "__main__":
    main()
