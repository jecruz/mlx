#!/usr/bin/env python3
"""Benchmark repeated Dax coding-agent prompts with shared context."""

from __future__ import annotations

import argparse
import json
import subprocess
import time
import urllib.request
from pathlib import Path
from typing import Any


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


def configure_profile(base_url: str, runtime_profile: str) -> dict[str, Any]:
    return request_json(
        "POST",
        f"{base_url}/engine/config",
        {"runtime_profile": runtime_profile},
    )


def prune_cache(base_url: str) -> dict[str, Any]:
    return request_json(
        "POST",
        f"{base_url}/engine/cache/prune",
        {"target_entries": 0, "clear_mlx_cache": False},
    )


def health_summary(base_url: str) -> dict[str, Any]:
    health = request_json("GET", f"{base_url}/health")
    policy = health["prefix_cache_policy"]
    return {
        "ok": health["ok"],
        "runtime_profile": health.get("runtime_profile"),
        "engine_preset": health.get("engine_preset"),
        "population_mode": policy.get("population_mode"),
        "pending_wait_ms": policy.get("pending_wait_ms"),
        "async_builds_started": policy.get("async_builds_started"),
        "async_builds_completed": policy.get("async_builds_completed"),
        "async_builds_failed": policy.get("async_builds_failed"),
        "pending_build_deduplications": policy.get("pending_build_deduplications"),
        "total_requests": (health.get("metrics") or {}).get("total_requests"),
    }


def build_prompt(*, run_id: str, shared_repeats: int, turn: int) -> str:
    shared_context = (
        f"M84 repeated coding-agent context {run_id}.\n"
        + (
            "Repository state includes MLX resident engine milestones, runtime "
            "profile selection, Dax prompt flow, prefix-cache policy, benchmark "
            "acceptance criteria, and coding-agent workspace instructions. "
        )
        * shared_repeats
    )
    return (
        shared_context
        + f"\nTurn {turn}: answer with four terse words about prompt reuse."
    )


def run_dax_prompt(
    *,
    dax_dir: Path,
    base_url: str,
    prompt: str,
    max_tokens: int,
    dax_profile: str | None,
    dax_intent: str | None,
) -> tuple[dict[str, Any], float, list[str]]:
    cmd = [
        "npx",
        "tsx",
        "src/cli.ts",
        "mlx-engine",
        "--base-url",
        base_url,
    ]
    if dax_profile:
        cmd.extend(["--profile", dax_profile])
    if dax_intent:
        cmd.extend(["--intent", dax_intent])
    cmd.extend(
        [
            "--prompt",
            prompt,
            "--max-tokens",
            str(max_tokens),
            "--json",
        ]
    )
    started = time.perf_counter()
    completed = subprocess.run(
        cmd,
        cwd=dax_dir,
        check=False,
        capture_output=True,
        text=True,
        timeout=240,
    )
    wall_ms = (time.perf_counter() - started) * 1000.0
    if completed.returncode != 0:
        raise RuntimeError(f"Dax prompt failed: {completed.stderr}")
    response = json.loads(completed.stdout)
    return response, wall_ms, cmd


def runtime_profile_for_intent(intent: str | None) -> str | None:
    if intent is None:
        return None
    return {
        "interactive": "interactive",
        "coding-agent": "agent-workspace-async",
        "agent-workspace": "agent-workspace-async",
        "coding-agent-first-hit": "agent-workspace-first-hit",
        "first-hit": "agent-workspace-first-hit",
        "coding-agent-low-memory": "agent-workspace-low-memory",
        "low-memory": "agent-workspace-low-memory",
        "memory-saver": "memory-saver",
        "diagnostics": "diagnostics",
    }.get(intent)


def auto_select_runtime_profile(
    *,
    manual_profile: str | None = None,
    diagnostics: bool = False,
    interactive: bool = False,
    agentic: bool = False,
    repeated_workspace: bool = False,
    immediate_second_turn: bool = False,
    low_memory: bool = False,
    memory_class_gb: int | None = None,
) -> tuple[str, str]:
    if manual_profile:
        return manual_profile, "manual override"
    if diagnostics:
        return "diagnostics", "diagnostics requested"
    if interactive and not agentic:
        return "interactive", "foreground interactive use"
    if low_memory or memory_class_gb in (16, 24, 32):
        return "agent-workspace-low-memory", "bounded memory mode"
    if immediate_second_turn:
        return "agent-workspace-first-hit", "immediate repeated-context second turn"
    if agentic or repeated_workspace:
        return "agent-workspace-async", "steady-state coding-agent reuse"
    return "interactive", "safe default for unknown foreground work"


