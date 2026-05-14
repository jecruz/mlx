#!/usr/bin/env python3
"""Run resident MLX benchmarks, comparison, and regression gate as one suite."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
import urllib.request
from pathlib import Path
from typing import Any


def run(cmd: list[str], *, cwd: Path) -> None:
    print("suite_cmd", " ".join(cmd), flush=True)
    subprocess.run(cmd, cwd=cwd, check=True)


def request_json(
    method: str,
    url: str,
    payload: dict[str, Any] | None = None,
    *,
    timeout: int = 900,
) -> dict[str, Any]:
    data = None
    headers = {}
    if payload is not None:
        data = json.dumps(payload).encode()
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode())


def write_row(path: Path, row: dict[str, Any]) -> None:
    with path.open("a") as f:
        f.write(json.dumps(row, sort_keys=True) + "\n")


def run_lifecycle_reload(
    *,
    base_url: str,
    artifact: Path,
    warmup_prompt_tokens: str,
) -> None:
    artifact.write_text("")
    before = request_json("GET", f"{base_url}/health")
    write_row(
        artifact,
        {
            "type": "health_before_unload",
            "created": int(time.time()),
            "engine_preset": before.get("engine_preset"),
            "loaded": before.get("loaded"),
            "load_ms": before.get("load_ms"),
            "uptime_s": before.get("uptime_s"),
            "warmup_prompt_tokens": before.get("warmup_prompt_tokens"),
            "device": before.get("device"),
            "prefix_cache_policy": before.get("prefix_cache_policy"),
            "prefix_kv_cache": before.get("prefix_kv_cache"),
            "mlx_memory": before.get("mlx_memory"),
        },
    )
    print(
        "suite_cold_health_before",
        before.get("engine_preset"),
        before.get("loaded"),
        before.get("load_ms"),
    )

    unload_started = time.perf_counter()
    unloaded = request_json("POST", f"{base_url}/engine/unload")
    unload_elapsed_ms = 1e3 * (time.perf_counter() - unload_started)
    write_row(
        artifact,
        {
            "type": "unload",
            "created": int(time.time()),
            "elapsed_ms": unload_elapsed_ms,
            "response": unloaded,
        },
    )
    print(
        "suite_cold_unload",
        round(unload_elapsed_ms, 2),
        unloaded.get("loaded"),
        unloaded.get("unload_count"),
    )

    reload_started = time.perf_counter()
    reloaded = request_json(
        "POST",
        f"{base_url}/engine/reload",
        {"warmup_prompt_tokens": warmup_prompt_tokens},
        timeout=1200,
    )
    reload_elapsed_ms = 1e3 * (time.perf_counter() - reload_started)
    write_row(
        artifact,
        {
            "type": "reload",
            "created": int(time.time()),
            "elapsed_ms": reload_elapsed_ms,
            "response": reloaded,
        },
    )
    print(
        "suite_cold_reload",
        round(reload_elapsed_ms, 2),
        round(reloaded.get("load_ms") or 0.0, 2),
        reloaded.get("warmup_prompt_tokens"),
    )

    after = request_json("GET", f"{base_url}/health")
    write_row(
        artifact,
        {
            "type": "health_after_reload",
            "created": int(time.time()),
            "engine_preset": after.get("engine_preset"),
            "loaded": after.get("loaded"),
            "load_ms": after.get("load_ms"),
            "uptime_s": after.get("uptime_s"),
            "warmup_prompt_tokens": after.get("warmup_prompt_tokens"),
            "warmup_results": after.get("warmup_results"),
            "device": after.get("device"),
            "prefix_cache_policy": after.get("prefix_cache_policy"),
            "prefix_kv_cache": after.get("prefix_kv_cache"),
            "mlx_memory": after.get("mlx_memory"),
        },
    )
    print(
        "suite_cold_health_after",
        after.get("engine_preset"),
        after.get("loaded"),
        round(after.get("load_ms") or 0.0, 2),
        after.get("warmup_prompt_tokens"),
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8765")
    parser.add_argument("--output-dir", type=Path, default=Path("."))
    parser.add_argument("--tag", default=None)
    parser.add_argument("--requests", type=int, default=6)
    parser.add_argument("--prefill-runs", type=int, default=5)
    parser.add_argument("--prefix-repeats", type=int, default=24)
    parser.add_argument("--max-tokens", type=int, default=8)
    parser.add_argument("--prefill-max-tokens", type=int, default=4)
    parser.add_argument("--skip-benchmarks", action="store_true")
    parser.add_argument("--skip-compare", action="store_true")
    parser.add_argument("--skip-gate", action="store_true")
    parser.add_argument("--skip-generated-cache-safety", action="store_true")
    parser.add_argument("--skip-generated-cache-edges", action="store_true")
    parser.add_argument("--skip-concurrent-cancel-pressure", action="store_true")
    parser.add_argument("--skip-async-cache-priority", action="store_true")
    parser.add_argument("--generated-cache-long-max-tokens", type=int, default=32)
    parser.add_argument("--generated-cache-stream-max-tokens", type=int, default=12)
    parser.add_argument("--generated-cache-cancel-repeats", type=int, default=96)
    parser.add_argument("--generated-cache-prefill-step-size", type=int, default=16)
    parser.add_argument("--concurrent-cancel-clients", type=int, default=4)
    parser.add_argument("--concurrent-cancel-repeats", type=int, default=128)
    parser.add_argument("--concurrent-cancel-prefill-step-size", type=int, default=16)
    parser.add_argument("--cold-start", action="store_true")
    parser.add_argument("--reload-warmup-prompt-tokens", default="64,512")
    parser.add_argument("--max-cache-hit-service-ms", type=float, default=250.0)
    parser.add_argument("--max-cache-hit-prefill-tokens", type=float, default=16.0)
    parser.add_argument("--max-warm-prefill-service-ms", type=float, default=550.0)
    parser.add_argument("--min-warm-prefill-tokens", type=float, default=500.0)
    parser.add_argument("--max-cold-to-warm-ratio", type=float, default=8.0)
    args = parser.parse_args()

    cwd = Path.cwd()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    tag = args.tag or str(int(time.time()))
    cache_artifact = args.output_dir / f"resident-benchmark-sync-safe-{tag}.jsonl"
    prefill_artifact = args.output_dir / f"resident-prefill-isolation-sync-safe-{tag}.jsonl"
    lifecycle_artifact = args.output_dir / f"resident-cold-start-sync-safe-{tag}.jsonl"

    if args.cold_start:
        run_lifecycle_reload(
            base_url=args.base_url.rstrip("/"),
            artifact=lifecycle_artifact,
            warmup_prompt_tokens=args.reload_warmup_prompt_tokens,
        )

    if not args.skip_benchmarks:
        run(
            [
                sys.executable,
                "benchmarks/python/resident_benchmark_harness.py",
                "--base-url",
                args.base_url,
                "--engine-preset",
                "sync-safe",
                "--reset-cache",
                "--requests",
                str(args.requests),
                "--prefix-repeats",
                str(args.prefix_repeats),
                "--max-tokens",
                str(args.max_tokens),
                "--output-jsonl",
                str(cache_artifact),
            ],
            cwd=cwd,
        )
        run(
            [
                sys.executable,
                "benchmarks/python/resident_benchmark_harness.py",
                "--base-url",
                args.base_url,
                "--mode",
                "prefill-isolation",
                "--engine-preset",
                "sync-safe",
                "--restore-engine-preset",
                "sync-safe",
                "--prefill-runs",
                str(args.prefill_runs),
                "--prefix-repeats",
                str(args.prefix_repeats),
                "--max-tokens",
                str(args.prefill_max_tokens),
                "--output-jsonl",
                str(prefill_artifact),
            ],
            cwd=cwd,
        )

    if not args.skip_compare:
        run(
            [
                sys.executable,
                "benchmarks/python/compare_resident_benchmarks.py",
                str(cache_artifact),
                str(prefill_artifact),
            ],
            cwd=cwd,
        )

    if not args.skip_gate:
        run(
            [
                sys.executable,
                "benchmarks/python/resident_regression_gate.py",
                "--cache-artifact",
                str(cache_artifact),
                "--prefill-artifact",
                str(prefill_artifact),
                "--max-cache-hit-service-ms",
                str(args.max_cache_hit_service_ms),
                "--max-cache-hit-prefill-tokens",
                str(args.max_cache_hit_prefill_tokens),
                "--max-warm-prefill-service-ms",
                str(args.max_warm_prefill_service_ms),
                "--min-warm-prefill-tokens",
                str(args.min_warm_prefill_tokens),
                "--max-cold-to-warm-ratio",
                str(args.max_cold_to_warm_ratio),
            ],
            cwd=cwd,
        )

    if not args.skip_generated_cache_safety:
        run(
            [
                sys.executable,
                "benchmarks/python/generated_prefix_cache_safety_probe.py",
                "--base-url",
                args.base_url,
                "--long-max-tokens",
                str(args.generated_cache_long_max_tokens),
                "--stream-max-tokens",
                str(args.generated_cache_stream_max_tokens),
                "--cancel-repeats",
                str(args.generated_cache_cancel_repeats),
                "--prefill-step-size",
                str(args.generated_cache_prefill_step_size),
            ],
            cwd=cwd,
        )

    if not args.skip_generated_cache_edges:
        run(
            [
                sys.executable,
                "benchmarks/python/generated_prefix_cache_edge_probe.py",
                "--base-url",
                args.base_url,
            ],
            cwd=cwd,
        )

    if not args.skip_concurrent_cancel_pressure:
        run(
            [
                sys.executable,
                "benchmarks/python/concurrent_cancel_pressure_probe.py",
                "--base-url",
                args.base_url,
                "--clients",
                str(args.concurrent_cancel_clients),
                "--cancel-repeats",
                str(args.concurrent_cancel_repeats),
                "--prefill-step-size",
                str(args.concurrent_cancel_prefill_step_size),
            ],
            cwd=cwd,
        )

    if not args.skip_async_cache_priority:
        run(
            [
                sys.executable,
                "benchmarks/python/async_cache_priority_probe.py",
                "--base-url",
                args.base_url,
            ],
            cwd=cwd,
        )

    if args.cold_start:
        print(
            "suite_result PASS",
            cache_artifact,
            prefill_artifact,
            lifecycle_artifact,
            "generated_cache_safety=",
            not args.skip_generated_cache_safety,
            "generated_cache_edges=",
            not args.skip_generated_cache_edges,
            "concurrent_cancel_pressure=",
            not args.skip_concurrent_cancel_pressure,
            "async_cache_priority=",
            not args.skip_async_cache_priority,
        )
    else:
        print(
            "suite_result PASS",
            cache_artifact,
            prefill_artifact,
            "generated_cache_safety=",
            not args.skip_generated_cache_safety,
            "generated_cache_edges=",
            not args.skip_generated_cache_edges,
            "concurrent_cancel_pressure=",
            not args.skip_concurrent_cancel_pressure,
            "async_cache_priority=",
            not args.skip_async_cache_priority,
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
