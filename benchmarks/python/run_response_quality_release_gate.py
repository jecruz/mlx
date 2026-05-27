#!/usr/bin/env python3
"""Run response-quality capture, comparison, and release gate as one command."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any


DEFAULT_BASELINE = Path(
    "artifacts/m258-live-response-quality-baseline/live-baseline-m258-qwen-a3b.json"
)


def run(cmd: list[str], *, cwd: Path) -> None:
    print("response_quality_release_cmd", " ".join(cmd), flush=True)
    subprocess.run(cmd, cwd=cwd, check=True)


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def artifact_summary(path: Path) -> dict[str, Any]:
    payload = load_json(path)
    summary = {
        "path": str(path),
        "type": payload.get("type"),
        "tag": payload.get("tag"),
        "verdict": payload.get("verdict"),
        "readiness": payload.get("readiness"),
        "failure_count": len(payload.get("failures") or []),
    }
    if payload.get("summary"):
        summary["summary"] = payload["summary"]
    if payload.get("candidate"):
        summary["candidate"] = payload["candidate"].get("summary")
    if payload.get("gate_count") is not None:
        summary["gate_count"] = payload.get("gate_count")
    return {key: value for key, value in summary.items() if value is not None}


def write_markdown(path: Path, output: dict[str, Any]) -> None:
    lines = [
        "# M260 Response Quality Release Runner",
        "",
        f"Verdict: `{output['verdict']}`",
        f"Readiness: `{output['readiness']}`",
        f"Tag: `{output['tag']}`",
        "",
        "## Artifacts",
        "",
    ]
    for name, artifact in output["artifacts"].items():
        lines.append(
            f"- `{name}`: `{artifact.get('verdict')}` - `{artifact.get('path')}`"
        )
    failure_lines = [f"- `{failure}`" for failure in output["failures"]] or ["- none"]
    lines.extend(["", "## Failures", "", *failure_lines, ""])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8773")
    parser.add_argument("--model", default="local-mlx")
    parser.add_argument("--runtime-profile", default="interactive")
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--top-p", type=float, default=1.0)
    parser.add_argument("--seed", type=int, default=260)
    parser.add_argument("--baseline-json", type=Path, default=DEFAULT_BASELINE)
    parser.add_argument(
        "--candidate-json",
        type=Path,
        help="Use an existing candidate capture instead of capturing from the live endpoint.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("artifacts/m260-response-quality-release-runner"),
    )
    parser.add_argument("--tag", default="m260-response-quality-release-runner")
    parser.add_argument("--fail-on-fail", action="store_true")
    return parser.parse_args()


def main_with_args(args: argparse.Namespace) -> int:
    cwd = Path.cwd()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    candidate_json = (
        args.candidate_json
        if args.candidate_json
        else args.output_dir / f"candidate-quality-capture-{args.tag}.json"
    )
    candidate_md = args.output_dir / f"candidate-quality-capture-{args.tag}.md"
    comparison_json = args.output_dir / f"candidate-vs-baseline-{args.tag}.json"
    comparison_md = args.output_dir / f"candidate-vs-baseline-{args.tag}.md"
    release_json = args.output_dir / f"quality-preserving-release-gate-{args.tag}.json"
    release_md = args.output_dir / f"quality-preserving-release-gate-{args.tag}.md"
    manifest_json = args.output_dir / f"response-quality-release-runner-{args.tag}.json"
    manifest_md = args.output_dir / f"response-quality-release-runner-{args.tag}.md"

    try:
        if not args.candidate_json:
            run(
                [
                    sys.executable,
                    "benchmarks/python/response_quality_regression_harness.py",
                    "capture",
                    "--base-url",
                    args.base_url,
                    "--model",
                    args.model,
                    "--runtime-profile",
                    args.runtime_profile,
                    "--temperature",
                    str(args.temperature),
                    "--top-p",
                    str(args.top_p),
                    "--seed",
                    str(args.seed),
                    "--output-json",
                    str(candidate_json),
                    "--output-md",
                    str(candidate_md),
                    "--tag",
                    f"{args.tag}-candidate",
                    "--fail-on-fail",
                ],
                cwd=cwd,
            )
        run(
            [
                sys.executable,
                "benchmarks/python/response_quality_regression_harness.py",
                "compare",
                "--baseline-json",
                str(args.baseline_json),
                "--candidate-json",
                str(candidate_json),
                "--output-json",
                str(comparison_json),
                "--output-md",
                str(comparison_md),
                "--tag",
                f"{args.tag}-candidate-vs-baseline",
                "--fail-on-fail",
            ],
            cwd=cwd,
        )
        run(
            [
                sys.executable,
                "benchmarks/python/release_quality_performance_gate.py",
                "--response-quality-comparison-json",
                str(comparison_json),
                "--output-json",
                str(release_json),
                "--output-md",
                str(release_md),
                "--tag",
                args.tag,
                "--fail-on-fail",
            ],
            cwd=cwd,
        )
        artifacts = {
            "candidate_quality": artifact_summary(candidate_json),
            "candidate_vs_baseline": artifact_summary(comparison_json),
            "release_gate": artifact_summary(release_json),
        }
        failures = [
            f"{name}: {artifact.get('verdict')!r}"
            for name, artifact in artifacts.items()
            if artifact.get("verdict") != "PASS" or artifact.get("failure_count")
        ]
        output = {
            "type": "response_quality_release_runner",
            "tag": args.tag,
            "verdict": "PASS" if not failures else "FAIL",
            "readiness": "response-quality-release-ready"
            if not failures
            else "not-ready",
            "base_url": args.base_url,
            "baseline_json": str(args.baseline_json),
            "candidate_source": "existing-artifact" if args.candidate_json else "live-capture",
            "artifacts": artifacts,
            "failures": failures,
        }
    except subprocess.CalledProcessError as exc:
        output = {
            "type": "response_quality_release_runner",
            "tag": args.tag,
            "verdict": "FAIL",
            "readiness": "not-ready",
            "base_url": args.base_url,
            "baseline_json": str(args.baseline_json),
            "candidate_source": "existing-artifact" if args.candidate_json else "live-capture",
            "artifacts": {},
            "failures": [f"command failed with exit code {exc.returncode}: {' '.join(exc.cmd)}"],
        }

    manifest_json.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    write_markdown(manifest_md, output)
    print(
        "response_quality_release_runner",
        output["verdict"],
        output["readiness"],
        manifest_json,
    )
    if args.fail_on_fail and output["verdict"] != "PASS":
        return 1
    return 0


def main() -> int:
    return main_with_args(parse_args())


if __name__ == "__main__":
    raise SystemExit(main())
