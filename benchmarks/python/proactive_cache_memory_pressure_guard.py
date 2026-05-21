#!/usr/bin/env python3
"""Gate proactive prefix-cache memory bounds against first-hit performance."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from mlx_engine.resident_service import runtime_profile_defaults


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text())


def add_check(
    checks: list[dict[str, Any]],
    failures: list[str],
    *,
    label: str,
    actual: Any,
    operator: str,
    threshold: Any,
) -> None:
    if operator == "==":
        passed = actual == threshold
    elif operator == "<=":
        passed = actual is not None and float(actual) <= float(threshold)
    elif operator == ">=":
        passed = actual is not None and float(actual) >= float(threshold)
    else:
        raise ValueError(f"unsupported operator: {operator}")
    verdict = "PASS" if passed else "FAIL"
    checks.append(
        {
            "label": label,
            "actual": actual,
            "operator": operator,
            "threshold": threshold,
            "verdict": verdict,
        }
    )
    if not passed:
        failures.append(f"{label}: {actual!r} {operator} {threshold!r} failed")


def first_request_metrics(artifact: dict[str, Any]) -> dict[str, Any]:
    baseline = artifact.get("baseline")
    if isinstance(baseline, dict):
        metrics = baseline.get("engine_metrics")
        if isinstance(metrics, dict):
            return metrics
    rows = artifact.get("rows") or []
    first = next(
        (
            row
            for row in rows
            if row.get("type") in {"request", "dax_repeated_context_bench_row"}
        ),
        None,
    )
    if first is None:
        raise ValueError("artifact has no request rows")
    metrics = first.get("engine_metrics")
    return metrics if isinstance(metrics, dict) else first


def gate(args: argparse.Namespace) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    failures: list[str] = []
    repeated = load_json(args.repeated_context_json)
    promotion = load_json(args.promotion_gate_json)
    first_hit_config = runtime_profile_defaults("agent-workspace-first-hit")["config"]
    low_memory_config = runtime_profile_defaults("agent-workspace-low-memory")["config"]
    first_metrics = first_request_metrics(repeated)
    promotion_metrics = promotion.get("metrics") or {}

    profile_checks = [
        (
            "first_hit.prefix_cache_memory_limit_mb",
            first_hit_config.get("prefix_cache_memory_limit_mb"),
            "<=",
            args.max_first_hit_memory_limit_mb,
        ),
        (
            "first_hit.prefix_cache_memory_limit_mb_nonzero",
            first_hit_config.get("prefix_cache_memory_limit_mb"),
            ">=",
            1.0,
        ),
        (
            "first_hit.prefix_cache_max_entries",
            first_hit_config.get("prefix_cache_max_entries"),
            "<=",
            args.max_first_hit_entries,
        ),
        (
            "first_hit.prefix_cache_min_entries",
            first_hit_config.get("prefix_cache_min_entries"),
            ">=",
            args.min_first_hit_entries,
        ),
        (
            "low_memory.prefix_cache_memory_limit_mb",
            low_memory_config.get("prefix_cache_memory_limit_mb"),
            "<=",
            args.max_low_memory_limit_mb,
        ),
        (
            "low_memory.prefix_cache_max_entries",
            low_memory_config.get("prefix_cache_max_entries"),
            "<=",
            args.max_low_memory_entries,
        ),
        (
            "low_memory.prefix_cache_min_entries",
            low_memory_config.get("prefix_cache_min_entries"),
            ">=",
            args.min_low_memory_entries,
        ),
    ]
    for label, actual, operator, threshold in profile_checks:
        add_check(
            checks,
            failures,
            label=label,
            actual=actual,
            operator=operator,
            threshold=threshold,
        )

    add_check(
        checks,
        failures,
        label="m229.first_request.proactive_prefix_cache_created",
        actual=first_metrics.get("proactive_prefix_cache_created"),
        operator=">=",
        threshold=args.min_proactive_prefixes_created,
    )
    add_check(
        checks,
        failures,
        label="m229.first_request.proactive_prefix_cache_trim_failures",
        actual=first_metrics.get("proactive_prefix_cache_trim_failures"),
        operator="<=",
        threshold=0,
    )
    add_check(
        checks,
        failures,
        label="m229.first_request.cache_memory_mb",
        actual=(
            float(first_metrics.get("cache_memory_bytes")) / (1024 * 1024)
            if first_metrics.get("cache_memory_bytes") is not None
            else None
        ),
        operator="<=",
        threshold=args.max_observed_cache_memory_mb,
    )
    add_check(
        checks,
        failures,
        label="m230.first_duplicate_service_ms",
        actual=promotion_metrics.get("first_duplicate_service_ms"),
        operator="<=",
        threshold=args.max_first_duplicate_service_ms,
    )
    add_check(
        checks,
        failures,
        label="m230.first_duplicate_cache_hit",
        actual=promotion_metrics.get("first_duplicate_cache_hit"),
        operator="==",
        threshold=True,
    )
    add_check(
        checks,
        failures,
        label="m230.first_duplicate_prefill_tokens",
        actual=promotion_metrics.get("first_duplicate_prefill_tokens"),
        operator="<=",
        threshold=args.max_first_duplicate_prefill_tokens,
    )
    add_check(
        checks,
        failures,
        label="m230.mature_hit_speedup_vs_baseline",
        actual=promotion_metrics.get("mature_hit_speedup_vs_baseline"),
        operator=">=",
        threshold=args.min_mature_hit_speedup,
    )

    return {
        "type": "proactive_cache_memory_pressure_guard",
        "tag": args.tag,
        "verdict": "PASS" if not failures else "FAIL",
        "readiness": "proactive-cache-memory-guard-ready" if not failures else "not-ready",
        "profiles": {
            "agent-workspace-first-hit": {
                "prefix_cache_max_entries": first_hit_config.get("prefix_cache_max_entries"),
                "prefix_cache_memory_limit_mb": first_hit_config.get("prefix_cache_memory_limit_mb"),
                "prefix_cache_min_entries": first_hit_config.get("prefix_cache_min_entries"),
            },
            "agent-workspace-low-memory": {
                "prefix_cache_max_entries": low_memory_config.get("prefix_cache_max_entries"),
                "prefix_cache_memory_limit_mb": low_memory_config.get("prefix_cache_memory_limit_mb"),
                "prefix_cache_min_entries": low_memory_config.get("prefix_cache_min_entries"),
            },
        },
        "observed_m229_first_request": {
            "proactive_prefix_cache_created": first_metrics.get("proactive_prefix_cache_created"),
            "proactive_prefix_cache_tokens": first_metrics.get("proactive_prefix_cache_tokens"),
            "proactive_prefix_cache_trim_failures": first_metrics.get("proactive_prefix_cache_trim_failures"),
            "cache_memory_bytes": first_metrics.get("cache_memory_bytes"),
        },
        "carried_forward_performance": {
            "promotion_gate": str(args.promotion_gate_json),
            "first_duplicate_service_ms": promotion_metrics.get("first_duplicate_service_ms"),
            "first_duplicate_prefill_tokens": promotion_metrics.get("first_duplicate_prefill_tokens"),
            "first_duplicate_cache_hit": promotion_metrics.get("first_duplicate_cache_hit"),
            "mature_hit_speedup_vs_baseline": promotion_metrics.get("mature_hit_speedup_vs_baseline"),
        },
        "checks": checks,
        "failures": failures,
    }


def write_markdown(path: Path, output: dict[str, Any]) -> None:
    lines = [
        "# M233 Proactive Cache Memory-Pressure Guard",
        "",
        f"Verdict: `{output['verdict']}`",
        f"Readiness: `{output['readiness']}`",
        "",
        "## Profiles",
        "",
        "| Profile | Max entries | Memory limit MB | Min entries |",
        "| --- | ---: | ---: | ---: |",
    ]
    for name, profile in output["profiles"].items():
        lines.append(
            f"| `{name}` | `{profile['prefix_cache_max_entries']}` | "
            f"`{profile['prefix_cache_memory_limit_mb']}` | "
            f"`{profile['prefix_cache_min_entries']}` |"
        )
    lines.extend(["", "## Checks", "", "| Check | Verdict | Actual | Threshold |", "| --- | --- | ---: | ---: |"])
    for check in output["checks"]:
        lines.append(
            f"| `{check['label']}` | `{check['verdict']}` | "
            f"`{check['actual']}` | `{check['operator']} {check['threshold']}` |"
        )
    failure_lines = [f"- `{failure}`" for failure in output["failures"]] or ["- none"]
    lines.extend(["", "## Failures", "", *failure_lines, ""])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repeated-context-json", type=Path, required=True)
    parser.add_argument("--promotion-gate-json", type=Path, required=True)
    parser.add_argument("--output-json", type=Path, required=True)
    parser.add_argument("--output-md", type=Path, required=True)
    parser.add_argument("--tag", default="m233-proactive-cache-memory-pressure")
    parser.add_argument("--max-first-hit-memory-limit-mb", type=float, default=128.0)
    parser.add_argument("--max-first-hit-entries", type=float, default=8.0)
    parser.add_argument("--min-first-hit-entries", type=float, default=5.0)
    parser.add_argument("--max-low-memory-limit-mb", type=float, default=64.0)
    parser.add_argument("--max-low-memory-entries", type=float, default=4.0)
    parser.add_argument("--min-low-memory-entries", type=float, default=1.0)
    parser.add_argument("--min-proactive-prefixes-created", type=float, default=5.0)
    parser.add_argument("--max-observed-cache-memory-mb", type=float, default=64.0)
    parser.add_argument("--max-first-duplicate-service-ms", type=float, default=250.0)
    parser.add_argument("--max-first-duplicate-prefill-tokens", type=float, default=16.0)
    parser.add_argument("--min-mature-hit-speedup", type=float, default=5.0)
    parser.add_argument("--fail-on-fail", action="store_true")
    args = parser.parse_args()

    output = gate(args)
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n")
    write_markdown(args.output_md, output)
    print(
        "proactive_cache_memory_pressure_guard",
        output["verdict"],
        output["readiness"],
        "checks",
        len(output["checks"]),
        "failures",
        len(output["failures"]),
        args.output_json,
    )
    for failure in output["failures"]:
        print("failure", failure)
    return 1 if args.fail_on_fail and output["failures"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