def run_resident_prompt(
    *,
    base_url: str,
    prompt: str,
    max_tokens: int,
) -> tuple[dict[str, Any], float, list[str]]:
    payload = {
        "model": "resident-dax-client",
        "prompt": prompt,
        "max_tokens": max_tokens,
        "policy": "auto",
    }
    started = time.perf_counter()
    response = request_json("POST", f"{base_url}/v1/completions", payload)
    wall_ms = (time.perf_counter() - started) * 1000.0
    return response, wall_ms, ["POST", f"{base_url}/v1/completions"]


def metric(response: dict[str, Any], key: str) -> Any:
    return (response.get("engine_metrics") or {}).get(key)


def row_for_response(
    *,
    turn: int,
    response: dict[str, Any],
    wall_ms: float,
    command: list[str],
    after: dict[str, Any],
) -> dict[str, Any]:
    service_request_ms = metric(response, "service_request_ms")
    overhead_ms = (
        wall_ms - float(service_request_ms)
        if isinstance(service_request_ms, (int, float))
        else None
    )
    return {
        "type": "dax_repeated_context_bench_row",
        "turn": turn,
        "wall_ms": wall_ms,
        "overhead_ms": overhead_ms,
        "command": command,
        "finish_reason": response["choices"][0].get("finish_reason"),
        "usage": response.get("usage"),
        "engine_metrics": response.get("engine_metrics"),
        "service_request_ms": service_request_ms,
        "cache_hit": bool(metric(response, "cache_hit")),
        "cache_scheduled": bool(metric(response, "cache_scheduled")),
        "cache_pending": bool(metric(response, "cache_pending")),
        "cache_pending_wait_result": metric(response, "cache_pending_wait_result"),
        "actual_prefill_tokens": metric(response, "actual_prefill_tokens"),
        "prompt_tokens_estimate": metric(response, "prompt_tokens_estimate"),
        "longest_prefix_match_tokens": metric(response, "longest_prefix_match_tokens"),
        "after": after,
    }


