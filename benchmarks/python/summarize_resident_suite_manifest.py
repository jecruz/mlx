#!/usr/bin/env python3
"""Print a compact summary for resident regression suite manifests."""

from __future__ import annotations

import argparse
import json
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


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest", type=Path)
    args = parser.parse_args()

    manifest = load_manifest(args.manifest)
    gate_report = manifest.get("gate_report") or {}
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

    if failure:
        print(
            "failure",
            failure.get("type"),
            "returncode",
            failure.get("returncode"),
            "command",
            " ".join(failure.get("command") or []),
        )


if __name__ == "__main__":
    main()
