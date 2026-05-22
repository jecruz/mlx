#!/usr/bin/env python3
"""Package release-blocking MLX/Prowl evidence into one bundle."""

from __future__ import annotations

import argparse
import json
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class EvidenceSpec:
    key: str
    path: Path
    kind: str
    required: bool = True
    expected_verdict: str | None = "PASS"
    required_text: str | None = None


DEFAULT_EVIDENCE = [
    EvidenceSpec(
        "quality_threshold",
        Path("artifacts/m231-model-swap-artifact-freshness-refresh/quality-threshold-gate-m231-qwen25-coder-14b-adapted.json"),
        "quality",
    ),
    EvidenceSpec(
        "model_swap_acceptance",
        Path("artifacts/m231-model-swap-artifact-freshness-refresh/model-swap-acceptance-m231-qwen25-coder-14b.json"),
        "model_swap",
    ),
    EvidenceSpec(
        "lifecycle_gate",
        Path("artifacts/m232-resident-lifecycle-regression-gate/resident-lifecycle-regression-gate-m232.json"),
        "lifecycle",
    ),
    EvidenceSpec(
        "memory_guard",
        Path("artifacts/m233-proactive-cache-memory-pressure-guard/proactive-cache-memory-pressure-guard-m233.json"),
        "memory_guard",
    ),
    EvidenceSpec(
        "routing_policy",
        Path("artifacts/m234-lower-memory-default-routing-policy/lower-memory-default-routing-policy-gate-m234.json"),
        "routing",
    ),
    EvidenceSpec(
        "resident_suite_package_index",
        Path("artifacts/m236-lifecycle-gate-ci-packaging/resident-suite-evidence-package/resident-suite-evidence-index.json"),
        "evidence_package",
    ),
    EvidenceSpec(
        "bounded_first_hit_benchmark",
        Path("artifacts/m237-bounded-first-hit-live-revalidation/dax-bounded-first-hit-m237-qwen25-coder-14b.json"),
        "first_hit_performance",
    ),
    EvidenceSpec(
        "bounded_first_hit_conversion_gate",
        Path("artifacts/m237-bounded-first-hit-live-revalidation/dax-first-hit-conversion-gate-m237-qwen25-coder-14b.json"),
        "first_hit_gate",
    ),
    EvidenceSpec(
        "product_mode_metadata_probe",
        Path("artifacts/m238-lower-memory-route-product-smoke/product-mode-metadata-probe-m238.json"),
        "product_routing",
    ),
    EvidenceSpec(
        "live_request_profile_metadata_probe",
        Path("artifacts/m238-lower-memory-route-product-smoke/live-request-profile-metadata-m238.json"),
        "live_routing",
    ),
    EvidenceSpec(
        "prowl_installed_app_health",
        Path("artifacts/m239-prowl-promotion-visibility-installed-app-smoke/prowl-app-health-m239.json"),
        "prowl_health",
        expected_verdict=None,
    ),
    EvidenceSpec(
        "prowl_direct_health",
        Path("artifacts/m239-prowl-promotion-visibility-installed-app-smoke/prowl-direct-health-m239.json"),
        "prowl_direct_health",
        expected_verdict=None,
    ),
    EvidenceSpec(
        "prowl_models_catalog",
        Path("artifacts/m239-prowl-promotion-visibility-installed-app-smoke/prowl-models-m239.json"),
        "prowl_catalog",
        expected_verdict=None,
    ),
    EvidenceSpec(
        "prowl_promotion_visibility_smoke",
        Path("artifacts/m239-prowl-promotion-visibility-installed-app-smoke/prowl-promotion-visibility-installed-app-smoke-m239.md"),
        "prowl_visibility",
        expected_verdict=None,
        required_text="Status: PASS",
    ),
    EvidenceSpec(
        "first_hit_regression_recovery_report",
        Path("artifacts/m247-first-hit-regression-recovery/first-hit-regression-recovery-m247.md"),
        "first_hit_recovery",
        expected_verdict=None,
        required_text="Status: PASS",
    ),
    EvidenceSpec(
        "first_hit_regression_recovery_audit",
        Path("artifacts/m247-first-hit-regression-recovery/milestone-completion-audit-m247.json"),
        "first_hit_recovery",
    ),
    EvidenceSpec(
        "first_hit_regression_recovery_benchmark",
        Path("artifacts/m247-first-hit-regression-recovery/dax-first-hit-m247-qwen25-coder-14b.json"),
        "first_hit_recovery",
    ),
    EvidenceSpec(
        "first_hit_regression_recovery_conversion_gate",
        Path("artifacts/m247-first-hit-regression-recovery/dax-first-hit-conversion-gate-m247-qwen25-coder-14b.json"),
        "first_hit_recovery",
    ),
    EvidenceSpec(
        "first_duplicate_budget_release_gate",
        Path("artifacts/m248-first-duplicate-budget-release-gate/quality-preserving-release-gate-m248.json"),
        "first_hit_recovery",
    ),
    EvidenceSpec(
        "first_duplicate_budget_release_audit",
        Path("artifacts/m248-first-duplicate-budget-release-gate/milestone-completion-audit-m248.json"),
        "first_hit_recovery",
    ),
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("artifacts/m240-release-evidence-bundle/release-evidence-bundle"),
        help="Directory to write the release evidence bundle.",
    )
    parser.add_argument(
        "--tag",
        default="m240-release-evidence-bundle",
        help="Tag to write into the evidence index.",
    )
    parser.add_argument(
        "--fail-on-fail",
        action="store_true",
        help="Exit non-zero if any required evidence item is missing or not green.",
    )
    return parser.parse_args()


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def check_json_spec(spec: EvidenceSpec, payload: dict[str, Any]) -> tuple[str, list[str], dict[str, Any]]:
    failures: list[str] = []
    verdict = payload.get("verdict") or payload.get("suite_verdict") or payload.get("status")
    summary: dict[str, Any] = {
        "verdict": verdict,
        "readiness": payload.get("readiness"),
        "type": payload.get("type"),
    }

    if spec.key == "model_swap_acceptance":
        summary["swap_decision"] = payload.get("swap_decision")
        metrics = payload.get("metrics") or {}
        summary["first_duplicate_service_ms"] = metrics.get("first_duplicate_service_ms")
        summary["mature_hit_speedup_vs_baseline"] = metrics.get("mature_hit_speedup_vs_baseline")
        summary["max_peak_memory_gb"] = metrics.get("max_peak_memory_gb")
        if payload.get("swap_decision") != "ACCEPT":
            failures.append(f"{spec.key}: swap_decision={payload.get('swap_decision')!r}")

    if spec.key == "bounded_first_hit_benchmark":
        summary["baseline_service_ms"] = payload.get("baseline_service_ms")
        summary["first_duplicate_service_ms"] = payload.get("first_duplicate_service_ms")
        summary["best_hit_service_ms"] = payload.get("best_hit_service_ms")
        summary["mature_hit_speedup_vs_baseline"] = payload.get("mature_hit_speedup_vs_baseline")
        summary["max_peak_memory_gb"] = payload.get("max_peak_memory_gb")
        summary["cache_memory_gb"] = payload.get("cache_memory_gb")

    if spec.key == "resident_suite_package_index":
        summary["suite_verdict"] = payload.get("suite_verdict")
        summary["missing"] = payload.get("missing")
        lifecycle_gate = payload.get("lifecycle_gate") or {}
        summary["lifecycle_gate_verdict"] = lifecycle_gate.get("verdict")
        if payload.get("missing"):
            failures.append(f"{spec.key}: missing={payload.get('missing')!r}")
        if lifecycle_gate.get("verdict") != "PASS":
            failures.append(
                f"{spec.key}: lifecycle_gate={lifecycle_gate.get('verdict')!r}"
            )

    if spec.key == "prowl_installed_app_health":
        if payload.get("status") != "ok":
            failures.append(f"{spec.key}: status={payload.get('status')!r}")
        verdict = "PASS" if not failures else "FAIL"
        summary["verdict"] = verdict

    if spec.key == "prowl_direct_health":
        if payload.get("ok") is not True:
            failures.append(f"{spec.key}: ok={payload.get('ok')!r}")
        if payload.get("child_reachable") is not True:
            failures.append(f"{spec.key}: child_reachable={payload.get('child_reachable')!r}")
        summary["active_model"] = payload.get("active_model")
        summary["active_profile"] = payload.get("active_profile")
        verdict = "PASS" if not failures else "FAIL"
        summary["verdict"] = verdict

    if spec.key == "prowl_models_catalog":
        model_count = len(payload.get("data") or [])
        summary["model_count"] = model_count
        if model_count <= 0:
            failures.append(f"{spec.key}: model_count={model_count}")
        verdict = "PASS" if not failures else "FAIL"
        summary["verdict"] = verdict

    nested_failures = payload.get("failures")
    if nested_failures:
        failures.append(f"{spec.key}: failures={nested_failures!r}")

    if spec.expected_verdict and verdict != spec.expected_verdict:
        failures.append(f"{spec.key}: verdict={verdict!r}, expected {spec.expected_verdict!r}")

    status = "PASS" if not failures else "FAIL"
    return status, failures, summary