def summarize(
    rows: list[dict[str, Any]],
    *,
    min_speedup: float,
    max_hit_prefill_tokens: int,
) -> dict[str, Any]:
    baseline = rows[0]
    hit_rows = [row for row in rows[1:] if row["cache_hit"]]
    best_hit = min(
        hit_rows,
        key=lambda row: (
            float(row["actual_prefill_tokens"] or 1e9),
            float(row["service_request_ms"] or 1e9),
        ),
        default=None,
    )
    baseline_service = float(baseline["service_request_ms"] or 0.0)
    best_hit_service = (
        float(best_hit["service_request_ms"] or 0.0) if best_hit is not None else 0.0
    )
    speedup = (
        baseline_service / best_hit_service
        if best_hit is not None and best_hit_service > 0
        else None
    )
    verdict = (
        "PASS"
        if best_hit is not None
        and (best_hit.get("actual_prefill_tokens") or 1e9) <= max_hit_prefill_tokens
        and (speedup or 0.0) >= min_speedup
        else "FAIL"
    )
    return {
        "verdict": verdict,
        "baseline": baseline,
        "best_hit": best_hit,
        "best_hit_selection": "lowest_prefill_then_lowest_service_request_ms",
        "hit_count": len(hit_rows),
        "baseline_service_request_ms": baseline_service,
        "best_hit_service_request_ms": best_hit_service if best_hit else None,
        "best_hit_speedup_vs_baseline": speedup,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8773")
    parser.add_argument(
        "--dax-dir",
        type=Path,
        default=Path("/Users/jeffreycruz/Development/AI_AGENTS/dax-stereo/packages/coding-agent"),
    )
    parser.add_argument("--output-jsonl", type=Path, default=Path("dax-repeated-context-m84.jsonl"))
    parser.add_argument("--output-json", type=Path)
    parser.add_argument("--turns", type=int, default=4)
    parser.add_argument("--shared-repeats", type=int, default=64)
    parser.add_argument("--max-tokens", type=int, default=4)
    parser.add_argument("--dax-profile")
    parser.add_argument("--dax-intent")
    parser.add_argument("--client-mode", choices=("cli", "resident"), default="cli")
    parser.add_argument("--auto-select-profile", action="store_true")
    parser.add_argument("--memory-class-gb", type=int)
    parser.add_argument("--immediate-second-turn", action="store_true")
    parser.add_argument("--low-memory", action="store_true")
    parser.add_argument("--diagnostics-workload", action="store_true")
    parser.add_argument("--interactive-workload", action="store_true")
    parser.add_argument("--agentic-workload", action="store_true")
    parser.add_argument("--repeated-workspace", action="store_true")
    parser.add_argument("--min-speedup", type=float, default=2.0)
    parser.add_argument("--max-hit-prefill-tokens", type=int, default=32)
    parser.add_argument("--fail-on-fail", action="store_true")
    args = parser.parse_args()

    if args.turns < 2:
        raise ValueError("--turns must be at least 2")
    base_url = args.base_url.rstrip("/")
    run_id = str(int(time.time()))
    args.output_jsonl.parent.mkdir(parents=True, exist_ok=True)
    args.output_jsonl.write_text("")

    auto_selection_reason = None
    if args.auto_select_profile:
        target_profile, auto_selection_reason = auto_select_runtime_profile(
            manual_profile=args.dax_profile,
            diagnostics=args.diagnostics_workload,
            interactive=args.interactive_workload,
            agentic=args.agentic_workload,
            repeated_workspace=args.repeated_workspace,
            immediate_second_turn=args.immediate_second_turn,
            low_memory=args.low_memory,
            memory_class_gb=args.memory_class_gb,
        )
    else:
        target_profile = args.dax_profile or runtime_profile_for_intent(args.dax_intent)
    if args.client_mode == "resident" and args.dax_intent and target_profile is None:
        raise ValueError(f"unknown --dax-intent for resident client mode: {args.dax_intent}")

    configure_profile(base_url, "interactive")
    prune_cache(base_url)
    if args.client_mode == "resident" and target_profile:
        configure_profile(base_url, target_profile)
    rows: list[dict[str, Any]] = []
    try:
        for turn in range(1, args.turns + 1):
            prompt = build_prompt(
                run_id=run_id,
                shared_repeats=args.shared_repeats,
                turn=turn,
            )
            if args.client_mode == "resident":
                response, wall_ms, command = run_resident_prompt(
                    base_url=base_url,
                    prompt=prompt,
                    max_tokens=args.max_tokens,
                )
            else:
                response, wall_ms, command = run_dax_prompt(
                    dax_dir=args.dax_dir,
                    base_url=base_url,
                    prompt=prompt,
                    max_tokens=args.max_tokens,
                    dax_profile=args.dax_profile,
                    dax_intent=args.dax_intent,
                )
            after = health_summary(base_url)
            row = row_for_response(
                turn=turn,
                response=response,
                wall_ms=wall_ms,
                command=command,
                after=after,
            )
            rows.append(row)
            with args.output_jsonl.open("a") as f:
                f.write(json.dumps(row, sort_keys=True) + "\n")
            print(
                "m84_dax_repeated",
                turn,
                "wall_ms",
                round(wall_ms, 2),
                "service_ms",
                round(float(row["service_request_ms"] or 0.0), 2),
                "hit",
                row["cache_hit"],
                "scheduled",
                row["cache_scheduled"],
                "prefill",
                row["actual_prefill_tokens"],
                "profile",
                after["runtime_profile"],
                flush=True,
            )
    finally:
        configure_profile(base_url, "interactive")

    summary = summarize(
        rows,
        min_speedup=args.min_speedup,
        max_hit_prefill_tokens=args.max_hit_prefill_tokens,
    )
    report = {
        "type": "dax_repeated_context_bench",
        "base_url": base_url,
        "dax_dir": str(args.dax_dir),
        "output_jsonl": str(args.output_jsonl),
        "turns": args.turns,
        "shared_repeats": args.shared_repeats,
        "max_tokens": args.max_tokens,
        "dax_profile": args.dax_profile,
        "dax_intent": args.dax_intent,
        "client_mode": args.client_mode,
        "auto_select_profile": args.auto_select_profile,
        "auto_selected_profile": target_profile if args.auto_select_profile else None,
        "auto_selection_reason": auto_selection_reason,
        "min_speedup": args.min_speedup,
        "max_hit_prefill_tokens": args.max_hit_prefill_tokens,
        "rows": rows,
        **summary,
    }
    if args.output_json:
        args.output_json.parent.mkdir(parents=True, exist_ok=True)
        args.output_json.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(
        "m84_dax_repeated_result",
        report["verdict"],
        "hits",
        report["hit_count"],
        "speedup",
        round(report["best_hit_speedup_vs_baseline"] or 0.0, 3),
        flush=True,
    )
    return 1 if args.fail_on_fail and report["verdict"] != "PASS" else 0


if __name__ == "__main__":
    raise SystemExit(main())
