#!/usr/bin/env python3
"""Validate the Python MLX package from a Metal-capable shell."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-json", type=Path, required=True)
    parser.add_argument("--tag", default="python-package-validation")
    parser.add_argument("--require-gpu", action="store_true")
    return parser.parse_args()


def run_minimal_env_check() -> dict[str, Any]:
    command = [
        "env",
        "-i",
        f"HOME={os.environ.get('HOME', '')}",
        "PATH=/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin",
        sys.executable,
        "-c",
        "import mlx.core as mx; print(mx.metal.is_available(), mx.default_device())",
    ]
    completed = subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
        timeout=60,
    )
    return {
        "command": command,
        "returncode": completed.returncode,
        "stdout": completed.stdout.strip(),
        "stderr": completed.stderr.strip(),
    }


def main() -> int:
    args = parse_args()
    failures: list[str] = []
    result: dict[str, Any] = {
        "type": "python_package_validation_probe",
        "tag": args.tag,
        "python_executable": sys.executable,
        "python_version": sys.version,
    }

    try:
        import mlx  # type: ignore
        import mlx.core as mx  # type: ignore

        metal_available = bool(mx.metal.is_available())
        default_device = str(mx.default_device())
        result.update(
            {
                "mlx_file": getattr(mlx, "__file__", None),
                "metal_available": metal_available,
                "default_device": default_device,
            }
        )
        if args.require_gpu and not (metal_available and "gpu" in default_device):
            failures.append(
                f"expected Metal GPU device, got metal_available={metal_available}, "
                f"default_device={default_device!r}"
            )
    except BaseException as exc:
        failures.append(f"normal import failed: {type(exc).__name__}: {exc}")

    minimal_env = run_minimal_env_check()
    result["minimal_env"] = minimal_env
    if minimal_env["returncode"] != 0:
        failures.append(f"minimal-env import returned {minimal_env['returncode']}")
    if args.require_gpu and "Device(gpu" not in minimal_env["stdout"]:
        failures.append(f"minimal-env import did not report GPU: {minimal_env['stdout']!r}")

    result["failures"] = failures
    result["verdict"] = "PASS" if not failures else "FAIL"
    result["readiness"] = "python-package-validation-ready" if not failures else "not-ready"

    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(
        "python_package_validation_probe",
        result["verdict"],
        "failures",
        len(failures),
        args.output_json,
        flush=True,
    )
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
