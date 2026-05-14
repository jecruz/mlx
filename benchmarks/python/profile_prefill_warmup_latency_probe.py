#!/usr/bin/env python3
"""Compare first real prompt latency with profile-prefill warmup off vs on."""

from __future__ import annotations

import argparse
import json
import statistics
import time
import urllib.request
import uuid
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


def write_row(path: Path, row: dict[str, Any]) -> None:
    with path.open("a") as f:
        f.write(json.dumps(row, sort_keys=True) + "\n")


def wait_for_warmup(base_url: str, *, timeout_s: float) -> dict[str, Any]:
    deadline = time.time() + timeout_s
    health = request_json("GET", f"{base_url}/health")
    while time.time() < deadline:
        warmup = health.get("warmup") or {}
        if warmup.get("completed") or warmup.get("mode") == "off":
            return health
        if warmup.get("error"):
            raise RuntimeError(f"warmup failed: {warmup['error']}")
        time.sleep(0.25)
        health = request_json("GET", f"{base_url}/health")
    raise RuntimeError(f"timed out waiting for warmup: {health.get('warmup')}")


def reload_engine(
    base_url: str,
    *,
    warmup_profile_prefill: bool,
    warmup_prompt_tokens: str,
) -> tuple[dict[str, Any], float]:
    started = time.perf_counter()
    response = request_json(
        "POST",
        f"{base_url}/engine/reload",
        {
            "warmup_prompt_tokens": warmup_prompt_tokens,
            "warmup_profile_prefill": warmup_profile_prefill,
            "warmup_mode": "async",
        },
    )
    return response, 1e3 * (time.perf_counter() - started)


def completion(base_url: str, *, prompt: str, max_tokens: int) -> dict[str, Any]:
    response = request_json(
        "POST",
        f"{base_url}/v1/completions",
        {
            "model": "mlx-engine-m13",
            "prompt": prompt,
            "max_tokens": max_tokens,
            "policy": "auto",
        },
    )
    metrics = response["engine_metrics"]
    if not response["choices"][0]["text"]:
        raise RuntimeError("first prompt response was empty")
    if not metrics.get("prefill_selection_source"):
        raise RuntimeError(f"response did not report prefill selection: {metrics}")
    return metrics


def build_prompt(*, run_id: str, prompt_repeats: int) -> str:
    return (
        f"M13 profile-prefill warmup latency probe {run_id}.\n"
        "You are measuring the first real long prompt after reload. "
        "Respond with one concise sentence.\n"
        + ("Prompt processing benchmark context with repeated agentic coding details. " * prompt_repeats)
    )


