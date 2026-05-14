#!/usr/bin/env python3
"""Start a fresh resident MLX process and run the regression suite against it."""

from __future__ import annotations

import argparse
import json
import os
import signal
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


def write_row(path: Path, row: dict[str, Any]) -> None:
    with path.open("a") as f:
        f.write(json.dumps(row, sort_keys=True) + "\n")


def request_json(url: str, *, timeout: float = 2.0) -> dict[str, Any]:
    with urllib.request.urlopen(url, timeout=timeout) as resp:
        return json.loads(resp.read().decode())


def tail_text(path: Path, lines: int = 80) -> str:
    if not path.exists():
        return ""
    data = path.read_text(errors="replace").splitlines()
    return "\n".join(data[-lines:])


def ensure_port_free(host: str, port: int) -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.5)
        result = sock.connect_ex((host, port))
    if result == 0:
        raise RuntimeError(f"port already has a listener: {host}:{port}")


def stop_process(process: subprocess.Popen[Any], *, timeout_s: float = 15.0) -> int:
    if process.poll() is not None:
        return int(process.returncode or 0)

    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        return int(process.poll() or 0)

    deadline = time.time() + timeout_s
    while time.time() < deadline:
        if process.poll() is not None:
            return int(process.returncode or 0)
        time.sleep(0.2)

    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    process.wait(timeout=5)
    return int(process.returncode or 0)


def wait_for_health(
    *,
    base_url: str,
    process: subprocess.Popen[Any],
    artifact: Path,
    service_log: Path,
    timeout_s: float,
) -> dict[str, Any]:
    started = time.perf_counter()
    last_error = None
    while 1e3 * (time.perf_counter() - started) < timeout_s * 1000:
        if process.poll() is not None:
            raise RuntimeError(
                "resident service exited before health was ready\n"
                f"returncode={process.returncode}\n"
                f"service_log_tail:\n{tail_text(service_log)}"
            )
        try:
            health = request_json(f"{base_url}/health")
            if health.get("ok") and health.get("loaded"):
                elapsed_ms = 1e3 * (time.perf_counter() - started)
                write_row(
                    artifact,
                    {
                        "type": "health_ready",
                        "created": int(time.time()),
                        "elapsed_ms": elapsed_ms,
                        "load_ms": health.get("load_ms"),
                        "startup_timings": health.get("startup_timings"),
                        "device": health.get("device"),
                        "engine_preset": health.get("engine_preset"),
                        "warmup_prompt_tokens": health.get("warmup_prompt_tokens"),
                        "warmup_results": health.get("warmup_results"),
                        "prefix_cache_policy": health.get("prefix_cache_policy"),
                        "prefix_kv_cache": health.get("prefix_kv_cache"),
                        "mlx_memory": health.get("mlx_memory"),
                    },
                )
                print(
                    "process_cold_health_ready",
                    round(elapsed_ms, 2),
                    round(health.get("load_ms") or 0.0, 2),
                    health.get("device"),
                    health.get("warmup_prompt_tokens"),
                    flush=True,
                )
                timings = health.get("startup_timings") or {}
                print(
                    "process_cold_startup_breakdown",
                    round(timings.get("parent_start_to_module_import_ms") or 0.0, 2),
                    round(timings.get("runtime_device_info_ms") or 0.0, 2),
                    round(timings.get("import_mlx_lm_helpers_ms") or 0.0, 2),
                    round(timings.get("model_load_ms") or 0.0, 2),
                    round(timings.get("warmup_ms") or 0.0, 2),
                    round(timings.get("parent_start_to_health_response_ms") or 0.0, 2),
                    flush=True,
                )
                return health
        except (urllib.error.URLError, TimeoutError, ConnectionError) as exc:
            last_error = str(exc)
        time.sleep(0.25)

    raise RuntimeError(
        "timed out waiting for resident service health\n"
        f"last_error={last_error}\n"
        f"service_log_tail:\n{tail_text(service_log)}"
    )


