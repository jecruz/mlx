#!/usr/bin/env python3
"""Measure repeated-prefix opportunities against the resident MLX service."""

from __future__ import annotations

import argparse
import json
import time
import urllib.request
import uuid
from pathlib import Path
from typing import Any


def request_json(method: str, url: str, payload: dict[str, Any] | None = None):
    data = None
    headers = {}
    if payload is not None:
        data = json.dumps(payload).encode()
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    with urllib.request.urlopen(req, timeout=180) as resp:
        return json.loads(resp.read().decode())


def build_agent_prompts(*, run_id: str) -> list[str]:
    system_prefix = f"""\
Benchmark run id: {run_id}

System: You are a local coding assistant connected to a resident MLX engine.
You must answer concisely, preserve exact file paths, and avoid inventing test
results. The user is working on a Mac-local inference stack with Pi, ComfyUI,
and a resident MLX service. Tools available conceptually: read, grep, bash,
redmine, and web search. Current project rules: verify performance claims,
prefer measured evidence, and keep implementation slices small.

Repository context:
- resident service exposes /health, /metrics, /generate, /v1/completions,
  /v1/chat/completions, /engine, /engine/reload, and /engine/unload.
- current model is gpt-oss-20b-MXFP4-Q8.
- current prefill policies are memory_saver=512 and throughput_default=2048.
- next engineering direction is prefix-cache instrumentation before real KV reuse.

User task:
"""
    tasks = [
        "Summarize why prefix reuse matters for coding-agent prompts.",
        "List the next two implementation checks before block KV reuse.",
        "Explain why continuous batching should wait until prefix metrics exist.",
        "Describe how Pi and ComfyUI benefit from resident inference.",
        "Give one risk when caching prompts across tool-augmented requests.",
        "Define the acceptance criteria for a prefix-cache implementation.",
    ]
    return [system_prefix + task for task in tasks]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8765")
    parser.add_argument("--output-jsonl", default="prefix-opportunity-sweep.jsonl")
    parser.add_argument("--max-tokens", type=int, default=4)
    parser.add_argument("--policy", default="auto")
    parser.add_argument(
        "--run-id",
        default=None,
        help="Unique run identifier inserted into the shared prefix.",
    )
    args = parser.parse_args()

    base_url = args.base_url.rstrip("/")
    output_path = Path(args.output_jsonl)
    run_id = args.run_id or f"{int(time.time())}-{uuid.uuid4().hex[:8]}"
    prompts = build_agent_prompts(run_id=run_id)

    rows = []
    for idx, prompt in enumerate(prompts, start=1):
        started = time.time()
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
        elapsed_ms = 1e3 * (time.time() - started)
        metrics = response["engine_metrics"]
        row = {
            "index": idx,
            "elapsed_ms": elapsed_ms,
            "prompt_tokens": metrics["prompt_tokens"],
            "generation_tokens": metrics["generation_tokens"],
            "effective_policy": metrics["effective_policy"],
            "prefill_step_size": metrics["prefill_step_size"],
            "prompt_tps": metrics["prompt_tps"],
            "run_ms": metrics["run_ms"],
            "longest_prefix_match_tokens": metrics["longest_prefix_match_tokens"],
            "prefix_reuse_ratio": metrics["prefix_reuse_ratio"],
            "estimated_recompute_tokens": metrics["estimated_recompute_tokens"],
            "cache_candidate": metrics["cache_candidate"],
            "cache_reuse_enabled": metrics.get("cache_reuse_enabled"),
            "cache_hit": metrics.get("cache_hit"),
            "cache_created": metrics.get("cache_created"),
            "cache_prepare_ms": metrics.get("cache_prepare_ms"),
            "cached_prefix_tokens": metrics.get("cached_prefix_tokens"),
            "actual_prefill_tokens": metrics.get("actual_prefill_tokens"),
            "matched_request_id": metrics["matched_request_id"],
            "request_id": metrics["request_id"],
        }
        rows.append(row)
        with output_path.open("a") as f:
            f.write(json.dumps(row) + "\n")
        print(
            "prefix_sweep",
            idx,
            row["prompt_tokens"],
            row["longest_prefix_match_tokens"],
            round(row["prefix_reuse_ratio"], 3),
            row["cache_candidate"],
            row["cache_reuse_enabled"],
            row["cache_hit"],
            row["cache_created"],
            round(row["cache_prepare_ms"] or 0.0, 2),
            row["actual_prefill_tokens"],
        )

    cache_candidates = sum(1 for row in rows if row["cache_candidate"])
    mean_reuse = sum(row["prefix_reuse_ratio"] for row in rows) / len(rows)
    print(
        "summary",
        len(rows),
        cache_candidates,
        round(mean_reuse, 3),
        str(output_path),
    )


if __name__ == "__main__":
    main()
