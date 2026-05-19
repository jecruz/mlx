#!/usr/bin/env python3
"""Live resident-engine model reload/swap safety probe."""

from __future__ import annotations

import argparse
import json
import time
import urllib.request
from pathlib import Path
from typing import Any


def request_json(
    method: str,
    url: str,
    payload: dict[str, Any] | None = None,
    *,
    timeout: int = 1200,
) -> dict[str, Any]:
    data = None
    headers = {}
    if payload is not None:
        data = json.dumps(payload).encode()
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode())


def wait_ready(base_url: str, *, timeout_s: float) -> dict[str, Any]:
    deadline = time.time() + timeout_s
    last_health: dict[str, Any] = {}
    while time.time() < deadline:
        last_health = request_json("GET", f"{base_url}/health", timeout=10)
        warmup = last_health.get("warmup") or {}
        if (
            last_health.get("ok")
            and last_health.get("loaded", True)
            and not warmup.get("running")
            and not warmup.get("error")
        ):
            return last_health
        if warmup.get("error"):
            raise RuntimeError(f"warmup failed: {warmup['error']}")
        time.sleep(0.5)
    raise RuntimeError(f"timed out waiting for ready health: {last_health}")


def model_from_status(status: dict[str, Any]) -> str | None:
    model = status.get("model")
    return str(model) if model else None


def summarize_status(status: dict[str, Any]) -> dict[str, Any]:
    return {
        "ok": status.get("ok"),
        "loaded": status.get("loaded", True),
        "model": status.get("model"),
        "backend": status.get("backend"),
        "engine_preset": status.get("engine_preset"),
        "runtime_profile": status.get("runtime_profile"),
        "reload_count": status.get("reload_count"),
        "unload_count": status.get("unload_count"),
        "last_reload_error": status.get("last_reload_error"),
        "warmup_prompt_tokens": status.get("warmup_prompt_tokens"),
        "warmup": status.get("warmup"),
        "device": status.get("device"),
        "mlx_memory": status.get("mlx_memory"),
    }


def summarize_health(health: dict[str, Any]) -> dict[str, Any]:
    return {
        "ok": health.get("ok"),
        "loaded": health.get("loaded", True),
        "model": health.get("model"),
        "backend": health.get("backend"),
        "engine_preset": health.get("engine_preset"),
        "runtime_profile": health.get("runtime_profile"),
        "device": health.get("device"),
        "warmup": health.get("warmup"),
        "mlx_memory": health.get("mlx_memory"),
        "scheduler": health.get("scheduler"),
        "load_ms": health.get("load_ms"),
        "uptime_s": health.get("uptime_s"),
    }


def reload_model(
    base_url: str,
    *,
    model: str,
    warmup_prompt_tokens: str,
    warmup_mode: str,
) -> tuple[dict[str, Any], float]:
    started = time.perf_counter()
    response = request_json(
        "POST",
        f"{base_url}/engine/reload",
        {
            "model": model,
            "warmup_prompt_tokens": warmup_prompt_tokens,
            "warmup_mode": warmup_mode,
        },
    )
    return response, 1e3 * (time.perf_counter() - started)


def completion_probe(base_url: str, *, label: str, max_tokens: int) -> dict[str, Any]:
    started = time.perf_counter()
    response = request_json(
        "POST",
        f"{base_url}/v1/completions",
        {
            "model": f"live-model-swap-{label}",
            "prompt": f"Output only: LIVE_MODEL_SWAP_{label.upper()}_OK\n/no_think",
            "max_tokens": max_tokens,
            "runtime_profile": "interactive",
            "stop": ["<|endoftext|>", "<|im_start|>", "<|im_end|>"],
        },
    )
    wall_ms = 1e3 * (time.perf_counter() - started)
    metrics = response.get("engine_metrics") or {}
    text = ((response.get("choices") or [{}])[0].get("text") or "").strip()
    return {
        "label": label,
        "wall_ms": wall_ms,
        "text": text,
        "finish_reason": (response.get("choices") or [{}])[0].get("finish_reason"),
        "metrics": metrics,
    }