def run_case(
    *,
    base_url: str,
    artifact: Path,
    label: str,
    warmup_profile_prefill: bool,
    warmup_prompt_tokens: str,
    prompt: str,
    max_tokens: int,
    warmup_timeout_s: float,
) -> dict[str, Any]:
    reloaded, reload_elapsed_ms = reload_engine(
        base_url,
        warmup_profile_prefill=warmup_profile_prefill,
        warmup_prompt_tokens=warmup_prompt_tokens,
    )
    health = wait_for_warmup(base_url, timeout_s=warmup_timeout_s)
    request_json(
        "POST",
        f"{base_url}/engine/cache/prune",
        {"target_entries": 0, "clear_mlx_cache": False},
    )
    metrics = completion(base_url, prompt=prompt, max_tokens=max_tokens)
    warmup = health.get("warmup") or {}
    row = {
        "type": "case",
        "created": int(time.time()),
        "case": label,
        "warmup_profile_prefill": warmup_profile_prefill,
        "reload_elapsed_ms": reload_elapsed_ms,
        "warmup": warmup,
        "warmup_results": health.get("warmup_results"),
        "load_ms": health.get("load_ms"),
        "service_request_ms": metrics.get("service_request_ms"),
        "run_ms": metrics.get("run_ms"),
        "actual_prefill_tokens": metrics.get("actual_prefill_tokens"),
        "prompt_tokens_estimate": metrics.get("prompt_tokens_estimate"),
        "prefill_step_size": metrics.get("prefill_step_size"),
        "prefill_selection_source": metrics.get("prefill_selection_source"),
        "prefill_band_min_prompt_tokens": metrics.get("prefill_band_min_prompt_tokens"),
        "prefill_band_max_prompt_tokens": metrics.get("prefill_band_max_prompt_tokens"),
    }
    write_row(artifact, row)
    print(
        "m13_case",
        label,
        "profile_prefill",
        warmup_profile_prefill,
        "warmup_results",
        warmup.get("result_count"),
        "prompt_tokens",
        row["prompt_tokens_estimate"],
        "prefill_step",
        row["prefill_step_size"],
        "service_ms",
        round(float(row["service_request_ms"] or 0.0), 2),
        "actual_prefill",
        row["actual_prefill_tokens"],
        flush=True,
    )
    return row


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    by_case = {}
    for row in rows:
        by_case.setdefault(row["case"], []).append(float(row["service_request_ms"]))
    summary = {
        "type": "summary",
        "created": int(time.time()),
        "cases": {
            case: {
                "count": len(values),
                "mean_service_request_ms": statistics.fmean(values),
                "min_service_request_ms": min(values),
                "max_service_request_ms": max(values),
            }
            for case, values in sorted(by_case.items())
        },
    }
    off = summary["cases"].get("profile_prefill_off", {})
    on = summary["cases"].get("profile_prefill_on", {})
    if off and on:
        off_mean = float(off["mean_service_request_ms"])
        on_mean = float(on["mean_service_request_ms"])
        summary["profile_prefill_delta_ms"] = on_mean - off_mean
        summary["profile_prefill_ratio"] = on_mean / off_mean if off_mean else None
    return summary


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8765")
    parser.add_argument("--output-jsonl", type=Path, default=Path("profile-prefill-warmup-latency.jsonl"))
    parser.add_argument("--warmup-prompt-tokens", default="64,512")
    parser.add_argument(
        "--prompt-repeats",
        type=int,
        default=370,
        help=(
            "Repeated text count. The default targets the long-prompt profile "
            "band for the gpt-oss-20b-MXFP4-Q8 benchmark profile."
        ),
    )
    parser.add_argument("--max-tokens", type=int, default=2)
    parser.add_argument("--rounds", type=int, default=1)
    parser.add_argument("--warmup-timeout-s", type=float, default=240.0)
    args = parser.parse_args()

    base_url = args.base_url.rstrip("/")
    args.output_jsonl.write_text("")
    prompt = build_prompt(run_id=uuid.uuid4().hex[:8], prompt_repeats=args.prompt_repeats)
    rows = []
    for round_index in range(args.rounds):
        rows.append(
            run_case(
                base_url=base_url,
                artifact=args.output_jsonl,
                label="profile_prefill_off",
                warmup_profile_prefill=False,
                warmup_prompt_tokens=args.warmup_prompt_tokens,
                prompt=prompt,
                max_tokens=args.max_tokens,
                warmup_timeout_s=args.warmup_timeout_s,
            )
        )
        rows.append(
            run_case(
                base_url=base_url,
                artifact=args.output_jsonl,
                label="profile_prefill_on",
                warmup_profile_prefill=True,
                warmup_prompt_tokens=args.warmup_prompt_tokens,
                prompt=prompt,
                max_tokens=args.max_tokens,
                warmup_timeout_s=args.warmup_timeout_s,
            )
        )
        print("m13_round", round_index + 1, "complete", flush=True)

    summary = summarize(rows)
    write_row(args.output_jsonl, summary)
    print(
        "m13_summary",
        "delta_ms",
        round(float(summary.get("profile_prefill_delta_ms") or 0.0), 2),
        "ratio",
        round(float(summary.get("profile_prefill_ratio") or 0.0), 3),
        args.output_jsonl,
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
