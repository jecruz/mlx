#!/usr/bin/env python3
"""Measure resident MLX latency impact from real prefix-cache reuse."""

from __future__ import annotations

import argparse
import json
import statistics
import time
import urllib.request
import uuid
from collections import defaultdict
from pathlib import Path
from typing import Any


def request_json(method: str, url: str, payload: dict[str, Any] | None = None):
    data = None
    headers = {}
    if payload is not None:
        data = json.dumps(payload).encode()
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    with urllib.request.urlopen(req, timeout=240) as resp:
        return json.loads(resp.read().decode())


def build_shared_prefix(*, group_id: str, target_repeats: int) -> str:
    base_context = """\
System: You are a local coding assistant connected to a resident MLX engine.
Follow the repo rules exactly, preserve paths, and do not invent benchmark
results. You are evaluating prompt-processing latency for repeated coding-agent
requests on Apple Silicon.

Repository context:
- resident service exposes /health, /metrics, /generate, /v1/completions,
  /v1/chat/completions, /engine, /engine/reload, and /engine/unload.
- model target is gpt-oss-20b-MXFP4-Q8 in MLX format.
- prefix cache reuse should avoid recomputing stable system, tool, and repo
  context across related requests.
- report concrete timings and token counts only.

Stable tool schema:
- read_file(path)
- search_text(pattern, path)
- run_command(command, cwd)
- update_redmine(issue_id, note)

"""
    repeated_context = (
        "Stable project fact: prefix reuse is valuable when system prompts, "
        "tool schemas, repo instructions, and active task context are repeated "
        "across sequential coding-agent turns.\n"
    )
    return (
        f"Benchmark group: {group_id}\n"
        + base_context
        + repeated_context * target_repeats
        + "\nUser task:\n"
    )


def build_tasks(count: int) -> list[str]:
    task_bank = [
        "Summarize the prefix-cache acceptance criteria.",
        "Explain which metric proves suffix-only prefill happened.",
        "List one risk when caching tool-augmented prompts.",
        "Describe how this helps Pi coding-agent requests.",
        "Compare cache-create and cache-hit behavior.",
        "Name the next benchmark needed before paged KV.",
        "Explain why first request should be slower.",
        "State the fallback rule if cache metadata differs.",
    ]
    return [task_bank[i % len(task_bank)] for i in range(count)]


def classify_phase(index_in_group: int, metrics: dict[str, Any]) -> str:
    if metrics.get("cache_scheduled"):
        return "cache_scheduled"
    if not metrics.get("cache_reuse_enabled"):
        return "full_prefill"
    if metrics.get("cache_created"):
        return "cache_create"
    if metrics.get("cache_hit"):
        return "cache_hit"
    return "cache_other"


def mean(values: list[float]) -> float | None:
    return statistics.fmean(values) if values else None


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8765")
    parser.add_argument("--output-jsonl", default="prefix-latency-sweep.jsonl")
    parser.add_argument("--groups", type=int, default=3)
    parser.add_argument("--requests-per-group", type=int, default=6)
    parser.add_argument("--prefix-repeats", type=int, default=24)
    parser.add_argument("--max-tokens", type=int, default=8)
    parser.add_argument("--policy", default="auto")
    args = parser.parse_args()

    base_url = args.base_url.rstrip("/")
    output_path = Path(args.output_jsonl)
    output_path.write_text("")

    rows = []
    for group_index in range(1, args.groups + 1):
        group_id = f"{int(time.time())}-{group_index}-{uuid.uuid4().hex[:8]}"
        shared_prefix = build_shared_prefix(
            group_id=group_id,
            target_repeats=args.prefix_repeats,
        )
        for request_index, task in enumerate(
            build_tasks(args.requests_per_group),
            start=1,
        ):
            prompt = shared_prefix + task
            started = time.perf_counter()
            response = request_json(
                "POST",
                f"{base_url}/v1/completions",
                {
                    "model": "local-gpt-oss",
                    "prompt": prompt,
                    "max_tokens": args.max_tokens,
                    "policy": args.policy,
                },
            )
            elapsed_ms = 1e3 * (time.perf_counter() - started)
            metrics = response["engine_metrics"]
            phase = classify_phase(request_index, metrics)
            row = {
                "group_index": group_index,
                "request_index": request_index,
                "phase": phase,
                "elapsed_ms": elapsed_ms,
                "run_ms": metrics["run_ms"],
                "service_request_ms": metrics.get("service_request_ms"),
                "cache_prepare_ms": metrics.get("cache_prepare_ms"),
                "prompt_tokens": metrics["prompt_tokens"],
                "actual_prefill_tokens": metrics.get("actual_prefill_tokens"),
                "generation_tokens": metrics["generation_tokens"],
                "prompt_tps": metrics["prompt_tps"],
                "generation_tps": metrics["generation_tps"],
                "longest_prefix_match_tokens": metrics[
                    "longest_prefix_match_tokens"
                ],
                "prefix_reuse_ratio": metrics["prefix_reuse_ratio"],
                "cache_candidate": metrics["cache_candidate"],
                "cache_reuse_enabled": metrics.get("cache_reuse_enabled"),
                "cache_hit": metrics.get("cache_hit"),
                "cache_created": metrics.get("cache_created"),
                "cache_population_mode": metrics.get("cache_population_mode"),
                "cache_scheduled": metrics.get("cache_scheduled"),
                "cache_pending": metrics.get("cache_pending"),
                "cached_prefix_tokens": metrics.get("cached_prefix_tokens"),
                "request_id": metrics["request_id"],
            }
            rows.append(row)
            with output_path.open("a") as f:
                f.write(json.dumps(row) + "\n")
            print(
                "latency_sweep",
                group_index,
                request_index,
                phase,
                row["prompt_tokens"],
                row["actual_prefill_tokens"],
                round(row["cache_prepare_ms"] or 0.0, 2),
                round(row["run_ms"], 2),
                round(row["service_request_ms"] or 0.0, 2),
                round(row["elapsed_ms"], 2),
            )

    phase_rows: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        phase_rows[row["phase"]].append(row)

    for phase in [
        "full_prefill",
        "cache_scheduled",
        "cache_create",
        "cache_hit",
        "cache_other",
    ]:
        bucket = phase_rows.get(phase, [])
        if not bucket:
            continue
        print(
            "summary_phase",
            phase,
            len(bucket),
            "mean_run_ms",
            round(mean([row["run_ms"] for row in bucket]) or 0.0, 2),
            "mean_service_request_ms",
            round(
                mean(
                    [
                        row["service_request_ms"]
                        for row in bucket
                        if row["service_request_ms"] is not None
                    ]
                )
                or 0.0,
                2,
            ),
            "mean_cache_prepare_ms",
            round(
                mean(
                    [
                        row["cache_prepare_ms"]
                        for row in bucket
                        if row["cache_prepare_ms"] is not None
                    ]
                )
                or 0.0,
                2,
            ),
            "mean_elapsed_ms",
            round(mean([row["elapsed_ms"] for row in bucket]) or 0.0, 2),
            "mean_actual_prefill",
            round(mean([row["actual_prefill_tokens"] for row in bucket]) or 0.0, 2),
        )

    print("summary", len(rows), str(output_path))


if __name__ == "__main__":
    main()
