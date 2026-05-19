#!/usr/bin/env python3
"""Run the focused live product regression suite for the resident MLX engine."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any


def run(cmd: list[str], *, cwd: Path) -> None:
    print("live_product_suite_cmd", " ".join(cmd), flush=True)
    subprocess.run(cmd, cwd=cwd, check=True)


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text())


def evidence_entry(path: Path) -> dict[str, Any]:
    payload = load_json(path)
    entry = {
        "path": str(path),
        "type": payload.get("type"),
        "verdict": payload.get("verdict"),
        "readiness": payload.get("readiness"),
        "row_count": payload.get("row_count") or len(payload.get("rows") or []),
    }
    if "best_hit_speedup_vs_baseline" in payload:
        entry["best_hit_speedup_vs_baseline"] = payload["best_hit_speedup_vs_baseline"]
    if "hit_count" in payload:
        entry["hit_count"] = payload["hit_count"]
    if "metrics" in payload:
        entry["metrics"] = payload["metrics"]
    if "auto_selected_profile" in payload:
        entry["auto_selected_profile"] = payload["auto_selected_profile"]
    return {key: value for key, value in entry.items() if value is not None}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8773")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("artifacts/m121-live-product-regression-suite"),
    )
    parser.add_argument("--tag", default="m121-qwen-a3b")
    parser.add_argument("--prompt-tokens", default="512,1024,2048,4096")
    parser.add_argument("--resident-profile", default="agent-workspace-first-hit")
    parser.add_argument("--low-memory-profile", default="agent-workspace-low-memory")
    parser.add_argument("--prompt-sweep-profile", default="agent-workspace-async")
    parser.add_argument("--turns", type=int, default=4)
    parser.add_argument("--shared-repeats", type=int, default=64)
    parser.add_argument("--max-tokens", type=int, default=4)
    parser.add_argument("--prompt-sweep-max-tokens", type=int, default=1)
    parser.add_argument("--max-mean-overhead-ms", type=float, default=500.0)
    parser.add_argument(
        "--dax-cli",
        type=Path,
        default=Path(
            "/Users/jeffreycruz/Development/AI_AGENTS/dax-stereo/packages/coding-agent/dist/cli.js"
        ),
    )
    parser.add_argument("--fail-on-fail", action="store_true")
    args = parser.parse_args()

    cwd = Path.cwd()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    resident_jsonl = args.output_dir / f"dax-resident-client-{args.tag}.jsonl"
    resident_json = args.output_dir / f"dax-resident-client-{args.tag}.json"
    overhead_json = args.output_dir / f"fast-path-overhead-gate-{args.tag}.json"
    prompt_sweep_jsonl = args.output_dir / f"live-prompt-transport-sweep-{args.tag}.jsonl"
    prompt_sweep_json = args.output_dir / f"live-prompt-transport-sweep-{args.tag}.json"
    low_memory_jsonl = args.output_dir / f"dax-low-memory-live-{args.tag}.jsonl"
    low_memory_json = args.output_dir / f"dax-low-memory-live-{args.tag}.json"
    low_memory_gate_json = args.output_dir / f"lower-memory-live-gate-{args.tag}.json"
    auto_gate_json = args.output_dir / f"auto-selection-runtime-gate-{args.tag}.json"
    auto_jsonl = args.output_dir / f"dax-auto-selected-{args.tag}.jsonl"
    auto_json = args.output_dir / f"dax-auto-selected-{args.tag}.json"
    request_profile_json = args.output_dir / f"live-request-profile-metadata-{args.tag}.json"
    dax_request_metadata_json = args.output_dir / f"dax-request-metadata-smoke-{args.tag}.json"
    cache_admission_json = args.output_dir / f"request-scoped-cache-admission-{args.tag}.json"
    request_scoped_gates_dir = args.output_dir / f"request-scoped-gates-{args.tag}"
    request_scoped_gates_json = (
        request_scoped_gates_dir / f"request-scoped-performance-gates-{args.tag}.json"
    )
    suite_json = args.output_dir / f"live-product-regression-suite-{args.tag}.json"

    try:
        run(
            [
                sys.executable,
                "benchmarks/python/dax_repeated_context_bench.py",
                "--base-url",
                args.base_url,
                "--client-mode",
                "resident",
                "--dax-profile",
                args.resident_profile,
                "--output-jsonl",
                str(resident_jsonl),
                "--output-json",
                str(resident_json),
                "--turns",
                str(args.turns),
                "--shared-repeats",
                str(args.shared_repeats),
                "--max-tokens",
                str(args.max_tokens),
                "--fail-on-fail",
            ],
            cwd=cwd,
        )
        run(
            [
                sys.executable,
                "benchmarks/python/dax_operator_overhead_gate.py",
                str(resident_jsonl),
                "--output-json",
                str(overhead_json),
                "--tag",
                args.tag,
                "--max-mean-overhead-ms",
                str(args.max_mean_overhead_ms),
                "--fail-on-fail",
            ],
            cwd=cwd,
        )
        run(
            [
                sys.executable,
                "benchmarks/python/live_prompt_transport_sweep.py",
                "--base-url",
                args.base_url,
                "--profile",
                args.prompt_sweep_profile,
                "--output-jsonl",
                str(prompt_sweep_jsonl),
                "--output-json",
                str(prompt_sweep_json),
                "--prompt-tokens",
                args.prompt_tokens,
                "--transports",
                "resident,cli",
                "--max-tokens",
                str(args.prompt_sweep_max_tokens),
                "--fail-on-fail",
            ],
            cwd=cwd,
        )
        run(
            [
                sys.executable,
                "benchmarks/python/dax_repeated_context_bench.py",
                "--base-url",
                args.base_url,
                "--client-mode",
                "resident",
                "--dax-profile",
                args.low_memory_profile,
                "--output-jsonl",
                str(low_memory_jsonl),
                "--output-json",
                str(low_memory_json),
                "--turns",
                str(args.turns),
                "--shared-repeats",
                str(args.shared_repeats),
                "--max-tokens",
                str(args.max_tokens),
                "--fail-on-fail",
            ],
            cwd=cwd,
        )
        run(
            [
                sys.executable,
                "benchmarks/python/lower_memory_runtime_gate.py",
                str(low_memory_jsonl),
                "--output-json",
                str(low_memory_gate_json),
                "--tag",
                args.tag,
                "--fail-on-fail",
            ],
            cwd=cwd,
        )
        run(
            [
                sys.executable,
                "benchmarks/python/profile_auto_selection_runtime_gate.py",
                "--output-json",
                str(auto_gate_json),
                "--tag",
                args.tag,
                "--fail-on-fail",
            ],
            cwd=cwd,
        )
        run(
            [
                sys.executable,
                "benchmarks/python/dax_repeated_context_bench.py",
                "--base-url",
                args.base_url,
                "--client-mode",
                "resident",
                "--auto-select-profile",
                "--agentic-workload",
                "--immediate-second-turn",
                "--output-jsonl",
                str(auto_jsonl),
                "--output-json",
                str(auto_json),
                "--turns",
                str(args.turns),
                "--shared-repeats",
                str(args.shared_repeats),
                "--max-tokens",
                str(args.max_tokens),
                "--fail-on-fail",
            ],
            cwd=cwd,
        )
        run(
            [
                sys.executable,
                "benchmarks/python/live_request_profile_metadata_probe.py",
                "--base-url",
                args.base_url,
                "--output-json",
                str(request_profile_json),
                "--tag",
                args.tag,
                "--fail-on-fail",
            ],
            cwd=cwd,
        )
        run(
            [
                sys.executable,
                "benchmarks/python/dax_request_metadata_smoke.py",
                "--base-url",
                args.base_url,
                "--dax-cli",
                str(args.dax_cli),
                "--output-json",
                str(dax_request_metadata_json),
                "--tag",
                args.tag,
                "--fail-on-fail",
            ],
            cwd=cwd,
        )
        run(
            [
                sys.executable,
                "benchmarks/python/request_scoped_cache_admission_probe.py",
                "--base-url",
                args.base_url,
                "--output-json",
                str(cache_admission_json),
                "--tag",
                args.tag,
                "--fail-on-fail",
            ],
            cwd=cwd,
        )
        run(
            [
                sys.executable,
                "benchmarks/python/request_scoped_performance_gates.py",
                "--admission",
                str(cache_admission_json),
                "--repeated",
                str(resident_json),
                "--low-memory",
                str(low_memory_json),
                "--output-dir",
                str(request_scoped_gates_dir),
                "--tag",
                args.tag,
                "--fail-on-fail",
            ],
            cwd=cwd,
        )
        artifacts = {
            "resident_client": evidence_entry(resident_json),
            "overhead_gate": evidence_entry(overhead_json),
            "prompt_transport_sweep": evidence_entry(prompt_sweep_json),
            "low_memory_client": evidence_entry(low_memory_json),
            "low_memory_gate": evidence_entry(low_memory_gate_json),
            "auto_selection_gate": evidence_entry(auto_gate_json),
            "auto_selected_client": evidence_entry(auto_json),
            "request_profile_metadata": evidence_entry(request_profile_json),
            "dax_request_metadata_smoke": evidence_entry(dax_request_metadata_json),
            "request_scoped_cache_admission": evidence_entry(cache_admission_json),
            "request_scoped_performance_gates": evidence_entry(request_scoped_gates_json),
        }
        failures = [
            f"{name}: verdict={entry.get('verdict')!r}"
            for name, entry in artifacts.items()
            if entry.get("verdict") != "PASS"
        ]
        output = {
            "type": "live_product_regression_suite",
            "tag": args.tag,
            "base_url": args.base_url,
            "verdict": "PASS" if not failures else "FAIL",
            "readiness": "live-regression-passing" if not failures else "not-ready",
            "output_dir": str(args.output_dir),
            "covered_milestones": [
                "M115",
                "M116",
                "M117",
                "M118",
                "M119",
                "M121",
                "M123",
                "M124",
                "M131",
                "M135",
                "M136",
                "M137",
                "M138",
                "M139",
                "M140",
            ],
            "artifacts": artifacts,
            "failures": failures,
        }
    except subprocess.CalledProcessError as exc:
        output = {
            "type": "live_product_regression_suite",
            "tag": args.tag,
            "base_url": args.base_url,
            "verdict": "FAIL",
            "readiness": "not-ready",
            "output_dir": str(args.output_dir),
            "covered_milestones": [
                "M115",
                "M116",
                "M117",
                "M118",
                "M119",
                "M121",
                "M123",
                "M124",
                "M131",
                "M135",
                "M136",
                "M137",
                "M138",
                "M139",
                "M140",
            ],
            "artifacts": {},
            "failures": [
                {
                    "command": exc.cmd,
                    "returncode": exc.returncode,
                }
            ],
        }

    suite_json.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n")
    print(
        "live_product_regression_suite",
        output["verdict"],
        output["readiness"],
        "artifacts",
        len(output["artifacts"]),
        "failures",
        len(output["failures"]),
        suite_json,
        flush=True,
    )
    if args.fail_on_fail and output["verdict"] != "PASS":
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
