#!/usr/bin/env python3
"""Collect comparable resident MLX benchmark evidence in one JSONL artifact."""

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


def request_json(
    method: str,
    url: str,
    payload: dict[str, Any] | None = None,
    *,
    timeout: int = 240,
) -> dict[str, Any]:
    data = None
    headers = {}
    if payload is not None:
        data = json.dumps(payload).encode()
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode())


def request_text(
    method: str,
    url: str,
    payload: dict[str, Any] | None = None,
    *,
    timeout: int = 240,
) -> str:
    data = None
    headers = {}
    if payload is not None:
        data = json.dumps(payload).encode()
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode()


def sse_json_events(text: str) -> list[dict[str, Any]]:
    events = []
    for line in text.splitlines():
        if not line.startswith("data: ") or line == "data: [DONE]":
            continue
        events.append(json.loads(line.removeprefix("data: ")))
    return events


def final_engine_metrics_from_sse(text: str) -> dict[str, Any]:
    for event in reversed(sse_json_events(text)):
        metrics = event.get("engine_metrics")
        if metrics is not None:
            return metrics
    raise AssertionError("expected final SSE event with engine_metrics")


def write_row(path: Path, row: dict[str, Any]) -> None:
    with path.open("a") as f:
        f.write(json.dumps(row, sort_keys=True) + "\n")


def state_summary(health: dict[str, Any]) -> dict[str, Any]:
    return {
        "engine_preset": health.get("engine_preset"),
        "device": health.get("device", {}).get("default_device"),
        "profile_path": health.get("profile_path"),
        "scheduler": health.get("scheduler"),
        "prefix_kv_cache": health.get("prefix_kv_cache"),
        "prefix_cache_policy": health.get("prefix_cache_policy"),
        "mlx_memory": health.get("mlx_memory"),
    }


def build_shared_prefix(*, run_id: str, repeats: int) -> str:
    stable_context = (
        "System: You are benchmarking a resident MLX local inference engine. "
        "Keep answers short. Stable repo context includes scheduler telemetry, "
        "prefix cache reuse, streaming latency, config presets, and MLX memory "
        "pressure policy. "
    )
    repeated = (
        "Stable coding-agent context: repeated system prompts and tool schemas "
        "should be reused safely when cache metadata matches exactly. "
    )
    return f"Benchmark run {run_id}.\n" + stable_context + (repeated * repeats) + "\nUser: "


def build_prefill_prompt(*, run_id: str, repeats: int) -> str:
    stable_context = (
        "System: You are isolating resident MLX prompt prefill timing. "
        "Prefix cache population is disabled for this benchmark, so every "
        "request should prefill the whole prompt. "
    )
    repeated = (
        "Prefill isolation fact: this repeated context intentionally measures "
        "warm-state full-prefill behavior rather than prefix-cache reuse. "
    )
    return (
        f"Prefill isolation run {run_id}.\n"
        + stable_context
        + (repeated * repeats)
        + "\nUser: answer with one concise benchmark metric."
    )


def classify(metrics: dict[str, Any]) -> str:
    if metrics.get("cache_scheduled"):
        return "cache_scheduled"
    if not metrics.get("cache_reuse_enabled"):
        return "full_prefill"
    if metrics.get("cache_created"):
        return "cache_create"
    if metrics.get("cache_hit"):
        return "cache_hit"
    return "cache_other"


def classify_prefill_iteration(index: int) -> str:
    return "prefill_cold" if index == 1 else "prefill_warm"


