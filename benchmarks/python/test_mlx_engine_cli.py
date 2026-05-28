#!/usr/bin/env python3
"""Unit tests for bin/mlx-engine CLI wiring."""

from __future__ import annotations

import importlib.util
from importlib.machinery import SourceFileLoader
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]
CLI_PATH = ROOT / "bin" / "mlx-engine"


def load_cli():
    loader = SourceFileLoader("mlx_engine_cli", str(CLI_PATH))
    spec = importlib.util.spec_from_loader("mlx_engine_cli", loader)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"failed to load {CLI_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class MLXEngineCLITests(unittest.TestCase):
    def test_response_quality_release_parser_defaults(self) -> None:
        cli = load_cli()
        parser = cli.build_parser()

        args = parser.parse_args(["response-quality-release", "--fail-on-fail"])

        self.assertEqual("http://127.0.0.1:8773", args.base_url)
        self.assertEqual("local-mlx", args.model)
        self.assertEqual("interactive", args.runtime_profile)
        self.assertEqual(0.0, args.temperature)
        self.assertEqual(1.0, args.top_p)
        self.assertEqual(260, args.seed)
        self.assertTrue(args.fail_on_fail)
        self.assertIs(args.func, cli.response_quality_release)

    def test_response_quality_release_invokes_runner(self) -> None:
        cli = load_cli()
        parser = cli.build_parser()
        args = parser.parse_args(
            [
                "response-quality-release",
                "--candidate-json",
                "candidate.json",
                "--output-dir",
                "out",
                "--tag",
                "test-tag",
                "--fail-on-fail",
            ]
        )

        with patch.object(cli.subprocess, "call", return_value=0) as call:
            code = cli.response_quality_release(args)

        self.assertEqual(0, code)
        cmd = call.call_args.args[0]
        self.assertIn(str(cli.RESPONSE_QUALITY_RELEASE), cmd)
        self.assertIn("--candidate-json", cmd)
        self.assertIn("candidate.json", cmd)
        self.assertIn("--fail-on-fail", cmd)


if __name__ == "__main__":
    unittest.main()
