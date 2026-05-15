#!/usr/bin/env python3
"""Sweep request split-prefill behavior across repeated-prefix lengths."""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from request_prefix_cache_probe import run_case, write_row


def parse_repeats(raw: str) -> list[int]:
    try:
        values = [int(part.strip()) for part in raw.split(",") if part.strip()]
    except ValueError as exc:
        raise SystemExit(f"invalid --prefix-repeats-list: {raw}") from exc
    if not values or any(value <= 0 for value in values):
        raise SystemExit("--prefix-repeats-list must contain positive integers")
    return values


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8765")
    parser.add_argument(
        "--output-jsonl",
        type=Path,
        default=Path("request-prefix-cache-length-sweep-m19.jsonl"),
    )
    parser.add_argument("--prefix-repeats-list", default="24,60,120")
    parser.add_argument("--max-tokens", type=int, default=4)
    parser.add_argument("--async-wait-timeout-s", type=float, default=45.0)
    parser.add_argument("--async-idle-grace-ms", type=int, default=50)
    args = parser.parse_args()

    base_url = args.base_url.rstrip("/")
    repeats_list = parse_repeats(args.prefix_repeats_list)
    args.output_jsonl.write_text("")
    summaries = []

    for repeats in repeats_list:
        async_case = run_case(
            base_url=base_url,
            artifact=args.output_jsonl,
            mode="async",
            repeats=repeats,
            max_tokens=args.max_tokens,
            async_wait_timeout_s=args.async_wait_timeout_s,
            async_idle_grace_ms=args.async_idle_grace_ms,
        )
        request_case = run_case(
            base_url=base_url,
            artifact=args.output_jsonl,
            mode="request",
            repeats=repeats,
            max_tokens=args.max_tokens,
            async_wait_timeout_s=args.async_wait_timeout_s,
            async_idle_grace_ms=args.async_idle_grace_ms,
        )
        async_populate = async_case["populate_service_request_ms"]
        request_populate = request_case["populate_service_request_ms"]
        improvement_ms = async_populate - request_populate
        async_tokens = async_case["rows"][1]["actual_prefill_tokens"]
        request_tokens = request_case["rows"][1]["actual_prefill_tokens"]
        summary = {
            "type": "length_summary",
            "created": int(time.time()),
            "prefix_repeats": repeats,
            "async_populate_service_request_ms": async_populate,
            "request_populate_service_request_ms": request_populate,
            "populate_request_vs_async_improvement_ms": improvement_ms,
            "async_populate_actual_prefill_tokens": async_tokens,
            "request_populate_actual_prefill_tokens": request_tokens,
            "async_hit_service_request_ms": async_case["hit_service_request_ms"],
            "request_hit_service_request_ms": request_case["hit_service_request_ms"],
            "request_populate_cache_prepare_ms": request_case[
                "populate_cache_prepare_ms"
            ],
        }
        summaries.append(summary)
        write_row(args.output_jsonl, summary)
        print(
            "m19_length",
            repeats,
            "async_populate_ms",
            round(async_populate, 2),
            "request_populate_ms",
            round(request_populate, 2),
            "delta_ms",
            round(improvement_ms, 2),
            "async_prefill",
            async_tokens,
            "request_prefill",
            request_tokens,
            flush=True,
        )

    best = max(
        summaries,
        key=lambda row: row["populate_request_vs_async_improvement_ms"],
    )
    final = {
        "type": "summary",
        "created": int(time.time()),
        "lengths": repeats_list,
        "best_prefix_repeats": best["prefix_repeats"],
        "best_populate_request_vs_async_improvement_ms": best[
            "populate_request_vs_async_improvement_ms"
        ],
        "rows": summaries,
    }
    write_row(args.output_jsonl, final)
    print(
        "m19_summary",
        "best_repeats",
        final["best_prefix_repeats"],
        "best_delta_ms",
        round(final["best_populate_request_vs_async_improvement_ms"], 2),
        args.output_jsonl,
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
