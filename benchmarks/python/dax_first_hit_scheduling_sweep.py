#!/usr/bin/env python3
"""Sweep Dax profile choices for first-hit scheduling behavior."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any


def run(cmd: list[str], *, cwd: Path) -> None:
    print("first_hit_sweep_cmd", " ".join(cmd), flush=True)
    subprocess.run(cmd, cwd=cwd, check=True)


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text())


def numeric(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


def variant_config(name: str) -> dict[str, str | None]:
    variants: dict[str, dict[str, str | None]] = {
        "auto": {"profile": None, "intent": None},
        "agent-workspace-async": {"profile": "agent-workspace-async", "intent": None},
        "agent-workspace-first-hit": {
            "profile": "agent-workspace-first-hit",
            "intent": None,
        },
        "agent-workspace": {"profile": "agent-workspace", "intent": None},
        "agent-workspace-request": {"profile": "agent-workspace-request", "intent": None},
    }
    if name not in variants:
        raise argparse.ArgumentTypeError(f"unknown variant: {name}")
    return variants[name]


def summarize_variant(
    *,
    name: str,
    benchmark: dict[str, Any],
    first_hit_gate: dict[str, Any],
) -> dict[str, Any]:
    derived = first_hit_gate.get("derived") or {}
    return {
        "variant": name,
        "benchmark_verdict": benchmark.get("verdict"),
        "first_hit_gate_verdict": first_hit_gate.get("verdict"),
        "hit_count": benchmark.get("hit_count"),
        "best_hit_speedup_vs_baseline": benchmark.get("best_hit_speedup_vs_baseline"),
        "scheduled_pre_hit_service_request_ms": derived.get(
            "scheduled_pre_hit_service_request_ms"
        ),
        "scheduled_pre_hit_ratio_vs_baseline": derived.get(
            "scheduled_pre_hit_ratio_vs_baseline"
        ),
        "scheduled_pre_hit_actual_prefill_tokens": derived.get(
            "scheduled_pre_hit_actual_prefill_tokens"
        ),
        "first_hit_service_request_ms": derived.get("first_hit_service_request_ms"),
        "first_hit_speedup_vs_baseline": derived.get("first_hit_speedup_vs_baseline"),
        "first_hit_actual_prefill_tokens": derived.get("first_hit_actual_prefill_tokens"),
        "failures": first_hit_gate.get("failures") or [],
    }


def choose_best(summaries: list[dict[str, Any]]) -> dict[str, Any] | None:
    candidates = [
        item
        for item in summaries
        if item.get("benchmark_verdict") == "PASS"
        and item.get("first_hit_gate_verdict") == "PASS"
        and numeric(item.get("scheduled_pre_hit_service_request_ms")) is not None
    ]
    if not candidates:
        return None
    return min(
        candidates,
        key=lambda item: (
            float(item["scheduled_pre_hit_service_request_ms"]),
            float(item.get("first_hit_service_request_ms") or 1e9),
        ),
    )


def choose_best_observed(summaries: list[dict[str, Any]]) -> dict[str, Any] | None:
    candidates = [
        item
        for item in summaries
        if item.get("benchmark_verdict") == "PASS"
        and numeric(item.get("scheduled_pre_hit_service_request_ms")) is not None
    ]
    if not candidates:
        return None
    return min(
        candidates,
        key=lambda item: (
            float(item["scheduled_pre_hit_service_request_ms"]),
            float(item.get("first_hit_service_request_ms") or 1e9),
        ),
    )


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
    parser.add_argument("--output-json", type=Path)
    parser.add_argument("--tag", default="m91-qwen-a3b")
    parser.add_argument("--variants", default="auto,agent-workspace,agent-workspace-async")
    parser.add_argument("--turns", type=int, default=4)
    parser.add_argument("--shared-repeats", type=int, default=64)
    parser.add_argument("--max-tokens", type=int, default=4)
    parser.add_argument("--max-scheduled-pre-hit-ms", type=float, default=1600.0)
    parser.add_argument("--max-scheduled-pre-hit-ratio", type=float, default=0.50)
    parser.add_argument("--min-scheduled-pre-hit-prefill-tokens", type=int, default=512)
    parser.add_argument("--min-first-hit-speedup", type=float, default=2.0)
    parser.add_argument("--max-first-hit-prefill-tokens", type=int, default=32)
    parser.add_argument("--fail-on-fail", action="store_true")
    args = parser.parse_args()

    cwd = Path.cwd()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    variant_names = [item.strip() for item in args.variants.split(",") if item.strip()]
    summaries = []
    artifacts = {}
    for name in variant_names:
        config = variant_config(name)
        benchmark_jsonl = args.output_dir / f"dax-repeated-context-{args.tag}-{name}.jsonl"
        benchmark_json = args.output_dir / f"dax-repeated-context-{args.tag}-{name}.json"
        gate_json = args.output_dir / f"dax-first-hit-latency-gate-{args.tag}-{name}.json"
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
            "--fail-on-fail",
        ]
        if config["profile"]:
            bench_cmd.extend(["--dax-profile", str(config["profile"])])
        if config["intent"]:
            bench_cmd.extend(["--dax-intent", str(config["intent"])])
        run(bench_cmd, cwd=cwd)
        run(
            [
                sys.executable,
                "benchmarks/python/dax_first_hit_latency_gate.py",
                str(benchmark_json),
                "--output-json",
                str(gate_json),
                "--max-scheduled-pre-hit-ms",
                str(args.max_scheduled_pre_hit_ms),
                "--max-scheduled-pre-hit-ratio",
                str(args.max_scheduled_pre_hit_ratio),
                "--min-scheduled-pre-hit-prefill-tokens",
                str(args.min_scheduled_pre_hit_prefill_tokens),
                "--min-first-hit-speedup",
                str(args.min_first_hit_speedup),
                "--max-first-hit-prefill-tokens",
                str(args.max_first_hit_prefill_tokens),
            ],
            cwd=cwd,
        )
        benchmark = load_json(benchmark_json)
        gate = load_json(gate_json)
        summaries.append(summarize_variant(name=name, benchmark=benchmark, first_hit_gate=gate))
        artifacts[name] = {
            "benchmark_json": str(benchmark_json),
            "benchmark_jsonl": str(benchmark_jsonl),
            "first_hit_gate_json": str(gate_json),
        }

    best_passing = choose_best(summaries)
    best_observed = choose_best_observed(summaries)
    sweep_completed = len(summaries) == len(variant_names) and all(
        item.get("benchmark_verdict") == "PASS" for item in summaries
    )
    report = {
        "type": "dax_first_hit_scheduling_sweep",
        "verdict": "PASS" if sweep_completed else "FAIL",
        "target_verdict": "PASS" if best_passing is not None else "FAIL",
        "base_url": args.base_url,
        "tag": args.tag,
        "variants": variant_names,
        "artifacts": artifacts,
        "summaries": summaries,
        "best_passing": best_passing,
        "best_observed": best_observed,
    }
    output_json = args.output_json or args.output_dir / f"dax-first-hit-scheduling-sweep-{args.tag}.json"
    output_json.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    for item in summaries:
        print(
            "first_hit_sweep_variant",
            item["variant"],
            item["first_hit_gate_verdict"],
            "scheduled_ms",
            item["scheduled_pre_hit_service_request_ms"],
            "first_hit_ms",
            item["first_hit_service_request_ms"],
        )
    print(
        "first_hit_sweep_result",
        report["verdict"],
        "target",
        report["target_verdict"],
        "best_passing",
        None if best_passing is None else best_passing["variant"],
        "best_observed",
        None if best_observed is None else best_observed["variant"],
        output_json,
    )
    return 1 if args.fail_on_fail and report["target_verdict"] != "PASS" else 0


if __name__ == "__main__":
    raise SystemExit(main())
