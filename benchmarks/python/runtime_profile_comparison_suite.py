#!/usr/bin/env python3
"""Compare resident benchmark behavior across runtime engine presets."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any


def safe_name(value: str) -> str:
    return "".join(ch if ch.isalnum() or ch in ("-", "_") else "-" for ch in value)


def read_json_if_exists(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    return json.loads(path.read_text())


def run(cmd: list[str], *, cwd: Path, dry_run: bool) -> int:
    print("profile_suite_cmd", " ".join(cmd), flush=True)
    if dry_run:
        return 0
    completed = subprocess.run(cmd, cwd=cwd, check=False)
    return completed.returncode


def profile_artifacts(output_dir: Path, *, tag: str, preset: str) -> dict[str, Path]:
    prefix = f"{safe_name(preset)}-{tag}"
    return {
        "benchmark": output_dir / f"resident-benchmark-{prefix}.jsonl",
        "cache_create_probe": output_dir / f"cache-create-optimization-{prefix}.json",
    }


def write_manifest(
    *,
    output_dir: Path,
    manifest_path: Path,
    tag: str,
    base_url: str,
    presets: list[str],
    dry_run: bool,
    results: list[dict[str, Any]],
) -> None:
    manifest = {
        "type": "runtime_profile_comparison_suite",
        "verdict": "PASS"
        if all(result["returncode"] == 0 for result in results)
        else "FAIL",
        "created": int(time.time()),
        "tag": tag,
        "base_url": base_url,
        "output_dir": str(output_dir),
        "dry_run": dry_run,
        "presets": presets,
        "results": results,
    }
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8765")
    parser.add_argument("--output-dir", type=Path, default=Path("artifacts/profile-comparison"))
    parser.add_argument("--tag", default=None)
    parser.add_argument(
        "--presets",
        default="sync-safe,async-experimental",
        help="Comma-separated engine presets to compare.",
    )
    parser.add_argument("--requests", type=int, default=3)
    parser.add_argument("--prefix-repeats", type=int, default=24)
    parser.add_argument("--max-tokens", type=int, default=6)
    parser.add_argument("--min-prepare-share", type=float, default=0.40)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    cwd = Path.cwd()
    tag = args.tag or str(int(time.time()))
    presets = [preset.strip() for preset in args.presets.split(",") if preset.strip()]
    if not presets:
        raise SystemExit("--presets must include at least one preset")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = args.output_dir / f"runtime-profile-comparison-{tag}.json"

    results: list[dict[str, Any]] = []
    for preset in presets:
        artifacts = profile_artifacts(args.output_dir, tag=tag, preset=preset)
        benchmark_cmd = [
            sys.executable,
            "benchmarks/python/resident_benchmark_harness.py",
            "--base-url",
            args.base_url,
            "--engine-preset",
            preset,
            "--reset-cache",
            "--requests",
            str(args.requests),
            "--prefix-repeats",
            str(args.prefix_repeats),
            "--max-tokens",
            str(args.max_tokens),
            "--output-jsonl",
            str(artifacts["benchmark"]),
        ]
        benchmark_returncode = run(benchmark_cmd, cwd=cwd, dry_run=args.dry_run)
        probe_returncode = 0
        probe_cmd = None
        if benchmark_returncode == 0:
            probe_cmd = [
                sys.executable,
                "benchmarks/python/cache_create_optimization_probe.py",
                str(artifacts["benchmark"]),
                "--output-json",
                str(artifacts["cache_create_probe"]),
                "--min-prepare-share",
                str(args.min_prepare_share),
                "--fail-on-fail",
            ]
            probe_returncode = run(probe_cmd, cwd=cwd, dry_run=args.dry_run)
        results.append(
            {
                "preset": preset,
                "returncode": benchmark_returncode or probe_returncode,
                "benchmark_command": benchmark_cmd,
                "probe_command": None if benchmark_returncode else probe_cmd,
                "artifacts": {
                    name: {
                        "path": str(path),
                        "exists": path.exists(),
                        "report": read_json_if_exists(path)
                        if name == "cache_create_probe"
                        else None,
                    }
                    for name, path in artifacts.items()
                },
            }
        )

    write_manifest(
        output_dir=args.output_dir,
        manifest_path=manifest_path,
        tag=tag,
        base_url=args.base_url,
        presets=presets,
        dry_run=args.dry_run,
        results=results,
    )
    verdict = "PASS" if all(result["returncode"] == 0 for result in results) else "FAIL"
    print(
        "runtime_profile_comparison",
        verdict,
        "presets",
        ",".join(presets),
        "manifest",
        manifest_path,
        flush=True,
    )
    return 0 if verdict == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
