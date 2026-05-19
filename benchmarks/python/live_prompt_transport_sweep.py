#!/usr/bin/env python3
"""Run a live prompt-size sweep across resident and CLI transports."""

from __future__ import annotations

import argparse
import json
import subprocess
import time
import urllib.request
from pathlib import Path
from typing import Any


def request_json(method: str, url: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    data = None
    headers = {}
    if payload is not None:
        data = json.dumps(payload).encode()
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    with urllib.request.urlopen(req, timeout=240) as resp:
        return json.loads(resp.read().decode())


def configure_profile(base_url: str, profile: str) -> None:
    request_json("POST", f"{base_url}/engine/config", {"runtime_profile": profile})


def prompt_for_target(target_tokens: int) -> str:
    chunk = (
        "MLX local inference prompt-processing benchmark context with repeated "
        "agent workspace instructions, cache policy notes, product routing, "
        "and performance acceptance criteria. "
    )
    # This is intentionally approximate; the artifact records actual prompt tokens.
    repeats = max(1, target_tokens // 20)
    return (chunk * repeats) + "\nAnswer with one short sentence."


def run_resident(base_url: str, prompt: str, max_tokens: int) -> tuple[dict[str, Any], float, list[str]]:
    payload = {
        "model": "live-prompt-transport-sweep",
        "prompt": prompt,
        "max_tokens": max_tokens,
        "policy": "auto",
    }
    started = time.perf_counter()
    response = request_json("POST", f"{base_url}/v1/completions", payload)
    wall_ms = (time.perf_counter() - started) * 1000.0
    return response, wall_ms, ["POST", f"{base_url}/v1/completions"]


def run_cli(
    *,
    dax_dir: Path,
    base_url: str,
    profile: str,
    prompt: str,
    max_tokens: int,
) -> tuple[dict[str, Any], float, list[str]]:
    cmd = [
        "npx",
        "tsx",
        "src/cli.ts",
        "mlx-engine",
        "--base-url",
        base_url,
        "--profile",
        profile,
        "--prompt",
        prompt,
        "--max-tokens",
        str(max_tokens),
        "--json",
    ]
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
        raise RuntimeError(completed.stderr)
    return json.loads(completed.stdout), wall_ms, cmd


def row_for_response(
    *,
    target_tokens: int,
    transport: str,
    profile: str,
    response: dict[str, Any],
    wall_ms: float,
    command: list[str],
) -> dict[str, Any]:
    metrics = response.get("engine_metrics") or {}
    service_ms = metrics.get("service_request_ms")
    overhead_ms = wall_ms - float(service_ms) if isinstance(service_ms, (int, float)) else None
    return {
        "type": "live_prompt_transport_sweep_row",
        "target_prompt_tokens": target_tokens,
        "transport": transport,
        "runtime_profile": profile,
        "wall_ms": wall_ms,
        "service_request_ms": service_ms,
        "overhead_ms": overhead_ms,
        "actual_prefill_tokens": metrics.get("actual_prefill_tokens"),
        "prompt_tokens": metrics.get("prompt_tokens"),
        "prompt_tokens_estimate": metrics.get("prompt_tokens_estimate"),
        "prompt_progress_last_ms": metrics.get("prompt_progress_last_ms"),
        "peak_memory_gb": metrics.get("peak_memory_gb"),
        "command": command,
        "engine_metrics": metrics,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8773")
    parser.add_argument(
        "--dax-dir",
        type=Path,
        default=Path("/Users/jeffreycruz/Development/AI_AGENTS/dax-stereo/packages/coding-agent"),
    )
    parser.add_argument("--output-jsonl", type=Path, required=True)
    parser.add_argument("--output-json", type=Path, required=True)
    parser.add_argument("--profile", default="agent-workspace-async")
    parser.add_argument("--prompt-tokens", default="512,1024,2048,4096")
    parser.add_argument("--transports", default="resident,cli")
    parser.add_argument("--max-tokens", type=int, default=1)
    parser.add_argument("--fail-on-fail", action="store_true")
    args = parser.parse_args()

    base_url = args.base_url.rstrip("/")
    targets = [int(item) for item in args.prompt_tokens.split(",") if item]
    transports = [item for item in args.transports.split(",") if item]
    configure_profile(base_url, args.profile)
    rows = []
    args.output_jsonl.parent.mkdir(parents=True, exist_ok=True)
    args.output_jsonl.write_text("")
    for target in targets:
        prompt = prompt_for_target(target)
        for transport in transports:
            if transport == "resident":
                response, wall_ms, command = run_resident(base_url, prompt, args.max_tokens)
            elif transport == "cli":
                response, wall_ms, command = run_cli(
                    dax_dir=args.dax_dir,
                    base_url=base_url,
                    profile=args.profile,
                    prompt=prompt,
                    max_tokens=args.max_tokens,
                )
            else:
                raise ValueError(f"unknown transport: {transport}")
            row = row_for_response(
                target_tokens=target,
                transport=transport,
                profile=args.profile,
                response=response,
                wall_ms=wall_ms,
                command=command,
            )
            rows.append(row)
            with args.output_jsonl.open("a") as f:
                f.write(json.dumps(row, sort_keys=True) + "\n")
            print(
                "live_prompt_transport",
                target,
                transport,
                "wall_ms",
                round(wall_ms, 2),
                "service_ms",
                round(float(row["service_request_ms"] or 0.0), 2),
                "prefill",
                row["actual_prefill_tokens"],
                flush=True,
            )

    failures = []
    expected = len(targets) * len(transports)
    if len(rows) != expected:
        failures.append(f"row_count={len(rows)} expected={expected}")
    if any(row.get("service_request_ms") is None for row in rows):
        failures.append("one or more rows missing service_request_ms")
    report = {
        "type": "live_prompt_transport_sweep",
        "verdict": "PASS" if not failures else "FAIL",
        "failures": failures,
        "base_url": base_url,
        "runtime_profile": args.profile,
        "prompt_token_targets": targets,
        "transports": transports,
        "row_count": len(rows),
        "output_jsonl": str(args.output_jsonl),
        "rows": rows,
    }
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print("live_prompt_transport_result", report["verdict"], "rows", len(rows), flush=True)
    return 1 if args.fail_on_fail and failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
