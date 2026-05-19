#!/usr/bin/env python3
"""Run the Dax product path and gate first-hit conversion."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any


def run(cmd: list[str], *, cwd: Path) -> None:
    print("dax_product_first_hit_cmd", " ".join(cmd), flush=True)
    subprocess.run(cmd, cwd=cwd, check=True)


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text())


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8773")
    parser.add_argument(
        "--dax-dir",
        type=Path,
        default=Path(
            "/Users/jeffreycruz/Development/AI_AGENTS/dax-stereo/packages/coding-agent"
        ),
    )
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--tag", default="m93-qwen-a3b")
    parser.add_argument("--dax-profile", default="agent-workspace-first-hit")
    parser.add_argument("--dax-intent")
    parser.add_argument("--turns", type=int, default=4)
    parser.add_argument("--shared-repeats", type=int, default=64)
    parser.add_argument("--max-tokens", type=int, default=4)
    parser.add_argument("--expected-conversion-turn", type=int, default=2)
    parser.add_argument("--max-conversion-prefill-tokens", type=int, default=32)
    parser.add_argument("--max-conversion-ratio", type=float, default=0.85)
    parser.add_argument("--min-mature-hit-speedup", type=float, default=2.0)
    parser.add_argument("--max-mature-hit-prefill-tokens", type=int, default=32)
    parser.add_argument("--fail-on-fail", action="store_true")
    args = parser.parse_args()

    cwd = Path.cwd()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    benchmark_jsonl = args.output_dir / f"dax-product-first-hit-{args.tag}.jsonl"
    benchmark_json = args.output_dir / f"dax-product-first-hit-{args.tag}.json"
    gate_json = args.output_dir / f"dax-product-first-hit-gate-{args.tag}.json"
    summary_json = args.output_dir / f"dax-product-first-hit-summary-{args.tag}.json"

    bench_cmd = [
        sys.executable,
        "benchmarks/python/dax_repeated_context_bench.py",
        "--base-url",
        args.base_url,
        "--dax-dir",
        str(args.dax_dir),
        "--output-jsonl",
        str(benchmark_jsonl),
        "--output-json",
        str(benchmark_json),
        "--turns",
        str(args.turns),
        "--shared-repeats",
        str(args.shared_repeats),
        "--max-tokens",
        str(args.max_tokens),
        "--dax-profile",
        args.dax_profile,
        "--fail-on-fail",
    ]
    if args.dax_intent:
        bench_cmd.extend(["--dax-intent", args.dax_intent])
    run(bench_cmd, cwd=cwd)

    gate_cmd = [
        sys.executable,
        "benchmarks/python/dax_first_hit_conversion_gate.py",
        str(benchmark_json),
        "--output-json",
        str(gate_json),
        "--expected-conversion-turn",
        str(args.expected_conversion_turn),
        "--max-conversion-prefill-tokens",
        str(args.max_conversion_prefill_tokens),
        "--max-conversion-ratio",
        str(args.max_conversion_ratio),
        "--min-mature-hit-speedup",
        str(args.min_mature_hit_speedup),
        "--max-mature-hit-prefill-tokens",
        str(args.max_mature_hit_prefill_tokens),
    ]
    if args.fail_on_fail:
        gate_cmd.append("--fail-on-fail")
    run(gate_cmd, cwd=cwd)

    benchmark = load_json(benchmark_json)
    gate = load_json(gate_json)
    summary: dict[str, Any] = {
        "type": "dax_product_first_hit_gate",
        "verdict": gate.get("verdict"),
        "base_url": args.base_url,
        "dax_profile": args.dax_profile,
        "dax_intent": args.dax_intent,
        "tag": args.tag,
        "artifacts": {
            "benchmark_json": str(benchmark_json),
            "benchmark_jsonl": str(benchmark_jsonl),
            "gate_json": str(gate_json),
        },
        "benchmark_verdict": benchmark.get("verdict"),
        "gate_verdict": gate.get("verdict"),
        "derived": gate.get("derived") or {},
        "failures": gate.get("failures") or [],
    }
    summary_json.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    print(
        "dax_product_first_hit_result",
        summary["verdict"],
        "profile",
        args.dax_profile,
        "conversion_prefill",
        summary["derived"].get("conversion_actual_prefill_tokens"),
        "conversion_ratio",
        summary["derived"].get("conversion_ratio_vs_baseline"),
        summary_json,
        flush=True,
    )
    return 1 if args.fail_on_fail and summary["verdict"] != "PASS" else 0


if __name__ == "__main__":
    raise SystemExit(main())