def validate_stage(
    *,
    stage: str,
    expected_model: str,
    status: dict[str, Any],
    health: dict[str, Any],
    completion: dict[str, Any],
) -> list[str]:
    failures = []
    observed_model = model_from_status(status)
    if observed_model != expected_model:
        failures.append(f"{stage}: model mismatch {observed_model!r} != {expected_model!r}")
    if not status.get("loaded", True):
        failures.append(f"{stage}: engine status is not loaded")
    if not health.get("loaded", True):
        failures.append(f"{stage}: health reports unloaded")
    default_device = str((health.get("device") or {}).get("default_device", ""))
    if "gpu" not in default_device:
        failures.append(f"{stage}: health default device is not gpu: {default_device!r}")
    if not completion.get("text"):
        failures.append(f"{stage}: completion text is empty")
    metrics = completion.get("metrics") or {}
    if not isinstance(metrics.get("service_request_ms"), int | float):
        failures.append(f"{stage}: service_request_ms missing")
    if not isinstance(metrics.get("active_memory_gb"), int | float):
        failures.append(f"{stage}: active_memory_gb missing")
    return failures


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8773")
    parser.add_argument("--candidate-model", required=True)
    parser.add_argument("--restore-model")
    parser.add_argument("--output-json", type=Path, required=True)
    parser.add_argument("--tag", default="m181-live-model-swap")
    parser.add_argument("--warmup-prompt-tokens", default="64")
    parser.add_argument("--warmup-mode", default="async", choices=["off", "sync", "async"])
    parser.add_argument("--warmup-timeout-s", type=float, default=900.0)
    parser.add_argument("--max-tokens", type=int, default=3)
    parser.add_argument("--fail-on-fail", action="store_true")
    args = parser.parse_args()

    base_url = args.base_url.rstrip("/")
    initial_status = request_json("GET", f"{base_url}/engine")
    restore_model = args.restore_model or model_from_status(initial_status)
    if not restore_model:
        raise RuntimeError("restore model is required when /engine has no model")

    stages: list[dict[str, Any]] = []
    failures: list[str] = []

    candidate_status, candidate_reload_ms = reload_model(
        base_url,
        model=args.candidate_model,
        warmup_prompt_tokens=args.warmup_prompt_tokens,
        warmup_mode=args.warmup_mode,
    )
    candidate_health = wait_ready(base_url, timeout_s=args.warmup_timeout_s)
    candidate_completion = completion_probe(
        base_url,
        label="candidate",
        max_tokens=args.max_tokens,
    )
    failures.extend(
        validate_stage(
            stage="candidate",
            expected_model=args.candidate_model,
            status=candidate_status,
            health=candidate_health,
            completion=candidate_completion,
        )
    )
    stages.append(
        {
            "stage": "candidate",
            "model": args.candidate_model,
            "reload_elapsed_ms": candidate_reload_ms,
            "status": summarize_status(candidate_status),
            "health": summarize_health(candidate_health),
            "completion": candidate_completion,
        }
    )

    restore_status, restore_reload_ms = reload_model(
        base_url,
        model=restore_model,
        warmup_prompt_tokens=args.warmup_prompt_tokens,
        warmup_mode=args.warmup_mode,
    )
    restore_health = wait_ready(base_url, timeout_s=args.warmup_timeout_s)
    restore_completion = completion_probe(
        base_url,
        label="restore",
        max_tokens=args.max_tokens,
    )
    failures.extend(
        validate_stage(
            stage="restore",
            expected_model=restore_model,
            status=restore_status,
            health=restore_health,
            completion=restore_completion,
        )
    )
    stages.append(
        {
            "stage": "restore",
            "model": restore_model,
            "reload_elapsed_ms": restore_reload_ms,
            "status": summarize_status(restore_status),
            "health": summarize_health(restore_health),
            "completion": restore_completion,
        }
    )

    output = {
        "type": "live_model_swap_probe",
        "tag": args.tag,
        "base_url": base_url,
        "verdict": "PASS" if not failures else "FAIL",
        "readiness": "live-model-swap-safe" if not failures else "not-ready",
        "initial_model": model_from_status(initial_status),
        "candidate_model": args.candidate_model,
        "restore_model": restore_model,
        "warmup_prompt_tokens": args.warmup_prompt_tokens,
        "warmup_mode": args.warmup_mode,
        "stages": stages,
        "failures": failures,
    }
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n")
    print(
        "live_model_swap_probe",
        output["verdict"],
        output["readiness"],
        "candidate_reload_ms",
        round(candidate_reload_ms, 2),
        "restore_reload_ms",
        round(restore_reload_ms, 2),
        "failures",
        len(failures),
        args.output_json,
    )
    for failure in failures:
        print("failure", failure)
    return 1 if args.fail_on_fail and failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
