#!/usr/bin/env python3
"""Measure live tokenized-prompt and prefix fast-path hit rates."""

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


def completion(base_url: str, *, prompt: str, max_tokens: int, runtime_profile: str) -> dict[str, Any]:
    return request_json(
        "POST",
        f"{base_url}/v1/completions",
        {
            "model": "live-cache-hit-instrumentation",
            "prompt": prompt,
            "max_tokens": max_tokens,
            "runtime_profile": runtime_profile,
            "stop": ["<|endoftext|>", "<|im_start|>", "<|im_end|>"],
        },
    )


def row_for_response(
    *,
    scenario: str,
    turn: int,
    prompt: str,
    response: dict[str, Any],
) -> dict[str, Any]:
    metrics = response.get("engine_metrics") or {}
    return {
        "scenario": scenario,
        "turn": turn,
        "prompt_hash": metrics.get("prompt_hash"),
        "finish_reason": ((response.get("choices") or [{}])[0].get("finish_reason")),
        "service_request_ms": metrics.get("service_request_ms"),
        "run_ms": metrics.get("run_ms"),
        "cache_hit": bool(metrics.get("cache_hit")),
        "cache_created": bool(metrics.get("cache_created")),
        "actual_prefill_tokens": metrics.get("actual_prefill_tokens"),
        "prompt_tokens_estimate": metrics.get("prompt_tokens_estimate"),
        "tokenized_prompt_cache_hit": bool(metrics.get("tokenized_prompt_cache_hit")),
        "tokenized_prompt_cache_ms": metrics.get("tokenized_prompt_cache_ms"),
        "prefix_lookup_fast_path": bool(metrics.get("prefix_lookup_fast_path")),
        "prefix_lookup_path": metrics.get("prefix_lookup_path"),
        "prefix_scan_candidates": metrics.get("prefix_scan_candidates"),
        "longest_prefix_match_tokens": metrics.get("longest_prefix_match_tokens"),
        "text": ((response.get("choices") or [{}])[0].get("text") or ""),
        "_prompt": prompt,
    }


def rate(rows: list[dict[str, Any]], key: str, *, skip_first: bool = True) -> float:
    selected = rows[1:] if skip_first else rows
    if not selected:
        return 0.0
    return sum(1 for row in selected if row.get(key)) / len(selected)


def mean_number(rows: list[dict[str, Any]], key: str) -> float | None:
    values = [row.get(key) for row in rows if isinstance(row.get(key), int | float)]
    if not values:
        return None
    return round(sum(values) / len(values), 3)


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    by_scenario: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        by_scenario.setdefault(row["scenario"], []).append(row)
    return {
        scenario: {
            "rows": len(items),
            "cache_hit_rate_after_first": rate(items, "cache_hit"),
            "tokenized_prompt_cache_hit_rate_after_first": rate(
                items, "tokenized_prompt_cache_hit"
            ),
            "prefix_fast_path_rate_after_first": rate(items, "prefix_lookup_fast_path"),
            "mean_service_request_ms": mean_number(items, "service_request_ms"),
            "mean_tokenized_prompt_cache_ms": mean_number(items, "tokenized_prompt_cache_ms"),
            "mean_prefix_scan_candidates": mean_number(items, "prefix_scan_candidates"),
            "max_actual_prefill_tokens": max(
                [
                    row.get("actual_prefill_tokens")
                    for row in items
                    if isinstance(row.get("actual_prefill_tokens"), int | float)
                ],
                default=None,
            ),
        }
        for scenario, items in by_scenario.items()
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8773")
    parser.add_argument("--runtime-profile", default="agent-workspace-first-hit")
    parser.add_argument("--turns", type=int, default=4)
    parser.add_argument("--max-tokens", type=int, default=1)
    parser.add_argument("--output-json", type=Path, required=True)
    parser.add_argument("--tag", default="m212-live-cache-hit-instrumentation")
    parser.add_argument("--fail-on-fail", action="store_true")
    args = parser.parse_args()

    if args.turns < 3:
        raise ValueError("--turns must be at least 3")
    base_url = args.base_url.rstrip("/")
    run_id = str(int(time.time()))
    exact_prompt = (
        f"M212 exact repeated coding-agent context {run_id}. "
        "Measure live tokenized prompt cache and prefix fast path. /no_think"
    )
    near_prefix_base = (
        f"M212 near-prefix coding-agent context {run_id}. "
        "Measure longest-prefix scanning behavior while suffixes change. /no_think"
    )

    configure_profile(base_url, "interactive")
    prune_cache(base_url)
    configure_profile(base_url, args.runtime_profile)

    rows: list[dict[str, Any]] = []
    try:
        for turn in range(1, args.turns + 1):
            response = completion(
                base_url,
                prompt=exact_prompt,
                max_tokens=args.max_tokens,
                runtime_profile=args.runtime_profile,
            )
            rows.append(
                row_for_response(
                    scenario="exact-repeat",
                    turn=turn,
                    prompt=exact_prompt,
                    response=response,
                )
            )
        for turn in range(1, args.turns + 1):
            prompt = f"{near_prefix_base}\nTurn suffix {turn}: keep this suffix unique."
            response = completion(
                base_url,
                prompt=prompt,
                max_tokens=args.max_tokens,
                runtime_profile=args.runtime_profile,
            )
            rows.append(
                row_for_response(
                    scenario="near-prefix",
                    turn=turn,
                    prompt=prompt,
                    response=response,
                )
            )
    finally:
        configure_profile(base_url, "interactive")

    summary = summarize(rows)
    failures: list[str] = []
    exact = summary.get("exact-repeat") or {}
    near = summary.get("near-prefix") or {}
    if exact.get("tokenized_prompt_cache_hit_rate_after_first", 0.0) < 1.0:
        failures.append("exact-repeat tokenized cache hit rate after first is below 1.0")
    if exact.get("prefix_fast_path_rate_after_first", 0.0) < 1.0:
        failures.append("exact-repeat prefix fast-path rate after first is below 1.0")
    if exact.get("cache_hit_rate_after_first", 0.0) <= 0.0:
        failures.append("exact-repeat cache hit rate after first is zero")
    if near.get("prefix_fast_path_rate_after_first", 1.0) > 0.0:
        failures.append("near-prefix unexpectedly used exact prefix fast path")
    if near.get("mean_prefix_scan_candidates") is None:
        failures.append("near-prefix scan candidate metric missing")

    output = {
        "type": "live_cache_hit_instrumentation_report",
        "tag": args.tag,
        "base_url": base_url,
        "runtime_profile": args.runtime_profile,
        "verdict": "PASS" if not failures else "FAIL",
        "readiness": "live-cache-hit-instrumentation-ready" if not failures else "not-ready",
        "summary": summary,
        "rows": rows,
        "failures": failures,
    }
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n")
    print(
        "live_cache_hit_instrumentation_report",
        output["verdict"],
        output["readiness"],
        "rows",
        len(rows),
        "failures",
        len(failures),
        args.output_json,
    )
    for failure in failures:
        print("failure", failure)
    return 1 if args.fail_on_fail and failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
