#!/usr/bin/env python3
"""Run Python MLX package validation through a tmux pane."""

from __future__ import annotations

import argparse
import json
import shlex
import subprocess
import time
import uuid
from pathlib import Path
from typing import Any


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pane", required=True, help="tmux pane target, e.g. session:1.2")
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument(
        "--output-json",
        type=Path,
        default=Path("artifacts/m244-python-package-tmux-validation/python-package-validation-m244.json"),
    )
    parser.add_argument("--tag", default="m244-python-package-tmux-validation")
    parser.add_argument("--timeout-seconds", type=float, default=90.0)
    parser.add_argument("--require-gpu", action="store_true")
    parser.add_argument("--fail-on-fail", action="store_true")
    return parser.parse_args()


def run_tmux(args: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["tmux", *args], check=check, capture_output=True, text=True)


def pane_exists(pane: str) -> bool:
    completed = run_tmux(["display-message", "-p", "-t", pane, "#{pane_id}"], check=False)
    return completed.returncode == 0 and bool(completed.stdout.strip())


def send_command(pane: str, command: str) -> None:
    run_tmux(["send-keys", "-t", pane, command, "C-m"])


def capture_pane(pane: str, lines: int = 120) -> str:
    completed = run_tmux(["capture-pane", "-p", "-t", pane, "-S", f"-{lines}"])
    return completed.stdout


def main() -> int:
    args = parse_args()
    repo_root = args.repo_root.resolve()
    output_json = args.output_json
    if not output_json.is_absolute():
        output_json = repo_root / output_json
    probe = repo_root / "benchmarks/python/python_package_validation_probe.py"
    marker = f"__MLX_PYTHON_PACKAGE_VALIDATION_{uuid.uuid4().hex}__"

    failures: list[str] = []
    if not pane_exists(args.pane):
        failures.append(f"tmux pane does not exist: {args.pane}")
    if not probe.exists():
        failures.append(f"probe script missing: {probe}")

    if not failures:
        command_parts = [
            "cd",
            shlex.quote(str(repo_root)),
            "&&",
            "python3",
            shlex.quote(str(probe)),
            "--output-json",
            shlex.quote(str(output_json)),
            "--tag",
            shlex.quote(args.tag),
        ]
        if args.require_gpu:
            command_parts.append("--require-gpu")
        command = " ".join(command_parts)
        send_command(args.pane, f"{command}; printf '{marker}:$?\\n'")

        deadline = time.time() + args.timeout_seconds
        while time.time() < deadline:
            if output_json.exists():
                break
            time.sleep(1.0)

        if not output_json.exists():
            failures.append(f"output JSON was not created before timeout: {output_json}")

    probe_payload: dict[str, Any] | None = None
    if output_json.exists():
        try:
            probe_payload = json.loads(output_json.read_text())
        except json.JSONDecodeError as exc:
            failures.append(f"output JSON is invalid: {exc}")

    pane_tail = capture_pane(args.pane) if pane_exists(args.pane) else ""
    marker_seen = marker in pane_tail
    if not marker_seen:
        failures.append(f"tmux completion marker was not observed: {marker}")

    if probe_payload is not None and probe_payload.get("verdict") != "PASS":
        failures.append(f"probe verdict={probe_payload.get('verdict')!r}")

    harness = {
        "type": "tmux_python_package_validation",
        "tag": args.tag,
        "pane": args.pane,
        "repo_root": str(repo_root),
        "probe": str(probe),
        "probe_output": str(output_json),
        "marker_seen": marker_seen,
        "probe_result": probe_payload,
        "failures": failures,
        "verdict": "PASS" if not failures else "FAIL",
        "readiness": "tmux-python-package-validation-ready" if not failures else "not-ready",
    }
    output_json.parent.mkdir(parents=True, exist_ok=True)
    harness_path = output_json.with_name(output_json.stem + "-harness.json")
    harness_path.write_text(json.dumps(harness, indent=2, sort_keys=True) + "\n")
    print(
        "tmux_python_package_validation",
        harness["verdict"],
        "failures",
        len(failures),
        "probe",
        output_json,
        "harness",
        harness_path,
    )
    if args.fail_on_fail and failures:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
