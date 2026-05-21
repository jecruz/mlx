#!/usr/bin/env python3
"""Repeatable resident lifecycle regression gate.

This gate intentionally avoids loading a large MLX model. It verifies the
critical lifecycle safety contracts with small probes:

- shutdown joins warmup and async prefix-cache build threads
- occupied-port startup fails before MLX import/model validation
- reload/unload/lifespan routes still call the shutdown path
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any


def run(cmd: list[str], *, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, cwd=cwd, check=False, capture_output=True, text=True, timeout=90)


def parse_json_stdout(stdout: str) -> dict[str, Any]:
    start = stdout.find("{")
    if start < 0:
        raise ValueError("stdout did not contain a JSON object")
    return json.loads(stdout[start:])


def add_check(
    checks: list[dict[str, Any]],
    failures: list[str],
    *,
    label: str,
    passed: bool,
    detail: str,
) -> None:
    checks.append(
        {
            "label": label,
            "verdict": "PASS" if passed else "FAIL",
            "detail": detail,
        }
    )
    if not passed:
        failures.append(f"{label}: {detail}")


def source_contracts(service_path: Path) -> list[dict[str, Any]]:
    source = service_path.read_text()
    contracts = [
        {
            "label": "resident_engine_shutdown_sets_event",
            "needle": "self.request_shutdown()",
            "detail": "ResidentEngine.shutdown must signal shutdown_requested before joining background work",
        },
        {
            "label": "reload_requests_old_engine_shutdown",
            "needle": "old_engine.request_shutdown()",
            "detail": "EngineManager.reload/unload must request old-engine shutdown before replacement/removal",
        },
        {
            "label": "reload_or_unload_joins_old_engine",
            "needle": "old_engine.shutdown()",
            "detail": "EngineManager.reload/unload must join old-engine background work",
        },
        {
            "label": "lifespan_shutdown_calls_manager",
            "needle": "manager.shutdown()",
            "detail": "FastAPI lifespan shutdown must call EngineManager.shutdown",
        },
        {
            "label": "port_preflight_before_mlx_import",
            "needle": "port unavailable before MLX import",
            "detail": "occupied-port startup must fail before importing MLX/model validation",
        },
    ]
    return [
        {
            "label": contract["label"],
            "verdict": "PASS" if contract["needle"] in source else "FAIL",
            "needle": contract["needle"],
            "detail": contract["detail"],
        }
        for contract in contracts
    ]


def write_markdown(path: Path, output: dict[str, Any]) -> None:
    lines = [
        "# M232 Resident Lifecycle Regression Gate",
        "",
        f"Verdict: `{output['verdict']}`",
        f"Readiness: `{output['readiness']}`",
        "",
        "## Probe Results",
        "",
        f"- Shutdown probe: `{output['probes']['shutdown']['verdict']}`",
        f"- Startup preflight probe: `{output['probes']['startup_preflight']['verdict']}`",
        "",
        "## Checks",
        "",
        "| Check | Verdict | Detail |",
        "| --- | --- | --- |",
    ]
    for check in output["checks"]:
        lines.append(f"| `{check['label']}` | `{check['verdict']}` | `{check['detail']}` |")
    blocker_lines = [f"- `{failure}`" for failure in output["failures"]] or ["- none"]
    lines.extend(["", "## Failures", "", *blocker_lines, ""])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-json", type=Path, required=True)
    parser.add_argument("--output-md", type=Path, required=True)
    parser.add_argument("--port-preflight-json", type=Path, required=True)
    parser.add_argument("--tag", default="m232-resident-lifecycle-regression")
    parser.add_argument("--fail-on-fail", action="store_true")
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[2]
    service_path = root / "mlx_engine" / "resident_service.py"
    shutdown_cmd = [sys.executable, "benchmarks/python/resident_shutdown_safety_probe.py"]
    port_cmd = [
        sys.executable,
        "benchmarks/python/resident_port_preflight_probe.py",
        "--output-json",
        str(args.port_preflight_json),
        "--tag",
        args.tag,
    ]

    shutdown_run = run(shutdown_cmd, cwd=root)
    port_run = run(port_cmd, cwd=root)

    shutdown_payload: dict[str, Any]
    try:
        shutdown_payload = parse_json_stdout(shutdown_run.stdout)
    except Exception as exc:  # pragma: no cover - included in artifact failures
        shutdown_payload = {
            "type": "resident_shutdown_safety_probe",
            "verdict": "FAIL",
            "parse_error": str(exc),
        }
    try:
        port_payload = json.loads(args.port_preflight_json.read_text())
    except Exception as exc:  # pragma: no cover - included in artifact failures
        port_payload = {
            "type": "resident_port_preflight_probe",
            "verdict": "FAIL",
            "parse_error": str(exc),
        }

    checks: list[dict[str, Any]] = []
    failures: list[str] = []
    add_check(
        checks,
        failures,
        label="shutdown_probe.exit_code",
        passed=shutdown_run.returncode == 0,
        detail=f"returncode={shutdown_run.returncode}",
    )
    add_check(
        checks,
        failures,
        label="shutdown_probe.verdict",
        passed=shutdown_payload.get("verdict") == "PASS",
        detail=f"verdict={shutdown_payload.get('verdict')!r}",
    )
    shutdown_result = shutdown_payload.get("result") or {}
    add_check(
        checks,
        failures,
        label="shutdown_probe.joined_warmup",
        passed=shutdown_result.get("warmup_joined") is True
        and shutdown_result.get("warmup_alive_after") is False,
        detail=(
            f"joined={shutdown_result.get('warmup_joined')!r}, "
            f"alive_after={shutdown_result.get('warmup_alive_after')!r}"
        ),
    )
    add_check(
        checks,
        failures,
        label="shutdown_probe.joined_async_cache_builds",
        passed=shutdown_result.get("async_threads_joined") == 1
        and shutdown_result.get("async_threads_alive_after") == 0,
        detail=(
            f"joined={shutdown_result.get('async_threads_joined')!r}, "
            f"alive_after={shutdown_result.get('async_threads_alive_after')!r}"
        ),
    )
    add_check(
        checks,
        failures,
        label="startup_preflight.exit_code",
        passed=port_run.returncode == 0,
        detail=f"returncode={port_run.returncode}",
    )
    add_check(
        checks,
        failures,
        label="startup_preflight.verdict",
        passed=port_payload.get("verdict") == "PASS",
        detail=f"verdict={port_payload.get('verdict')!r}",
    )
    for contract in source_contracts(service_path):
        add_check(
            checks,
            failures,
            label=f"source_contract.{contract['label']}",
            passed=contract["verdict"] == "PASS",
            detail=contract["detail"],
        )

    output = {
        "type": "resident_lifecycle_regression_gate",
        "tag": args.tag,
        "verdict": "PASS" if not failures else "FAIL",
        "readiness": "resident-lifecycle-regression-ready" if not failures else "not-ready",
        "commands": {
            "shutdown_probe": " ".join(shutdown_cmd),
            "startup_preflight_probe": " ".join(port_cmd),
        },
        "probes": {
            "shutdown": {
                "returncode": shutdown_run.returncode,
                "verdict": shutdown_payload.get("verdict"),
                "result": shutdown_payload.get("result"),
            },
            "startup_preflight": {
                "returncode": port_run.returncode,
                "verdict": port_payload.get("verdict"),
                "readiness": port_payload.get("readiness"),
                "artifact": str(args.port_preflight_json),
            },
        },
        "checks": checks,
        "failures": failures,
    }
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n")
    write_markdown(args.output_md, output)
    print(
        "resident_lifecycle_regression_gate",
        output["verdict"],
        output["readiness"],
        "checks",
        len(checks),
        "failures",
        len(failures),
        args.output_json,
    )
    for failure in failures:
        print("failure", failure)
    return 1 if args.fail_on_fail and failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
