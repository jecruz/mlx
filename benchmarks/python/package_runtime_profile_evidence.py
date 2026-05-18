#!/usr/bin/env python3
"""Package runtime profile comparison evidence into one handoff directory."""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path
from typing import Any


def load_json(path: Path, *, expected_type: str) -> dict[str, Any]:
    payload = json.loads(path.read_text())
    if payload.get("type") != expected_type:
        raise ValueError(f"{path}: expected {expected_type}, got {payload.get('type')}")
    return payload


def copy_artifact(path: Path, output_dir: Path, copied: list[dict[str, Any]]) -> None:
    destination = output_dir / path.name
    shutil.copy2(path, destination)
    copied.append({"source": str(path), "copied_to": str(destination)})


def collect_comparison_paths(report: dict[str, Any]) -> list[Path]:
    paths: list[Path] = []
    for result in report.get("results") or []:
        for artifact in (result.get("artifacts") or {}).values():
            path = artifact.get("path") if isinstance(artifact, dict) else None
            if path:
                paths.append(Path(path))
    return paths


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("comparison_report", type=Path)
    parser.add_argument("--gate-report", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()

    comparison = load_json(
        args.comparison_report,
        expected_type="runtime_profile_comparison_suite",
    )
    gate = (
        load_json(args.gate_report, expected_type="runtime_profile_comparison_gate")
        if args.gate_report
        else None
    )
    args.output_dir.mkdir(parents=True, exist_ok=True)
    copied: list[dict[str, Any]] = []
    missing: list[str] = []
    seen: set[Path] = set()
    candidates = [args.comparison_report]
    if args.gate_report is not None:
        candidates.append(args.gate_report)
    candidates.extend(collect_comparison_paths(comparison))
    for candidate in candidates:
        path = candidate if candidate.is_absolute() else Path.cwd() / candidate
        if path in seen:
            continue
        seen.add(path)
        if path.exists():
            copy_artifact(path, args.output_dir, copied)
        else:
            missing.append(str(candidate))

    index = {
        "type": "runtime_profile_evidence_package",
        "comparison_tag": comparison.get("tag"),
        "comparison_verdict": comparison.get("verdict"),
        "gate_verdict": gate.get("verdict") if gate else None,
        "presets": comparison.get("presets"),
        "copied_count": len(copied),
        "missing_count": len(missing),
        "copied": copied,
        "missing": missing,
    }
    index_path = args.output_dir / "runtime-profile-evidence-index.json"
    index_path.write_text(json.dumps(index, indent=2, sort_keys=True) + "\n")
    print(
        "runtime_profile_evidence_package",
        "PASS" if not missing else "WARN",
        "copied",
        len(copied),
        "missing",
        len(missing),
        index_path,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
