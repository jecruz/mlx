#!/usr/bin/env python3
"""Package resident regression suite evidence into one handoff directory."""

from __future__ import annotations

import argparse
import json
import shutil
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


def copy_artifact(source: Path, output_dir: Path) -> dict[str, Any]:
    destination = output_dir / source.name
    shutil.copy2(source, destination)
    return {
        "source": str(source),
        "path": str(destination),
        "bytes": destination.stat().st_size,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()

    manifest_path = args.manifest
    manifest = load_manifest(manifest_path)
    args.output_dir.mkdir(parents=True, exist_ok=True)

    copied: dict[str, dict[str, Any]] = {
        "suite_manifest": copy_artifact(manifest_path, args.output_dir)
    }
    missing: dict[str, str] = {}
    for name, artifact in sorted((manifest.get("artifacts") or {}).items()):
        artifact_path = Path(str(artifact.get("path") or ""))
        if not artifact_path.exists():
            missing[name] = str(artifact_path)
            continue
        copied[name] = copy_artifact(artifact_path, args.output_dir)

    evidence_index = {
        "type": "resident_suite_evidence_package",
        "suite_verdict": manifest.get("verdict"),
        "suite_tag": manifest.get("tag"),
        "source_manifest": str(manifest_path),
        "output_dir": str(args.output_dir),
        "copied": copied,
        "missing": missing,
    }
    index_path = args.output_dir / "resident-suite-evidence-index.json"
    index_path.write_text(json.dumps(evidence_index, indent=2, sort_keys=True) + "\n")

    print(
        "evidence_package",
        manifest.get("verdict"),
        "copied",
        len(copied),
        "missing",
        len(missing),
        index_path,
    )


if __name__ == "__main__":
    main()
