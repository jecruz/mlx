#!/usr/bin/env python3
"""Repeated mixed request-profile stress gate for persistent profile bleed."""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import time
import urllib.request
from pathlib import Path
from typing import Any


def request_json(method: str, url: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    data = json.dumps(payload).encode() if payload is not None else None
    headers = {"Content-Type": "application/json"} if payload is not None else {}
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=240) as resp:
        return json.loads(resp.read().decode())


CASES = [
    (
        "first_hit",
        {
            "workload_intent": "first-hit",
            "immediate_second_turn": True,
            "agentic_workload": True,
            "repeated_workspace": True,
        },
        "agent-workspace-first-hit",
    ),
    (
        "low_memory",
        {
            "workload_intent": "low-memory",
            "low_memory": True,
            "agentic_workload": True,
            "repeated_workspace": True,
        },
        "agent-workspace-low-memory",
    ),
    (
        "diagnostics",
        {
            "workload_intent": "diagnostics",
            "diagnostics_workload": True,
        },
        "diagnostics",
    ),
]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8773")
    parser.add_argument("--output-json", type=Path, required=True)
    parser.add_argument("--tag", default="m151-qwen-a3b")
    parser.add_argument("--iterations", type=int, default=8)
    parser.add_argument("--workers", type=int, default=3)
    parser.add_argument("--max-tokens", type=int, default=2)
    parser.add_argument("--fail-on-fail", action="store_true")
    args = parser.parse_args()
    base_url = args.base_url.rstrip("/")

    request_json("POST", f"{base_url}/engine/config", {"runtime_profile": "interactive"})
    failures: list[str] = []
    rows: list[dict[str, Any]] = []

    def run_case(iteration: int, case: tuple[str, dict[str, Any], str]) -> dict[str, Any]:
        name, metadata, expected = case
        response = request_json(
            "POST",
            f"{base_url}/v1/completions",
            {
                "model": "local-mlx",
                "prompt": f"{args.tag} iteration {iteration} metadata {name}. Reply briefly.",
                "max_tokens": args.max_tokens,
                "stream": False,
                **metadata,
            },
        )
        metrics = response["engine_metrics"]
        return {
            "iteration": iteration,
            "case": name,
            "expected_profile": expected,
            "request_runtime_profile": metrics.get("request_runtime_profile"),
            "request_runtime_profile_source": metrics.get("request_runtime_profile_source"),
            "request_runtime_profile_applied": metrics.get("request_runtime_profile_applied"),
            "request_runtime_profile_scoped": metrics.get("request_runtime_profile_scoped"),
            "service_request_ms": metrics.get("service_request_ms"),
        }

    for iteration in range(1, args.iterations + 1):
        before = request_json("GET", f"{base_url}/health").get("runtime_profile")
        with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as executor:
            batch = list(executor.map(lambda case: run_case(iteration, case), CASES))
        after = request_json("GET", f"{base_url}/health").get("runtime_profile")
        for row in batch:
            row["before_runtime_profile"] = before
            row["after_runtime_profile"] = after
            rows.append(row)
            if row["request_runtime_profile"] != row["expected_profile"]:
                failures.append(
                    f"iteration {iteration} {row['case']}: routed {row['request_runtime_profile']!r}"
                )
            if row["request_runtime_profile_source"] != "request_metadata":
                failures.append(
                    f"iteration {iteration} {row['case']}: source {row['request_runtime_profile_source']!r}"
                )
            if row["request_runtime_profile_applied"] is not True:
                failures.append(
                    f"iteration {iteration} {row['case']}: applied {row['request_runtime_profile_applied']!r}"
                )
            if row["request_runtime_profile_scoped"] is not True:
                failures.append(
                    f"iteration {iteration} {row['case']}: scoped {row['request_runtime_profile_scoped']!r}"
                )
        if before != "interactive" or after != "interactive":
            failures.append(f"iteration {iteration}: profile bleed before={before!r} after={after!r}")
            request_json("POST", f"{base_url}/engine/config", {"runtime_profile": "interactive"})
        time.sleep(0.05)

    output = {
        "type": "request_scoped_concurrency_stress",
        "tag": args.tag,
        "base_url": base_url,
        "verdict": "PASS" if not failures else "FAIL",
        "readiness": "request-profile-stress-no-bleed" if not failures else "not-ready",
        "iterations": args.iterations,
        "workers": args.workers,
        "row_count": len(rows),
        "rows": rows,
        "failures": failures,
    }
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n")
    print(
        "request_scoped_concurrency_stress",
        output["verdict"],
        "iterations",
        args.iterations,
        "rows",
        len(rows),
        "failures",
        len(failures),
        args.output_json,
    )
    if args.fail_on_fail and output["verdict"] != "PASS":
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
