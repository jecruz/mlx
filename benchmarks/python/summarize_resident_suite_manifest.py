#!/usr/bin/env python3
"""Print a compact summary for resident regression suite manifests."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


def load_manifest(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise SystemExit(f"{path}: file not found")
    try:
        manifest = json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        raise SystemExit(f"{path}: invalid JSON: {exc}") from exc
    if manifest.get("type") != "resident_regression_suite":
        raise SystemExit(f"{path}: not a resident_regression_suite manifest")
    return manifest


def print_manifest_summary(manifest: dict[str, Any]) -> None:
    gate_report = manifest.get("gate_report") or {}
    dax_gate_report = manifest.get("dax_repeated_context_gate_report") or {}
    failure = manifest.get("failure") or {}

    print(
        "suite",
        manifest.get("verdict"),
        "tag",
        manifest.get("tag"),
        "base_url",
        manifest.get("base_url"),
    )
    print(
        "steps",
        " ".join(
            f"{name}={enabled}"
            for name, enabled in sorted((manifest.get("steps") or {}).items())
        ),
    )
    for name, artifact in sorted((manifest.get("artifacts") or {}).items()):
        print(
            "artifact",
            name,
            artifact.get("kind"),
            "enabled",
            artifact.get("enabled"),
            "exists",
            artifact.get("exists"),
            artifact.get("path"),
        )
    if gate_report:
        print(
            "gate",
            gate_report.get("verdict"),
            "checks",
            len(gate_report.get("checks") or []),
            "failures",
            len(gate_report.get("failures") or []),
        )
        for failure_text in gate_report.get("failures") or []:
            print("gate_failure", failure_text)
    else:
        print("gate", "none")

    if dax_gate_report:
        print(
            "dax_repeated_context_gate",
            dax_gate_report.get("verdict"),
            "checks",
            len(dax_gate_report.get("checks") or []),
            "failures",
            len(dax_gate_report.get("failures") or []),
        )
        for failure_text in dax_gate_report.get("failures") or []:
            print("dax_repeated_context_gate_failure", failure_text)
    else:
        print("dax_repeated_context_gate", "none")

    if failure:
        print(
            "failure",
            failure.get("type"),
            "returncode",
            failure.get("returncode"),
            "command",
            " ".join(failure.get("command") or []),
        )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest", type=Path)
    parser.add_argument(
        "--fail-on-fail",
        action="store_true",
        help="Exit non-zero when the suite manifest verdict is not PASS.",
    )
    args = parser.parse_args()

    manifest = load_manifest(args.manifest)
    print_manifest_summary(manifest)
    if args.fail_on_fail and manifest.get("verdict") != "PASS":
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
