#!/usr/bin/env python3
"""Compare quality gate artifacts across two MLX model runs."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text())


def artifact_summary(path: Path) -> dict[str, Any]:
    artifact = load(path)
    rows = artifact.get("rows") or []
    service_times = [
        row.get("service_request_ms")
        for row in rows
        if isinstance(row, dict) and isinstance(row.get("service_request_ms"), int | float)
    ]
    if not service_times:
        for row in rows:
            if not isinstance(row, dict):
                continue
            for nested in row.values():
                if isinstance(nested, dict) and isinstance(nested.get("service_request_ms"), int | float):
                    service_times.append(nested["service_request_ms"])
    return {
        "path": str(path),
        "type": artifact.get("type"),
        "tag": artifact.get("tag"),
        "verdict": artifact.get("verdict"),
        "failure_count": len(artifact.get("failures", [])),
        "failures": artifact.get("failures", []),
        "row_count": len(rows),
        "mean_service_request_ms": round(sum(service_times) / len(service_times), 3) if service_times else None,
    }


def collect_model(label: str, model: str, paths: list[Path]) -> dict[str, Any]:
    artifacts = {path.stem: artifact_summary(path) for path in paths}
    failures = [
        f"{label}:{name}: {artifact['verdict']} failures={artifact['failure_count']}"
        for name, artifact in artifacts.items()
        if artifact["verdict"] != "PASS" or artifact["failure_count"]
    ]
    return {
        "label": label,
        "model": model,
        "verdict": "PASS" if not failures else "FAIL",
        "artifacts": artifacts,
        "failures": failures,
    }


def write_markdown(path: Path, output: dict[str, Any]) -> None:
    lines = [
        "# M170 Model Quality Comparison",
        "",
        f"Verdict: `{output['verdict']}`",
        "",
        "Speed work is blocked unless every compared model keeps the quality gates passing.",
        "",
        "## Models",
        "",
    ]
    for model in output["models"]:
        lines.extend(
            [
                f"### {model['label']}",
                "",
                f"- Model: `{model['model']}`",
                f"- Verdict: `{model['verdict']}`",
                f"- Failures: `{len(model['failures'])}`",
                "",
                "| Artifact | Verdict | Rows | Failures | Mean Service ms |",
                "| --- | --- | ---: | ---: | ---: |",
            ]
        )
        for name, artifact in sorted(model["artifacts"].items()):
            mean_ms = artifact["mean_service_request_ms"]
            lines.append(
                f"| `{name}` | `{artifact['verdict']}` | {artifact['row_count']} | "
                f"{artifact['failure_count']} | {mean_ms if mean_ms is not None else ''} |"
            )
        lines.append("")
    failure_lines = [f"- `{failure}`" for failure in output["failures"]] or ["- none"]
    lines.extend(["## Failures", "", *failure_lines, ""])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--current-label", required=True)
    parser.add_argument("--current-model", required=True)
    parser.add_argument("--current-artifact", type=Path, action="append", required=True)
    parser.add_argument("--candidate-label", required=True)
    parser.add_argument("--candidate-model", required=True)
    parser.add_argument("--candidate-artifact", type=Path, action="append", required=True)
    parser.add_argument("--output-json", type=Path, required=True)
    parser.add_argument("--output-md", type=Path, required=True)
    parser.add_argument("--tag", default="m170-model-quality-comparison")
    parser.add_argument("--fail-on-fail", action="store_true")
    args = parser.parse_args()

    current = collect_model(args.current_label, args.current_model, args.current_artifact)
    candidate = collect_model(args.candidate_label, args.candidate_model, args.candidate_artifact)
    failures = current["failures"] + candidate["failures"]
    output = {
        "type": "model_quality_comparison",
        "tag": args.tag,
        "verdict": "PASS" if not failures else "FAIL",
        "models": [current, candidate],
        "failures": failures,
        "readiness": "model-quality-comparable" if not failures else "quality-regression-detected",
    }
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n")
    write_markdown(args.output_md, output)
    print("model_quality_comparison", output["verdict"], "failures", len(failures), args.output_json)
    if args.fail_on_fail and output["verdict"] != "PASS":
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