def metric_row(
    *,
    run_id: str,
    kind: str,
    phase: str,
    index: int,
    elapsed_ms: float,
    metrics: dict[str, Any],
) -> dict[str, Any]:
    return {
        "type": "request",
        "run_id": run_id,
        "kind": kind,
        "phase": phase,
        "index": index,
        "elapsed_ms": elapsed_ms,
        "request_id": metrics.get("request_id"),
        "effective_policy": metrics.get("effective_policy"),
        "prefill_step_size": metrics.get("prefill_step_size"),
        "prompt_tokens": metrics.get("prompt_tokens"),
        "actual_prefill_tokens": metrics.get("actual_prefill_tokens"),
        "generation_tokens": metrics.get("generation_tokens"),
        "run_ms": metrics.get("run_ms"),
        "service_request_ms": metrics.get("service_request_ms"),
        "engine_lock_wait_ms": metrics.get("engine_lock_wait_ms"),
        "scheduler_queue_wait_ms": metrics.get("scheduler_queue_wait_ms"),
        "cache_prepare_ms": metrics.get("cache_prepare_ms"),
        "longest_prefix_match_tokens": metrics.get("longest_prefix_match_tokens"),
        "prefix_reuse_ratio": metrics.get("prefix_reuse_ratio"),
        "cache_candidate": metrics.get("cache_candidate"),
        "cache_reuse_enabled": metrics.get("cache_reuse_enabled"),
        "cache_hit": metrics.get("cache_hit"),
        "cache_created": metrics.get("cache_created"),
        "cache_scheduled": metrics.get("cache_scheduled"),
        "cache_pending": metrics.get("cache_pending"),
        "cached_prefix_tokens": metrics.get("cached_prefix_tokens"),
        "cache_exact_match_trimmed": metrics.get("cache_exact_match_trimmed"),
        "cache_population_mode": metrics.get("cache_population_mode"),
        "prompt_progress_events": metrics.get("prompt_progress_events"),
        "prompt_progress_total_tokens": metrics.get("prompt_progress_total_tokens"),
        "prompt_progress_processed_tokens": metrics.get(
            "prompt_progress_processed_tokens"
        ),
        "prompt_progress_complete": metrics.get("prompt_progress_complete"),
        "generated_token_count_recorded": metrics.get(
            "generated_token_count_recorded"
        ),
        "generated_prefix_cache_recorded": metrics.get(
            "generated_prefix_cache_recorded"
        ),
        "generated_prefix_cache_tokens": metrics.get("generated_prefix_cache_tokens"),
        "stream_first_token_ms": metrics.get("stream_first_token_ms"),
        "stream_mean_token_gap_ms": metrics.get("stream_mean_token_gap_ms"),
        "stream_token_events": metrics.get("stream_token_events"),
        "prompt_tps": metrics.get("prompt_tps"),
        "generation_tps": metrics.get("generation_tps"),
    }


def fmean(rows: list[dict[str, Any]], key: str) -> float | None:
    values = [float(row[key]) for row in rows if row.get(key) is not None]
    return statistics.fmean(values) if values else None


