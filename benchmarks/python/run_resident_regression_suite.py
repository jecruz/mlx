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

from summarize_resident_suite_manifest import print_manifest_summary


ACTIVE_SUITE_CONTEXT: dict[str, Any] | None = None
ACTIVE_PRINT_MANIFEST_SUMMARY = False


def run(cmd: list[str], *, cwd: Path) -> None:
    print("suite_cmd", " ".join(cmd), flush=True)
    try:
        subprocess.run(cmd, cwd=cwd, check=True)
    except subprocess.CalledProcessError as exc:
        if ACTIVE_SUITE_CONTEXT is not None:
            write_suite_manifest(
                verdict="FAIL",
                failure={
                    "type": "subprocess",
                    "command": cmd,
                    "returncode": exc.returncode,
                },
                **ACTIVE_SUITE_CONTEXT,
            )
            print(
                "suite_result FAIL",
                "returncode=",
                exc.returncode,
                "suite_manifest=",
                ACTIVE_SUITE_CONTEXT["suite_manifest"],
            )
            if ACTIVE_PRINT_MANIFEST_SUMMARY:
                manifest = read_json_if_exists(ACTIVE_SUITE_CONTEXT["suite_manifest"])
                if manifest is not None:
                    print_manifest_summary(manifest)
        raise SystemExit(exc.returncode) from None


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