def wait_for_warmup(
    *,
    base_url: str,
    process: subprocess.Popen[Any],
    artifact: Path,
    service_log: Path,
    timeout_s: float,
) -> dict[str, Any]:
    started = time.perf_counter()
    last_health: dict[str, Any] | None = None
    while 1e3 * (time.perf_counter() - started) < timeout_s * 1000:
        if process.poll() is not None:
            raise RuntimeError(
                "resident service exited before warmup completed\n"
                f"returncode={process.returncode}\n"
                f"service_log_tail:\n{tail_text(service_log)}"
            )
        health = request_json(f"{base_url}/health")
        last_health = health
        warmup = health.get("warmup") or {}
        if warmup.get("completed") or warmup.get("mode") == "off":
            elapsed_ms = 1e3 * (time.perf_counter() - started)
            write_row(
                artifact,
                {
                    "type": "warmup_ready",
                    "created": int(time.time()),
                    "elapsed_ms": elapsed_ms,
                    "warmup": warmup,
                    "warmup_results": health.get("warmup_results"),
                    "startup_timings": health.get("startup_timings"),
                },
            )
            print(
                "process_cold_warmup_ready",
                round(elapsed_ms, 2),
                warmup.get("mode"),
                warmup.get("result_count"),
                flush=True,
            )
            return health
        if warmup.get("error"):
            raise RuntimeError(f"resident service warmup failed: {warmup.get('error')}")
        time.sleep(0.25)

    raise RuntimeError(
        "timed out waiting for resident service warmup\n"
        f"last_health={last_health}\n"
        f"service_log_tail:\n{tail_text(service_log)}"
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", required=True)
    parser.add_argument("--profile", default=None)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8766)
    parser.add_argument("--base-url", default=None)
    parser.add_argument("--tag", default=None)
    parser.add_argument("--output-dir", type=Path, default=Path("."))
    parser.add_argument("--python", default=sys.executable)
    parser.add_argument("--engine-preset", default="sync-safe")
    parser.add_argument("--warmup-prompt-tokens", default="64,512")
    parser.add_argument("--warmup-mode", choices=("sync", "async", "off"), default="sync")
    parser.add_argument("--wait-warmup-before-suite", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--health-timeout-s", type=float, default=120.0)
    parser.add_argument("--warmup-timeout-s", type=float, default=120.0)
    parser.add_argument("--requests", type=int, default=6)
    parser.add_argument("--prefill-runs", type=int, default=5)
    parser.add_argument("--prefix-repeats", type=int, default=24)
    parser.add_argument("--max-tokens", type=int, default=8)
    parser.add_argument("--prefill-max-tokens", type=int, default=4)
    parser.add_argument("--max-cache-hit-service-ms", type=float, default=250.0)
    parser.add_argument("--max-cache-hit-prefill-tokens", type=float, default=16.0)
    parser.add_argument("--max-warm-prefill-service-ms", type=float, default=550.0)
    parser.add_argument("--min-warm-prefill-tokens", type=float, default=500.0)
    parser.add_argument("--max-cold-to-warm-ratio", type=float, default=8.0)
    parser.add_argument("--skip-generated-cache-safety", action="store_true")
    parser.add_argument("--generated-cache-long-max-tokens", type=int, default=32)
    parser.add_argument("--generated-cache-stream-max-tokens", type=int, default=12)
    parser.add_argument("--generated-cache-cancel-repeats", type=int, default=96)
    parser.add_argument("--generated-cache-prefill-step-size", type=int, default=16)
    args = parser.parse_args()

    cwd = Path.cwd()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    tag = args.tag or str(int(time.time()))
    base_url = (args.base_url or f"http://{args.host}:{args.port}").rstrip("/")
    artifact = args.output_dir / f"resident-process-cold-start-{tag}.jsonl"
    service_log = args.output_dir / f"resident-process-cold-start-{tag}.log"
    artifact.write_text("")

    ensure_port_free(args.host, args.port)

    service_cmd = [
        args.python,
        "benchmarks/python/resident_mlx_service.py",
        "--model",
        args.model,
        "--host",
        args.host,
        "--port",
        str(args.port),
        "--engine-preset",
        args.engine_preset,
        "--warmup-prompt-tokens",
        args.warmup_prompt_tokens,
        "--warmup-mode",
        args.warmup_mode,
        "--require-gpu",
    ]
    if args.profile:
        service_cmd.extend(["--profile", args.profile])

    parent_started_at_epoch = time.time()
    write_row(
        artifact,
        {
            "type": "process_start",
            "created": int(time.time()),
            "parent_started_at_epoch": parent_started_at_epoch,
            "base_url": base_url,
            "service_cmd": service_cmd,
            "service_log": str(service_log),
        },
    )
    print("process_cold_cmd", " ".join(service_cmd), flush=True)

    log_handle = service_log.open("w")
    process: subprocess.Popen[Any] | None = None
    exit_code = 1
    try:
        env = os.environ.copy()
        env["MLX_ENGINE_PARENT_STARTED_AT_EPOCH"] = str(parent_started_at_epoch)
        process = subprocess.Popen(
            service_cmd,
            cwd=cwd,
            env=env,
            stdout=log_handle,
            stderr=subprocess.STDOUT,
            start_new_session=True,
            text=True,
        )
        write_row(
            artifact,
            {
                "type": "process_spawned",
                "created": int(time.time()),
                "pid": process.pid,
            },
        )
        print("process_cold_spawned", process.pid, flush=True)

        wait_for_health(
            base_url=base_url,
            process=process,
            artifact=artifact,
            service_log=service_log,
            timeout_s=args.health_timeout_s,
        )
        if args.wait_warmup_before_suite:
            wait_for_warmup(
                base_url=base_url,
                process=process,
                artifact=artifact,
                service_log=service_log,
                timeout_s=args.warmup_timeout_s,
            )

        suite_cmd = [
            args.python,
            "benchmarks/python/run_resident_regression_suite.py",
            "--base-url",
            base_url,
            "--tag",
            f"{tag}-suite",
            "--output-dir",
            str(args.output_dir),
            "--requests",
            str(args.requests),
            "--prefill-runs",
            str(args.prefill_runs),
            "--prefix-repeats",
            str(args.prefix_repeats),
            "--max-tokens",
            str(args.max_tokens),
            "--prefill-max-tokens",
            str(args.prefill_max_tokens),
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
            "--generated-cache-long-max-tokens",
            str(args.generated_cache_long_max_tokens),
            "--generated-cache-stream-max-tokens",
            str(args.generated_cache_stream_max_tokens),
            "--generated-cache-cancel-repeats",
            str(args.generated_cache_cancel_repeats),
            "--generated-cache-prefill-step-size",
            str(args.generated_cache_prefill_step_size),
        ]
        if args.skip_generated_cache_safety:
            suite_cmd.append("--skip-generated-cache-safety")

        write_row(
            artifact,
            {
                "type": "suite_start",
                "created": int(time.time()),
                "suite_cmd": suite_cmd,
            },
        )
        print("process_cold_suite_cmd", " ".join(suite_cmd), flush=True)
        suite_t0 = time.perf_counter()
        suite_result = subprocess.run(suite_cmd, cwd=cwd)
        suite_elapsed_ms = 1e3 * (time.perf_counter() - suite_t0)
        write_row(
            artifact,
            {
                "type": "suite_done",
                "created": int(time.time()),
                "elapsed_ms": suite_elapsed_ms,
                "returncode": suite_result.returncode,
            },
        )
        print(
            "process_cold_suite_done",
            suite_result.returncode,
            round(suite_elapsed_ms, 2),
            flush=True,
        )
        exit_code = suite_result.returncode
    finally:
        if process is not None:
            returncode = stop_process(process)
            write_row(
                artifact,
                {
                    "type": "process_exit",
                    "created": int(time.time()),
                    "pid": process.pid,
                    "returncode": returncode,
                },
            )
            print("process_cold_exit", process.pid, returncode, flush=True)
        log_handle.close()

    if exit_code == 0:
        print("process_cold_result PASS", artifact, service_log, flush=True)
    else:
        print("process_cold_result FAIL", exit_code, artifact, service_log, flush=True)
    return exit_code


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        print("process_cold_error", str(exc), file=sys.stderr, flush=True)
        sys.exit(1)