def summarize(run_id: str, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    summaries = []
    phase_rows: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        phase_rows[row["phase"]].append(row)

    for phase, bucket in sorted(phase_rows.items()):
        summaries.append(
            {
                "type": "summary",
                "run_id": run_id,
                "phase": phase,
                "count": len(bucket),
                "mean_elapsed_ms": fmean(bucket, "elapsed_ms"),
                "mean_run_ms": fmean(bucket, "run_ms"),
                "mean_service_request_ms": fmean(bucket, "service_request_ms"),
                "mean_cache_prepare_ms": fmean(bucket, "cache_prepare_ms"),
                "mean_actual_prefill_tokens": fmean(bucket, "actual_prefill_tokens"),
                "mean_stream_first_token_ms": fmean(bucket, "stream_first_token_ms"),
                "mean_stream_gap_ms": fmean(bucket, "stream_mean_token_gap_ms"),
            }
        )
    return summaries


def apply_config(
    *,
    base_url: str,
    output_path: Path,
    run_id: str,
    payload: dict[str, Any],
    label: str,
) -> dict[str, Any]:
    config = request_json("POST", f"{base_url}/engine/config", payload)
    write_row(
        output_path,
        {
            "type": label,
            "run_id": run_id,
            "payload": payload,
            "response": config,
        },
    )
    print(label, payload, sorted(config["changes"].keys()))
    return config


def prune_cache(
    *,
    base_url: str,
    output_path: Path,
    run_id: str,
    label: str,
) -> dict[str, Any]:
    prune = request_json(
        "POST",
        f"{base_url}/engine/cache/prune",
        {"target_entries": 0, "clear_mlx_cache": True},
    )
    write_row(
        output_path,
        {"type": label, "run_id": run_id, "response": prune},
    )
    print(label, prune["before_entries"], prune["after_entries"])
    return prune


def run_prefill_isolation(
    *,
    base_url: str,
    output_path: Path,
    run_id: str,
    args: argparse.Namespace,
) -> None:
    config_payload: dict[str, Any] = {"prefix_cache_population_mode": "off"}
    if args.engine_preset:
        config_payload["engine_preset"] = args.engine_preset
    apply_config(
        base_url=base_url,
        output_path=output_path,
        run_id=run_id,
        payload=config_payload,
        label="prefill_config_apply",
    )
    prune_cache(
        base_url=base_url,
        output_path=output_path,
        run_id=run_id,
        label="prefill_cache_prune",
    )

    health_start = request_json("GET", f"{base_url}/health")
    write_row(
        output_path,
        {
            "type": "health_start",
            "run_id": run_id,
            "created": int(time.time()),
            **state_summary(health_start),
        },
    )

    prompt = build_prefill_prompt(run_id=run_id, repeats=args.prefix_repeats)
    request_rows = []
    for index in range(1, args.prefill_runs + 1):
        started = time.perf_counter()
        response = request_json(
            "POST",
            f"{base_url}/v1/completions",
            {
                "model": "resident-mlx",
                "prompt": prompt,
                "max_tokens": args.max_tokens,
                "policy": args.policy,
            },
        )
        elapsed_ms = 1e3 * (time.perf_counter() - started)
        metrics = response["engine_metrics"]
        row = metric_row(
            run_id=run_id,
            kind="prefill_completion",
            phase=classify_prefill_iteration(index),
            index=index,
            elapsed_ms=elapsed_ms,
            metrics=metrics,
        )
        request_rows.append(row)
        write_row(output_path, row)
        print(
            "prefill_request",
            index,
            row["phase"],
            row["prompt_tokens"],
            row["actual_prefill_tokens"],
            row["cache_reuse_enabled"],
            round(row["service_request_ms"] or 0.0, 2),
            round(row["prompt_tps"] or 0.0, 2),
        )

    for summary in summarize(run_id, request_rows):
        write_row(output_path, summary)
        print(
            "prefill_summary",
            summary["phase"],
            summary["count"],
            round(summary["mean_service_request_ms"] or 0.0, 2),
            round(summary["mean_actual_prefill_tokens"] or 0.0, 2),
        )

    if args.restore_engine_preset:
        apply_config(
            base_url=base_url,
            output_path=output_path,
            run_id=run_id,
            payload={"engine_preset": args.restore_engine_preset},
            label="restore_config_apply",
        )

    health_after = request_json("GET", f"{base_url}/health")
    write_row(
        output_path,
        {
            "type": "health_after",
            "run_id": run_id,
            "created": int(time.time()),
            **state_summary(health_after),
        },
    )
    print(
        "prefill_done",
        run_id,
        str(output_path),
        health_after.get("engine_preset"),
        health_after["prefix_cache_policy"]["population_mode"],
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8765")
    parser.add_argument("--output-jsonl", default=None)
    parser.add_argument(
        "--mode",
        choices=("standard", "prefill-isolation"),
        default="standard",
    )
    parser.add_argument("--engine-preset", default=None)
    parser.add_argument("--prefix-cache-max-entries", type=int, default=None)
    parser.add_argument("--reset-cache", action="store_true")
    parser.add_argument("--requests", type=int, default=6)
    parser.add_argument("--prefill-runs", type=int, default=5)
    parser.add_argument("--restore-engine-preset", default=None)
    parser.add_argument("--prefix-repeats", type=int, default=24)
    parser.add_argument("--max-tokens", type=int, default=8)
    parser.add_argument("--policy", default="auto")
    args = parser.parse_args()

    base_url = args.base_url.rstrip("/")
    run_id = f"{int(time.time())}-{uuid.uuid4().hex[:8]}"
    output_path = Path(args.output_jsonl or f"resident-benchmark-{run_id}.jsonl")
    output_path.write_text("")

    health_before = request_json("GET", f"{base_url}/health")
    write_row(
        output_path,
        {
            "type": "health_before",
            "run_id": run_id,
            "created": int(time.time()),
            **state_summary(health_before),
        },
    )
    print(
        "harness_health_before",
        health_before.get("engine_preset"),
        health_before["device"]["default_device"],
        health_before["prefix_cache_policy"]["population_mode"],
        health_before["prefix_kv_cache"]["max_entries"],
    )

    if args.mode == "prefill-isolation":
        run_prefill_isolation(
            base_url=base_url,
            output_path=output_path,
            run_id=run_id,
            args=args,
        )
        return

    config_payload: dict[str, Any] = {}
    if args.engine_preset:
        config_payload["engine_preset"] = args.engine_preset
    if args.prefix_cache_max_entries is not None:
        config_payload["prefix_cache_max_entries"] = args.prefix_cache_max_entries
    if config_payload:
        config = request_json("POST", f"{base_url}/engine/config", config_payload)
        write_row(
            output_path,
            {
                "type": "config_apply",
                "run_id": run_id,
                "payload": config_payload,
                "response": config,
            },
        )
        print("harness_config_apply", config_payload, sorted(config["changes"].keys()))

    if args.reset_cache:
        prune = request_json(
            "POST",
            f"{base_url}/engine/cache/prune",
            {"target_entries": 0, "clear_mlx_cache": True},
        )
        write_row(
            output_path,
            {"type": "cache_prune", "run_id": run_id, "response": prune},
        )
        print("harness_cache_prune", prune["before_entries"], prune["after_entries"])

    health_start = request_json("GET", f"{base_url}/health")
    write_row(
        output_path,
        {
            "type": "health_start",
            "run_id": run_id,
            "created": int(time.time()),
            **state_summary(health_start),
        },
    )

    shared_prefix = build_shared_prefix(
        run_id=run_id,
        repeats=args.prefix_repeats,
    )
    request_rows = []
    for index in range(1, args.requests + 1):
        prompt = shared_prefix + f"request {index}: name one useful benchmark metric."
        started = time.perf_counter()
        response = request_json(
            "POST",
            f"{base_url}/v1/completions",
            {
                "model": "resident-mlx",
                "prompt": prompt,
                "max_tokens": args.max_tokens,
                "policy": args.policy,
            },
        )
        elapsed_ms = 1e3 * (time.perf_counter() - started)
        metrics = response["engine_metrics"]
        row = metric_row(
            run_id=run_id,
            kind="completion",
            phase=classify(metrics),
            index=index,
            elapsed_ms=elapsed_ms,
            metrics=metrics,
        )
        request_rows.append(row)
        write_row(output_path, row)
        print(
            "harness_request",
            index,
            row["phase"],
            row["prompt_tokens"],
            row["actual_prefill_tokens"],
            round(row["service_request_ms"] or 0.0, 2),
            round(row["cache_prepare_ms"] or 0.0, 2),
        )

    stream_prompt_a = shared_prefix + "stream request A: answer with one word."
    stream_prompt_b = shared_prefix + "stream request B: answer with one word."
    request_text(
        "POST",
        f"{base_url}/v1/completions",
        {
            "model": "resident-mlx",
            "prompt": stream_prompt_a,
            "max_tokens": 4,
            "policy": args.policy,
            "stream": True,
        },
    )
    started = time.perf_counter()
    stream_text = request_text(
        "POST",
        f"{base_url}/v1/completions",
        {
            "model": "resident-mlx",
            "prompt": stream_prompt_b,
            "max_tokens": 4,
            "policy": args.policy,
            "stream": True,
        },
    )
    stream_elapsed_ms = 1e3 * (time.perf_counter() - started)
    stream_metrics = final_engine_metrics_from_sse(stream_text)
    stream_row = metric_row(
        run_id=run_id,
        kind="stream_completion",
        phase=classify(stream_metrics),
        index=args.requests + 1,
        elapsed_ms=stream_elapsed_ms,
        metrics=stream_metrics,
    )
    request_rows.append(stream_row)
    write_row(output_path, stream_row)
    print(
        "harness_stream",
        stream_row["phase"],
        stream_row["actual_prefill_tokens"],
        round(stream_row["stream_first_token_ms"] or 0.0, 2),
        round(stream_row["stream_mean_token_gap_ms"] or 0.0, 2),
    )

    for summary in summarize(run_id, request_rows):
        write_row(output_path, summary)
        print(
            "harness_summary",
            summary["phase"],
            summary["count"],
            round(summary["mean_service_request_ms"] or 0.0, 2),
            round(summary["mean_actual_prefill_tokens"] or 0.0, 2),
        )

    health_after = request_json("GET", f"{base_url}/health")
    write_row(
        output_path,
        {
            "type": "health_after",
            "run_id": run_id,
            "created": int(time.time()),
            **state_summary(health_after),
        },
    )
    print(
        "harness_done",
        run_id,
        str(output_path),
        health_after.get("engine_preset"),
        health_after["prefix_cache_policy"]["population_mode"],
    )


if __name__ == "__main__":
    main()