def read_json_if_exists(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    return json.loads(path.read_text())


def apply_threshold_calibration(args: argparse.Namespace) -> None:
    if args.threshold_calibration_json is None:
        return
    payload = json.loads(args.threshold_calibration_json.read_text())
    if payload.get("type") != "resident_threshold_calibration":
        raise ValueError(
            "threshold calibration JSON must have type resident_threshold_calibration"
        )
    thresholds = payload.get("thresholds") or {}
    mapping = {
        "max_cache_hit_service_ms": "max_cache_hit_service_ms",
        "max_cache_hit_prefill_tokens": "max_cache_hit_prefill_tokens",
        "max_cache_create_service_ms": "max_cache_create_service_ms",
        "max_cache_create_prepare_share": "max_cache_create_prepare_share",
        "max_warm_prefill_service_ms": "max_warm_prefill_service_ms",
        "min_warm_prefill_tokens": "min_warm_prefill_tokens",
        "max_cold_to_warm_ratio": "max_cold_to_warm_ratio",
        "min_cache_hit_speedup_vs_full_prefill": (
            "min_cache_hit_speedup_vs_full_prefill"
        ),
        "min_cache_hit_prefill_reduction_vs_full_prefill": (
            "min_cache_hit_prefill_reduction_vs_full_prefill"
        ),
    }
    applied: dict[str, float] = {}
    for key, attr in mapping.items():
        if key not in thresholds:
            continue
        value = thresholds[key]
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(f"invalid calibrated threshold {key}: {value!r}")
        setattr(args, attr, float(value))
        applied[key] = float(value)
    print(
        "suite_threshold_calibration",
        args.threshold_calibration_json,
        "applied",
        json.dumps(applied, sort_keys=True),
        flush=True,
    )


def artifact_entry(path: Path, *, kind: str, enabled: bool) -> dict[str, Any]:
    return {
        "kind": kind,
        "path": str(path),
        "enabled": enabled,
        "exists": path.exists(),
    }


def write_suite_manifest(
    *,
    verdict: str,
    tag: str,
    base_url: str,
    output_dir: Path,
    suite_manifest: Path,
    cache_artifact: Path,
    prefill_artifact: Path,
    gate_artifact: Path,
    lifecycle_artifact: Path,
    dax_repeated_context_artifact: Path,
    dax_repeated_context_jsonl: Path,
    dax_repeated_context_gate_artifact: Path,
    dax_first_hit_summary_artifact: Path,
    dax_first_hit_benchmark_artifact: Path,
    dax_first_hit_jsonl: Path,
    dax_first_hit_gate_artifact: Path,
    steps: dict[str, bool],
    failure: dict[str, Any] | None = None,
) -> None:
    artifacts = {
        "cache": artifact_entry(
            cache_artifact,
            kind="resident_cache_benchmark",
            enabled=steps["benchmarks"],
        ),
        "prefill": artifact_entry(
            prefill_artifact,
            kind="resident_prefill_isolation",
            enabled=steps["benchmarks"],
        ),
        "gate": artifact_entry(
            gate_artifact,
            kind="resident_regression_gate",
            enabled=steps["gate"],
        ),
        "cold_start": artifact_entry(
            lifecycle_artifact,
            kind="resident_cold_start_lifecycle",
            enabled=steps["cold_start"],
        ),
        "dax_repeated_context": artifact_entry(
            dax_repeated_context_artifact,
            kind="dax_repeated_context_bench",
            enabled=steps["dax_repeated_context"],
        ),
        "dax_repeated_context_jsonl": artifact_entry(
            dax_repeated_context_jsonl,
            kind="dax_repeated_context_rows",
            enabled=steps["dax_repeated_context"],
        ),
        "dax_repeated_context_gate": artifact_entry(
            dax_repeated_context_gate_artifact,
            kind="dax_repeated_context_gate",
            enabled=steps["dax_repeated_context"],
        ),
        "dax_first_hit_summary": artifact_entry(
            dax_first_hit_summary_artifact,
            kind="dax_product_first_hit_gate_summary",
            enabled=steps["dax_first_hit"],
        ),
        "dax_first_hit_benchmark": artifact_entry(
            dax_first_hit_benchmark_artifact,
            kind="dax_repeated_context_bench",
            enabled=steps["dax_first_hit"],
        ),
        "dax_first_hit_jsonl": artifact_entry(
            dax_first_hit_jsonl,
            kind="dax_repeated_context_rows",
            enabled=steps["dax_first_hit"],
        ),
        "dax_first_hit_gate": artifact_entry(
            dax_first_hit_gate_artifact,
            kind="dax_first_hit_conversion_gate",
            enabled=steps["dax_first_hit"],
        ),
    }
    suite_report = {
        "type": "resident_regression_suite",
        "verdict": verdict,
        "tag": tag,
        "base_url": base_url,
        "output_dir": str(output_dir),
        "artifacts": artifacts,
        "steps": steps,
        "gate_report": read_json_if_exists(gate_artifact),
        "dax_repeated_context_report": read_json_if_exists(
            dax_repeated_context_artifact
        ),
        "dax_repeated_context_gate_report": read_json_if_exists(
            dax_repeated_context_gate_artifact
        ),
        "dax_first_hit_summary_report": read_json_if_exists(
            dax_first_hit_summary_artifact
        ),
        "dax_first_hit_benchmark_report": read_json_if_exists(
            dax_first_hit_benchmark_artifact
        ),
        "dax_first_hit_gate_report": read_json_if_exists(
            dax_first_hit_gate_artifact
        ),
        "failure": failure,
    }
    suite_manifest.write_text(json.dumps(suite_report, indent=2, sort_keys=True) + "\n")


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
    parser.add_argument("--include-dax-repeated-context", action="store_true")
    parser.add_argument("--include-dax-first-hit", action="store_true")
    parser.add_argument(
        "--dax-dir",
        type=Path,
        default=Path(
            "/Users/jeffreycruz/Development/AI_AGENTS/dax-stereo/packages/coding-agent"
        ),
    )
    parser.add_argument("--dax-repeated-turns", type=int, default=4)
    parser.add_argument("--dax-repeated-shared-repeats", type=int, default=64)
    parser.add_argument("--dax-repeated-max-tokens", type=int, default=4)
    parser.add_argument("--dax-repeated-min-speedup", type=float, default=2.0)
    parser.add_argument("--dax-repeated-max-hit-prefill-tokens", type=int, default=32)
    parser.add_argument("--dax-repeated-min-hit-count", type=int, default=1)
    parser.add_argument(
        "--dax-repeated-min-baseline-prefill-tokens",
        type=int,
        default=512,
    )
    parser.add_argument("--dax-repeated-max-hit-service-ms", type=float, default=400.0)
    parser.add_argument("--dax-first-hit-profile", default="agent-workspace-first-hit")
    parser.add_argument("--dax-first-hit-max-conversion-ratio", type=float, default=0.85)
    parser.add_argument("--dax-first-hit-max-prefill-tokens", type=int, default=32)
    parser.add_argument("--dax-first-hit-min-mature-speedup", type=float, default=2.0)
    parser.add_argument("--print-manifest-summary", action="store_true")
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
    parser.add_argument("--max-cache-create-service-ms", type=float, default=750.0)
    parser.add_argument("--max-cache-create-prepare-share", type=float, default=0.80)
    parser.add_argument("--max-warm-prefill-service-ms", type=float, default=550.0)
    parser.add_argument("--min-warm-prefill-tokens", type=float, default=500.0)
    parser.add_argument("--max-cold-to-warm-ratio", type=float, default=8.0)
    parser.add_argument(
        "--min-cache-hit-speedup-vs-full-prefill",
        type=float,
        default=4.0,
    )
    parser.add_argument(
        "--min-cache-hit-prefill-reduction-vs-full-prefill",
        type=float,
        default=0.90,
    )
    parser.add_argument("--threshold-calibration-json", type=Path)
    args = parser.parse_args()
    apply_threshold_calibration(args)

    cwd = Path.cwd()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    tag = args.tag or str(int(time.time()))
    cache_artifact = args.output_dir / f"resident-benchmark-sync-safe-{tag}.jsonl"
    prefill_artifact = args.output_dir / f"resident-prefill-isolation-sync-safe-{tag}.jsonl"
    lifecycle_artifact = args.output_dir / f"resident-cold-start-sync-safe-{tag}.jsonl"
    gate_artifact = args.output_dir / f"resident-regression-gate-{tag}.json"
    dax_repeated_context_jsonl = (
        args.output_dir / f"dax-repeated-context-{tag}.jsonl"
    )
    dax_repeated_context_artifact = (
        args.output_dir / f"dax-repeated-context-{tag}.json"
    )
    dax_repeated_context_gate_artifact = (
        args.output_dir / f"dax-repeated-context-gate-{tag}.json"
    )
    dax_first_hit_summary_artifact = (
        args.output_dir / f"dax-product-first-hit-summary-{tag}.json"
    )
    dax_first_hit_benchmark_artifact = (
        args.output_dir / f"dax-product-first-hit-{tag}.json"
    )
    dax_first_hit_jsonl = args.output_dir / f"dax-product-first-hit-{tag}.jsonl"
    dax_first_hit_gate_artifact = (
        args.output_dir / f"dax-product-first-hit-gate-{tag}.json"
    )
    suite_manifest = args.output_dir / f"resident-regression-suite-{tag}.json"
    steps = {
        "benchmarks": not args.skip_benchmarks,
        "compare": not args.skip_compare,
        "gate": not args.skip_gate,
        "cold_start": args.cold_start,
        "generated_cache_safety": not args.skip_generated_cache_safety,
        "generated_cache_edges": not args.skip_generated_cache_edges,
        "concurrent_cancel_pressure": not args.skip_concurrent_cancel_pressure,
        "async_cache_priority": not args.skip_async_cache_priority,
        "dax_repeated_context": args.include_dax_repeated_context,
        "dax_first_hit": args.include_dax_first_hit,
    }
    global ACTIVE_SUITE_CONTEXT
    global ACTIVE_PRINT_MANIFEST_SUMMARY
    ACTIVE_SUITE_CONTEXT = {
        "tag": tag,
        "base_url": args.base_url,
        "output_dir": args.output_dir,
        "suite_manifest": suite_manifest,
        "cache_artifact": cache_artifact,
        "prefill_artifact": prefill_artifact,
        "gate_artifact": gate_artifact,
        "lifecycle_artifact": lifecycle_artifact,
        "dax_repeated_context_artifact": dax_repeated_context_artifact,
        "dax_repeated_context_jsonl": dax_repeated_context_jsonl,
        "dax_repeated_context_gate_artifact": dax_repeated_context_gate_artifact,
        "dax_first_hit_summary_artifact": dax_first_hit_summary_artifact,
        "dax_first_hit_benchmark_artifact": dax_first_hit_benchmark_artifact,
        "dax_first_hit_jsonl": dax_first_hit_jsonl,
        "dax_first_hit_gate_artifact": dax_first_hit_gate_artifact,
        "steps": steps,
    }
    ACTIVE_PRINT_MANIFEST_SUMMARY = args.print_manifest_summary

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
                "--output-json",
                str(gate_artifact),
                "--max-cache-hit-service-ms",
                str(args.max_cache_hit_service_ms),
                "--max-cache-hit-prefill-tokens",
                str(args.max_cache_hit_prefill_tokens),
                "--max-cache-create-service-ms",
                str(args.max_cache_create_service_ms),
                "--max-cache-create-prepare-share",
                str(args.max_cache_create_prepare_share),
                "--max-warm-prefill-service-ms",
                str(args.max_warm_prefill_service_ms),
                "--min-warm-prefill-tokens",
                str(args.min_warm_prefill_tokens),
                "--max-cold-to-warm-ratio",
                str(args.max_cold_to_warm_ratio),
                "--min-cache-hit-speedup-vs-full-prefill",
                str(args.min_cache_hit_speedup_vs_full_prefill),
                "--min-cache-hit-prefill-reduction-vs-full-prefill",
                str(args.min_cache_hit_prefill_reduction_vs_full_prefill),
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

    if args.include_dax_repeated_context:
        run(
            [
                sys.executable,
                "benchmarks/python/dax_repeated_context_bench.py",
                "--base-url",
                args.base_url,
                "--dax-dir",
                str(args.dax_dir),
                "--output-jsonl",
                str(dax_repeated_context_jsonl),
                "--output-json",
                str(dax_repeated_context_artifact),
                "--turns",
                str(args.dax_repeated_turns),
                "--shared-repeats",
                str(args.dax_repeated_shared_repeats),
                "--max-tokens",
                str(args.dax_repeated_max_tokens),
                "--min-speedup",
                str(args.dax_repeated_min_speedup),
                "--max-hit-prefill-tokens",
                str(args.dax_repeated_max_hit_prefill_tokens),
                "--fail-on-fail",
            ],
            cwd=cwd,
        )
        run(
            [
                sys.executable,
                "benchmarks/python/dax_repeated_context_gate.py",
                str(dax_repeated_context_artifact),
                "--output-json",
                str(dax_repeated_context_gate_artifact),
                "--min-hit-count",
                str(args.dax_repeated_min_hit_count),
                "--min-speedup",
                str(args.dax_repeated_min_speedup),
                "--min-baseline-prefill-tokens",
                str(args.dax_repeated_min_baseline_prefill_tokens),
                "--max-hit-prefill-tokens",
                str(args.dax_repeated_max_hit_prefill_tokens),
                "--max-hit-service-ms",
                str(args.dax_repeated_max_hit_service_ms),
                "--fail-on-fail",
            ],
            cwd=cwd,
        )

    if args.include_dax_first_hit:
        run(
            [
                sys.executable,
                "benchmarks/python/dax_product_first_hit_gate.py",
                "--base-url",
                args.base_url,
                "--dax-dir",
                str(args.dax_dir),
                "--output-dir",
                str(args.output_dir),
                "--tag",
                tag,
                "--dax-profile",
                args.dax_first_hit_profile,
                "--turns",
                str(args.dax_repeated_turns),
                "--shared-repeats",
                str(args.dax_repeated_shared_repeats),
                "--max-tokens",
                str(args.dax_repeated_max_tokens),
                "--max-conversion-prefill-tokens",
                str(args.dax_first_hit_max_prefill_tokens),
                "--max-conversion-ratio",
                str(args.dax_first_hit_max_conversion_ratio),
                "--min-mature-hit-speedup",
                str(args.dax_first_hit_min_mature_speedup),
                "--max-mature-hit-prefill-tokens",
                str(args.dax_repeated_max_hit_prefill_tokens),
                "--fail-on-fail",
            ],
            cwd=cwd,
        )

    write_suite_manifest(verdict="PASS", failure=None, **ACTIVE_SUITE_CONTEXT)
    if args.print_manifest_summary:
        manifest = read_json_if_exists(suite_manifest)
        if manifest is not None:
            print_manifest_summary(manifest)

    if args.cold_start:
        print(
            "suite_result PASS",
            cache_artifact,
            prefill_artifact,
            lifecycle_artifact,
            "gate_artifact=",
            gate_artifact,
            "suite_manifest=",
            suite_manifest,
            "generated_cache_safety=",
            not args.skip_generated_cache_safety,
            "generated_cache_edges=",
            not args.skip_generated_cache_edges,
            "concurrent_cancel_pressure=",
            not args.skip_concurrent_cancel_pressure,
            "async_cache_priority=",
            not args.skip_async_cache_priority,
            "dax_repeated_context=",
            args.include_dax_repeated_context,
            "dax_first_hit=",
            args.include_dax_first_hit,
        )
    else:
        print(
            "suite_result PASS",
            cache_artifact,
            prefill_artifact,
            "gate_artifact=",
            gate_artifact,
            "suite_manifest=",
            suite_manifest,
            "generated_cache_safety=",
            not args.skip_generated_cache_safety,
            "generated_cache_edges=",
            not args.skip_generated_cache_edges,
            "concurrent_cancel_pressure=",
            not args.skip_concurrent_cancel_pressure,
            "async_cache_priority=",
            not args.skip_async_cache_priority,
            "dax_repeated_context=",
            args.include_dax_repeated_context,
            "dax_first_hit=",
            args.include_dax_first_hit,
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
