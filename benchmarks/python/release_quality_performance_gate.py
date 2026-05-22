#!/usr/bin/env python3
"""Release-blocking gate for quality-preserving MLX performance evidence."""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable


@dataclass(frozen=True)
class GateSpec:
    key: str
    path: Path
    category: str
    expected_verdict: str = "PASS"
    extra_checks: tuple[Callable[[dict[str, Any]], list[str]], ...] = field(default_factory=tuple)


def no_failures(payload: dict[str, Any]) -> list[str]:
    failures = payload.get("failures")
    return [f"failures={failures!r}"] if failures else []


def swap_accept(payload: dict[str, Any]) -> list[str]:
    return (
        []
        if payload.get("swap_decision") == "ACCEPT"
        else [f"swap_decision={payload.get('swap_decision')!r}"]
    )


def min_speedup(payload: dict[str, Any], *, key: str, threshold: float) -> list[str]:
    value = payload.get(key)
    if not isinstance(value, (int, float)):
        return [f"{key}=missing"]
    return [] if value >= threshold else [f"{key}={value!r} < {threshold!r}"]


def max_value(payload: dict[str, Any], *, key: str, threshold: float) -> list[str]:
    value = payload.get(key)
    if not isinstance(value, (int, float)):
        return [f"{key}=missing"]
    return [] if value <= threshold else [f"{key}={value!r} > {threshold!r}"]


def lower_memory_metrics(payload: dict[str, Any]) -> list[str]:
    metrics = payload.get("metrics") or {}
    failures: list[str] = []
    for key, threshold in (
        ("max_active_memory_gb", 16.0),
        ("max_peak_memory_gb", 16.0),
        ("max_cache_memory_limit_mb", 64.0),
        ("conversion_prefill_tokens", 32.0),
    ):
        value = metrics.get(key)
        if not isinstance(value, (int, float)):
            failures.append(f"metrics.{key}=missing")
        elif value > threshold:
            failures.append(f"metrics.{key}={value!r} > {threshold!r}")
    return failures


def first_duplicate_service_budget(payload: dict[str, Any], *, threshold: float) -> list[str]:
    rows = payload.get("rows") or []
    if len(rows) < 2:
        return ["rows[1]=missing"]
    first_duplicate = rows[1] or {}
    value = first_duplicate.get("service_request_ms")
    if not isinstance(value, (int, float)):
        return ["rows[1].service_request_ms=missing"]
    return (
        []
        if value <= threshold
        else [f"rows[1].service_request_ms={value!r} > {threshold!r}"]
    )


def lifecycle_ready(payload: dict[str, Any]) -> list[str]:
    return (
        []
        if payload.get("readiness") == "resident-lifecycle-regression-ready"
        else [f"readiness={payload.get('readiness')!r}"]
    )