def check_text_spec(spec: EvidenceSpec, text: str) -> tuple[str, list[str], dict[str, Any]]:
    failures: list[str] = []
    if spec.required_text and spec.required_text not in text:
        failures.append(f"{spec.key}: missing text {spec.required_text!r}")
    return ("PASS" if not failures else "FAIL"), failures, {
        "contains_required_text": not failures,
    }


def copy_artifact(src: Path, output_dir: Path) -> Path:
    dest = output_dir / src
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dest)
    return dest


def main() -> None:
    args = parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    failures: list[str] = []
    entries: list[dict[str, Any]] = []

    for spec in DEFAULT_EVIDENCE:
        entry: dict[str, Any] = {
            "key": spec.key,
            "kind": spec.kind,
            "source": str(spec.path),
            "required": spec.required,
        }

        if not spec.path.exists():
            entry["status"] = "MISSING"
            message = f"{spec.key}: missing {spec.path}"
            entry["failures"] = [message]
            if spec.required:
                failures.append(message)
            entries.append(entry)
            continue

        copied = copy_artifact(spec.path, args.output_dir)
        entry["bundle_path"] = str(copied.relative_to(args.output_dir))

        if spec.path.suffix == ".json":
            status, item_failures, summary = check_json_spec(spec, read_json(spec.path))
        else:
            status, item_failures, summary = check_text_spec(
                spec,
                spec.path.read_text(encoding="utf-8"),
            )

        entry["status"] = status
        entry["summary"] = summary
        entry["failures"] = item_failures
        failures.extend(item_failures)
        entries.append(entry)

    index = {
        "type": "release_evidence_bundle",
        "tag": args.tag,
        "verdict": "FAIL" if failures else "PASS",
        "readiness": "release-evidence-ready" if not failures else "not-ready",
        "required_evidence_count": sum(1 for spec in DEFAULT_EVIDENCE if spec.required),
        "copied_evidence_count": sum(1 for entry in entries if entry.get("bundle_path")),
        "failures": failures,
        "evidence": entries,
        "single_command": (
            "python3 benchmarks/python/package_release_evidence_bundle.py "
            f"--output-dir {args.output_dir} "
            "--fail-on-fail"
        ),
    }

    index_path = args.output_dir / "release-evidence-index.json"
    index_path.write_text(json.dumps(index, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    print(
        "release_evidence_bundle",
        index["verdict"],
        "copied",
        index["copied_evidence_count"],
        "required",
        index["required_evidence_count"],
        "failures",
        len(failures),
        index_path,
    )

    if args.fail_on_fail and failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
