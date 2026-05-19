#!/usr/bin/env python3
"""CI-style quality threshold gate for model/profile/speed changes."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text())


def check(
    checks: list[dict[str, Any]],
    failures: list[str],
    *,
    label: str,
    actual: float | int | str | bool | None,
    operator: str,
    threshold: float | int | str | bool,
) -> None:
    if operator == "==":
        verdict = "PASS" if actual == threshold else "FAIL"
    elif actual is None:
        verdict = "FAIL"
    elif operator == "<=":
        verdict = "PASS" if float(actual) <= float(threshold) else "FAIL"
    elif operator == ">=":
        verdict = "PASS" if float(actual) >= float(threshold) else "FAIL"
    else:
        raise ValueError(f"unsupported operator: {operator}")
    checks.append(
        {
            "label": label,
            "actual": actual,
            "operator": operator,
            "threshold": threshold,
            "verdict": verdict,
        }
    )
    if verdict == "FAIL":
        failures.append(f"{label}: {actual!r} {operator} {threshold!r} failed")


def nested_values(row: dict[str, Any]) -> list[dict[str, Any]]:
    values = [row]
    for value in row.values():
        if isinstance(value, dict):
            values.append(value)
    return values


def summarize_quality_artifact(path: Path) -> dict[str, Any]:
    artifact = load_json(path)
    rows = artifact.get("rows") or []
    row_values = [value for row in rows if isinstance(row, dict) for value in nested_values(row)]
    visible_thinking_count = sum(1 for value in row_values if value.get("visible_thinking"))
    max_repetition = max(
        [
            float(value["repetition_score"])
            for value in row_values
            if isinstance(value.get("repetition_score"), int | float)
        ]
        or [0.0]
    )
    row_failure_count = sum(len(value.get("failures") or []) for value in row_values)
    missing_required_count = sum(len(value.get("missing") or []) for value in row_values)
    return {
        "path": str(path),
        "type": artifact.get("type"),
        "tag": artifact.get("tag"),
        "verdict": artifact.get("verdict"),
        "failure_count": len(artifact.get("failures") or []),
        "row_count": len(rows),
        "row_failure_count": row_failure_count,
        "missing_required_count": missing_required_count,
        "visible_thinking_count": visible_thinking_count,
        "max_repetition_score": round(max_repetition, 6),
    }


def gate(args: argparse.Namespace) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    failures: list[str] = []
    artifacts = {
        path.stem: summarize_quality_artifact(path) for path in args.quality_artifact
    }
    for name, artifact in artifacts.items():
        check(
            checks,
            failures,
            label=f"{name}.verdict",
            actual=artifact["verdict"],
            operator="==",
            threshold="PASS",
        )
        check(
            checks,
            failures,
            label=f"{name}.failure_count",
            actual=artifact["failure_count"],
            operator="<=",
            threshold=args.max_artifact_failures,
        )
        check(
            checks,
            failures,
            label=f"{name}.row_failure_count",
            actual=artifact["row_failure_count"],
            operator="<=",
            threshold=args.max_row_failures,
        )
        check(
            checks,
            failures,
            label=f"{name}.missing_required_count",
            actual=artifact["missing_required_count"],
            operator="<=",
            threshold=args.max_missing_required,
        )
        check(
            checks,
            failures,
            label=f"{name}.visible_thinking_count",
            actual=artifact["visible_thinking_count"],
            operator="<=",
            threshold=args.max_visible_thinking,
        )
        check(
            checks,
            failures,
            label=f"{name}.max_repetition_score",
            actual=artifact["max_repetition_score"],
            operator="<=",
            threshold=args.max_repetition_score,
        )

    operator_bundle = None
    if args.operator_bundle_json:
        operator_bundle = load_json(args.operator_bundle_json)
        check(
            checks,
            failures,
            label="operator_bundle.verdict",
            actual=operator_bundle.get("verdict"),
            operator="==",
            threshold="PASS",
        )
        check(
            checks,
            failures,
            label="operator_bundle.failure_count",
            actual=len(operator_bundle.get("failures") or []),
            operator="<=",
            threshold=0,
        )
        status_card = operator_bundle.get("status_card") or {}
        for key in ["engine", "gpu", "quality", "model_comparison"]:
            check(
                checks,
                failures,
                label=f"operator_bundle.status_card.{key}",
                actual=status_card.get(key),
                operator="==",
                threshold="PASS",
            )
        if not args.allow_warnings:
            check(
                checks,
                failures,
                label="operator_bundle.warning_count",
                actual=len(operator_bundle.get("warnings") or []),
                operator="<=",
                threshold=0,
            )

    return {
        "type": "quality_threshold_gate",
        "tag": args.tag,
        "verdict": "PASS" if not failures else "FAIL",
        "readiness": "ci-quality-ready" if not failures else "ci-quality-blocked",
        "checks": checks,
        "artifacts": artifacts,
        "operator_bundle": {
            "path": str(args.operator_bundle_json),
            "verdict": operator_bundle.get("verdict"),
            "warning_count": len(operator_bundle.get("warnings") or []),
        }
        if operator_bundle is not None
        else None,
        "thresholds": {
            "max_artifact_failures": args.max_artifact_failures,
            "max_row_failures": args.max_row_failures,
            "max_missing_required": args.max_missing_required,
            "max_visible_thinking": args.max_visible_thinking,
            "max_repetition_score": args.max_repetition_score,
            "allow_warnings": args.allow_warnings,
        },
        "failures": failures,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--quality-artifact", type=Path, action="append", required=True)
    parser.add_argument("--operator-bundle-json", type=Path)
    parser.add_argument("--output-json", type=Path, required=True)
    parser.add_argument("--tag", default="m173-quality-threshold-gate")
    parser.add_argument("--max-artifact-failures", type=int, default=0)
    parser.add_argument("--max-row-failures", type=int, default=0)
    parser.add_argument("--max-missing-required", type=int, default=0)
    parser.add_argument("--max-visible-thinking", type=int, default=0)
    parser.add_argument("--max-repetition-score", type=float, default=0.2)
    parser.add_argument("--allow-warnings", action="store_true")
    parser.add_argument("--fail-on-fail", action="store_true")
    args = parser.parse_args()

    report = gate(args)
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    for item in report["checks"]:
        print(
            "quality_threshold_check",
            item["verdict"],
            item["label"],
            item["actual"],
            item["operator"],
            item["threshold"],
        )
    for failure in report["failures"]:
        print("quality_threshold_failure", failure)
    print(
        "quality_threshold_result",
        report["verdict"],
        report["readiness"],
        "checks",
        len(report["checks"]),
        "failures",
        len(report["failures"]),
        args.output_json,
    )
    return 1 if args.fail_on_fail and report["verdict"] != "PASS" else 0


if __name__ == "__main__":
    raise SystemExit(main())