def copied_bundle(payload: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    if payload.get("copied_evidence_count") != payload.get("required_evidence_count"):
        failures.append(
            "copied_evidence_count does not match required_evidence_count: "
            f"{payload.get('copied_evidence_count')!r} != {payload.get('required_evidence_count')!r}"
        )
    return failures


def python_package_gpu_ready(payload: dict[str, Any]) -> list[str]:
    probe = payload.get("probe_result") or payload
    failures: list[str] = []
    if probe.get("metal_available") is not True:
        failures.append(f"metal_available={probe.get('metal_available')!r}")
    if "Device(gpu" not in str(probe.get("default_device")):
        failures.append(f"default_device={probe.get('default_device')!r}")
    minimal_env = probe.get("minimal_env") or {}
    if minimal_env.get("returncode") != 0:
        failures.append(f"minimal_env.returncode={minimal_env.get('returncode')!r}")
    if "Device(gpu" not in str(minimal_env.get("stdout")):
        failures.append(f"minimal_env.stdout={minimal_env.get('stdout')!r}")
    return failures


DEFAULT_GATES = [
    GateSpec(
        "deterministic_quality_adapted",
        Path("artifacts/m241-bounded-low-memory-live-revalidation/chat-template-quality-adapted-m241-qwen25-coder-14b-low-memory.json"),
        "quality",
        extra_checks=(no_failures,),
    ),
    GateSpec(
        "quality_threshold",
        Path("artifacts/m241-bounded-low-memory-live-revalidation/quality-threshold-gate-m241-qwen25-coder-14b-low-memory.json"),
        "quality",
        extra_checks=(no_failures,),
    ),
    GateSpec(
        "model_swap_acceptance",
        Path("artifacts/m231-model-swap-artifact-freshness-refresh/model-swap-acceptance-m231-qwen25-coder-14b.json"),
        "model_swap",
        extra_checks=(no_failures, swap_accept),
    ),
    GateSpec(
        "routing_policy",
        Path("artifacts/m234-lower-memory-default-routing-policy/lower-memory-default-routing-policy-gate-m234.json"),
        "routing",
        extra_checks=(no_failures,),
    ),
    GateSpec(
        "product_mode_routing",
        Path("artifacts/m238-lower-memory-route-product-smoke/product-mode-metadata-probe-m238.json"),
        "routing",
        extra_checks=(no_failures,),
    ),
    GateSpec(
        "live_request_profile_routing",
        Path("artifacts/m238-lower-memory-route-product-smoke/live-request-profile-metadata-m238.json"),
        "routing",
        extra_checks=(no_failures,),
    ),
    GateSpec(
        "bounded_first_hit_benchmark",
        Path("artifacts/m237-bounded-first-hit-live-revalidation/dax-bounded-first-hit-m237-qwen25-coder-14b.json"),
        "first_hit",
        extra_checks=(
            no_failures,
            lambda payload: min_speedup(
                payload,
                key="best_hit_speedup_vs_baseline",
                threshold=5.0,
            ),
            lambda payload: max_value(
                payload,
                key="best_hit_service_request_ms",
                threshold=250.0,
            ),
        ),
    ),
    GateSpec(
        "bounded_first_hit_conversion",
        Path("artifacts/m237-bounded-first-hit-live-revalidation/dax-first-hit-conversion-gate-m237-qwen25-coder-14b.json"),
        "first_hit",
        extra_checks=(no_failures,),
    ),
    GateSpec(
        "first_duplicate_service_budget",
        Path("artifacts/m247-first-hit-regression-recovery/dax-first-hit-m247-qwen25-coder-14b.json"),
        "first_hit",
        extra_checks=(
            no_failures,
            lambda payload: min_speedup(
                payload,
                key="best_hit_speedup_vs_baseline",
                threshold=5.0,
            ),
            lambda payload: first_duplicate_service_budget(
                payload,
                threshold=250.0,
            ),
        ),
    ),
    GateSpec(
        "lower_memory_benchmark",
        Path("artifacts/m241-bounded-low-memory-live-revalidation/dax-bounded-low-memory-m241-qwen25-coder-14b.json"),
        "lower_memory",
        extra_checks=(
            no_failures,
            lambda payload: min_speedup(
                payload,
                key="best_hit_speedup_vs_baseline",
                threshold=2.0,
            ),
            lambda payload: max_value(
                payload,
                key="best_hit_service_request_ms",
                threshold=250.0,
            ),
        ),
    ),
    GateSpec(
        "lower_memory_runtime",
        Path("artifacts/m241-bounded-low-memory-live-revalidation/lower-memory-runtime-gate-m241-qwen25-coder-14b.json"),
        "lower_memory",
        extra_checks=(no_failures, lower_memory_metrics),
    ),
    GateSpec(
        "lower_memory_first_hit_conversion",
        Path("artifacts/m241-bounded-low-memory-live-revalidation/dax-low-memory-first-hit-conversion-gate-m241-qwen25-coder-14b.json"),
        "lower_memory",
        extra_checks=(no_failures,),
    ),
    GateSpec(
        "lifecycle_regression",
        Path("artifacts/m232-resident-lifecycle-regression-gate/resident-lifecycle-regression-gate-m232.json"),
        "lifecycle",
        extra_checks=(no_failures, lifecycle_ready),
    ),
    GateSpec(
        "release_evidence_bundle",
        Path("artifacts/m240-release-evidence-bundle/release-evidence-bundle/release-evidence-index.json"),
        "release_packaging",
        extra_checks=(no_failures, copied_bundle),
    ),
    GateSpec(
        "python_package_tmux_validation",
        Path("artifacts/m244-python-package-tmux-validation/python-package-validation-m244-harness.json"),
        "python_package",
        extra_checks=(no_failures, python_package_gpu_ready),
    ),
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-json",
        type=Path,
        default=Path("artifacts/m242-quality-preserving-release-gate/quality-preserving-release-gate-m242.json"),
    )
    parser.add_argument(
        "--output-md",
        type=Path,
        default=Path("artifacts/m242-quality-preserving-release-gate/quality-preserving-release-gate-m242.md"),
    )
    parser.add_argument("--tag", default="m242-quality-preserving-release-gate")
    parser.add_argument("--fail-on-fail", action="store_true")
    return parser.parse_args()


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def summarize_payload(payload: dict[str, Any]) -> dict[str, Any]:
    summary = {
        "type": payload.get("type"),
        "verdict": payload.get("verdict"),
        "readiness": payload.get("readiness"),
    }
    for key in (
        "swap_decision",
        "best_hit_speedup_vs_baseline",
        "best_hit_service_request_ms",
        "baseline_service_request_ms",
        "copied_evidence_count",
        "required_evidence_count",
        "metal_available",
        "default_device",
    ):
        if key in payload:
            summary[key] = payload.get(key)
    if payload.get("probe_result"):
        probe = payload["probe_result"]
        summary["probe_result"] = {
            "verdict": probe.get("verdict"),
            "metal_available": probe.get("metal_available"),
            "default_device": probe.get("default_device"),
            "minimal_env_stdout": (probe.get("minimal_env") or {}).get("stdout"),
        }
    if payload.get("type") == "dax_repeated_context_bench":
        rows = payload.get("rows") or []
        if len(rows) > 1:
            summary["first_duplicate_service_request_ms"] = (rows[1] or {}).get(
                "service_request_ms"
            )
    if payload.get("metrics"):
        metrics = payload["metrics"]
        summary["metrics"] = {
            key: metrics.get(key)
            for key in (
                "max_active_memory_gb",
                "max_peak_memory_gb",
                "max_cache_memory_limit_mb",
                "conversion_prefill_tokens",
            )
            if key in metrics
        }
    return summary


def evaluate_gate(spec: GateSpec) -> dict[str, Any]:
    entry: dict[str, Any] = {
        "key": spec.key,
        "category": spec.category,
        "path": str(spec.path),
    }
    if not spec.path.exists():
        entry["status"] = "MISSING"
        entry["failures"] = [f"missing {spec.path}"]
        return entry

    payload = load_json(spec.path)
    failures: list[str] = []
    if payload.get("verdict") != spec.expected_verdict:
        failures.append(
            f"verdict={payload.get('verdict')!r}, expected {spec.expected_verdict!r}"
        )
    for check in spec.extra_checks:
        failures.extend(check(payload))

    entry["status"] = "PASS" if not failures else "FAIL"
    entry["failures"] = failures
    entry["summary"] = summarize_payload(payload)
    return entry


def write_markdown(path: Path, output: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        f"# {output['tag']} Quality-Preserving Release Gate",
        "",
        f"Verdict: `{output['verdict']}`",
        f"Readiness: `{output['readiness']}`",
        "",
        "## Gate Coverage",
        "",
    ]
    for entry in output["gates"]:
        lines.append(
            f"- `{entry['key']}` ({entry['category']}): `{entry['status']}` - `{entry['path']}`"
        )
    lines.extend(["", "## Failures", ""])
    if output["failures"]:
        lines.extend(f"- `{failure}`" for failure in output["failures"])
    else:
        lines.append("- none")
    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    args = parse_args()
    gates = [evaluate_gate(spec) for spec in DEFAULT_GATES]
    failures = [
        f"{entry['key']}: {failure}"
        for entry in gates
        for failure in entry.get("failures", [])
    ]
    categories = sorted({spec.category for spec in DEFAULT_GATES})
    output = {
        "type": "quality_preserving_release_gate",
        "tag": args.tag,
        "verdict": "PASS" if not failures else "FAIL",
        "readiness": "quality-preserving-release-ready" if not failures else "not-ready",
        "categories": categories,
        "gate_count": len(gates),
        "failures": failures,
        "gates": gates,
    }
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if args.output_md:
        write_markdown(args.output_md, output)
    print(
        "quality_preserving_release_gate",
        output["verdict"],
        "gates",
        len(gates),
        "failures",
        len(failures),
        args.output_json,
    )
    if args.fail_on_fail and failures:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
