#!/usr/bin/env python3
"""Validate resident service exits before MLX import when its port is occupied."""

from __future__ import annotations

import argparse
import json
import socket
import subprocess
import sys
from pathlib import Path
from typing import Any


def run(cmd: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, check=False, capture_output=True, text=True, timeout=60)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-json", type=Path, required=True)
    parser.add_argument("--tag", default="m224-port-preflight")
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[2]
    service = root / "benchmarks" / "python" / "resident_mlx_service.py"
    failures: list[str] = []

    import_probe = run(
        [
            sys.executable,
            "-c",
            (
                "import sys;"
                "import mlx_engine.resident_service;"
                "print('mlx.core' in sys.modules)"
            ),
        ]
    )
    if import_probe.returncode != 0:
        failures.append(f"resident_service import probe failed: {import_probe.stderr.strip()}")
    if import_probe.stdout.strip() != "False":
        failures.append("resident_service imported mlx.core at module import time")

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as occupied:
        occupied.bind(("127.0.0.1", 0))
        occupied.listen(1)
        port = int(occupied.getsockname()[1])
        launch = run(
            [
                sys.executable,
                str(service),
                "--model",
                "/definitely/missing/model",
                "--host",
                "127.0.0.1",
                "--port",
                str(port),
                "--warmup-mode",
                "off",
            ]
        )

    if launch.returncode != 98:
        failures.append(f"expected exit 98 for occupied port, got {launch.returncode}")
    if "port unavailable before MLX import" not in launch.stderr:
        failures.append("occupied-port launch did not report pre-MLX port unavailability")
    if "model config" in launch.stderr or "model access" in launch.stderr:
        failures.append("occupied-port launch reached model validation after port failure")

    output: dict[str, Any] = {
        "type": "resident_port_preflight_probe",
        "tag": args.tag,
        "verdict": "PASS" if not failures else "FAIL",
        "readiness": "resident-port-preflight-ready" if not failures else "not-ready",
        "import_probe": {
            "returncode": import_probe.returncode,
            "stdout": import_probe.stdout.strip(),
            "stderr": import_probe.stderr.strip(),
        },
        "occupied_port_launch": {
            "returncode": launch.returncode,
            "stderr": launch.stderr.strip(),
            "stdout": launch.stdout.strip(),
        },
        "failures": failures,
    }
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n")
    print("resident_port_preflight_probe", output["verdict"], "failures", len(failures), args.output_json)
    for failure in failures:
        print("failure", failure)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
