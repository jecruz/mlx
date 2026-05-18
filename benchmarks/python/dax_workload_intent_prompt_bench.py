#!/usr/bin/env python3
"""Benchmark Dax MLX prompt paths for automatic workload intent selection."""

from __future__ import annotations

import argparse
import json
import subprocess
import time
import urllib.request
from pathlib import Path
from statistics import mean
from typing import Any


CASES = ("auto", "explicit-intent", "manual-profile")


def request_json(
    method: str,
    url: str,
    payload: dict[str, Any] | None = None,
    *,
    timeout: int = 120,
) -> dict[str, Any]:
    data = None
    headers = {}
    if payload is not None:
        data = json.dumps(payload).encode()
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode())


def health_summary(base_url: str) -> dict[str, Any]:
    health = request_json("GET", f"{base_url}/health")
    policy = health["prefix_cache_policy"]
    return {
        "ok": health["ok"],
        "runtime_profile": health.get("runtime_profile"),
        "engine_preset": health.get("engine_preset"),
        "population_mode": policy.get("population_mode"),
        "pending_wait_ms": policy.get("pending_wait_ms"),
        "total_requests": health.get("metrics", {}).get("total_requests"),
    }


def restore_interactive(base_url: str) -> dict[str, Any]:
    request_json("POST", f"{base_url}/engine/config", {"runtime_profile": "interactive"})
    return health_summary(base_url)


def command_for_case(
    *,
    dax_dir: Path,
    base_url: str,
    case: str,
    prompt: str,
    max_tokens: int,
) -> list[str]:
    cmd = [
        "npx",
        "tsx",
        "src/cli.ts",
        "mlx-engine",
        "--base-url",
        base_url,
        "--prompt",
        prompt,
        "--max-tokens",
        str(max_tokens),
    ]
    if case == "auto":
        return cmd
    if case == "explicit-intent":
        return [*cmd, "--intent", "coding-agent"]
    if case == "manual-profile":
        return [*cmd, "--profile", "agent-workspace-async"]
    raise ValueError(f"unknown case: {case}")


def run_case(
    *,
    dax_dir: Path,
    base_url: str,
    case: str,
    iteration: int,
    prompt: str,
    max_tokens: int,
) -> dict[str, Any]:
    before = restore_interactive(base_url)
    cmd = command_for_case(
        dax_dir=dax_dir,
        base_url=base_url,
        case=case,
        prompt=prompt,
        max_tokens=max_tokens,
    )
    started = time.perf_counter()
    completed = subprocess.run(
        cmd,
        cwd=dax_dir,
        check=False,
        capture_output=True,
        text=True,
        timeout=180,
    )
    wall_ms = (time.perf_counter() - started) * 1000.0
    after = health_summary(base_url)
    row = {
        "type": "dax_workload_intent_prompt_bench_row",
        "case": case,
        "iteration": iteration,
        "returncode": completed.returncode,
        "wall_ms": wall_ms,
        "command": cmd,
        "stdout": completed.stdout.strip(),
        "stderr": completed.stderr.strip(),
        "before": before,
        "after": after,
    }
    print(
        "m83_dax_prompt",
        case,
        iteration,
        "return",
        completed.returncode,
        "wall_ms",
        round(wall_ms, 2),
        "profile",
        after.get("runtime_profile"),
        "mode",
        after.get("population_mode"),
        "wait",
        after.get("pending_wait_ms"),
        flush=True,
    )
    if completed.returncode != 0:
        raise RuntimeError(f"{case} iteration {iteration} failed: {completed.stderr}")
    if after.get("runtime_profile") != "agent-workspace-async":
        raise RuntimeError(f"{case} did not apply agent-workspace-async: {after}")
    return row


def run_warmup(*, dax_dir: Path, base_url: str) -> None:
    cmd = [
        "npx",
        "tsx",
        "src/cli.ts",
        "mlx-engine",
        "--base-url",
        base_url,
        "--once",
    ]
    subprocess.run(
        cmd,
        cwd=dax_dir,
        check=True,
        capture_output=True,
        text=True,
        timeout=120,
    )


def ordered_cases(iteration: int) -> tuple[str, ...]:
    shift = (iteration - 1) % len(CASES)
    return (*CASES[shift:], *CASES[:shift])


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    cases = sorted({row["case"] for row in rows})
    summaries = {}
    for case in cases:
        case_rows = [row for row in rows if row["case"] == case]
        summaries[case] = {
            "runs": len(case_rows),
            "mean_wall_ms": mean(row["wall_ms"] for row in case_rows),
            "min_wall_ms": min(row["wall_ms"] for row in case_rows),
            "max_wall_ms": max(row["wall_ms"] for row in case_rows),
            "runtime_profiles": sorted(
                {row["after"].get("runtime_profile") for row in case_rows}
            ),
            "population_modes": sorted(
                {row["after"].get("population_mode") for row in case_rows}
            ),
        }
    auto_mean = summaries["auto"]["mean_wall_ms"]
    manual_mean = summaries["manual-profile"]["mean_wall_ms"]
    intent_mean = summaries["explicit-intent"]["mean_wall_ms"]
    return {
        "summaries": summaries,
        "auto_vs_manual_profile_wall_ratio": auto_mean / manual_mean,
        "auto_vs_explicit_intent_wall_ratio": auto_mean / intent_mean,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8773")
    parser.add_argument(
        "--dax-dir",
        type=Path,
        default=Path("/Users/jeffreycruz/Development/AI_AGENTS/dax-stereo/packages/coding-agent"),
    )
    parser.add_argument("--output-jsonl", type=Path, default=Path("dax-workload-intent-m83.jsonl"))
    parser.add_argument("--output-json", type=Path)
    parser.add_argument("--repeats", type=int, default=2)
    parser.add_argument("--max-tokens", type=int, default=4)
    parser.add_argument(
        "--prompt",
        default="Reply with exactly four short words about MLX prompt reuse.",
    )
    args = parser.parse_args()

    if args.repeats < 1:
        raise ValueError("--repeats must be positive")
    base_url = args.base_url.rstrip("/")
    args.output_jsonl.parent.mkdir(parents=True, exist_ok=True)
    args.output_jsonl.write_text("")

    run_warmup(dax_dir=args.dax_dir, base_url=base_url)
    rows: list[dict[str, Any]] = []
    for iteration in range(1, args.repeats + 1):
        for case in ordered_cases(iteration):
            row = run_case(
                dax_dir=args.dax_dir,
                base_url=base_url,
                case=case,
                iteration=iteration,
                prompt=args.prompt,
                max_tokens=args.max_tokens,
            )
            rows.append(row)
            with args.output_jsonl.open("a") as f:
                f.write(json.dumps(row, sort_keys=True) + "\n")

    report = {
        "type": "dax_workload_intent_prompt_bench",
        "verdict": "PASS",
        "base_url": base_url,
        "dax_dir": str(args.dax_dir),
        "output_jsonl": str(args.output_jsonl),
        "repeats": args.repeats,
        "prompt": args.prompt,
        "max_tokens": args.max_tokens,
        **summarize(rows),
    }
    if args.output_json:
        args.output_json.parent.mkdir(parents=True, exist_ok=True)
        args.output_json.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(
        "m83_dax_prompt_result",
        report["verdict"],
        "auto_ratio_manual",
        round(report["auto_vs_manual_profile_wall_ratio"], 3),
        "auto_ratio_intent",
        round(report["auto_vs_explicit_intent_wall_ratio"], 3),
        flush=True,
    )
    restore_interactive(base_url)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
