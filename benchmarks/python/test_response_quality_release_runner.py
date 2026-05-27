#!/usr/bin/env python3
"""Unit tests for run_response_quality_release_gate."""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_response_quality_release_gate as runner


class ResponseQualityReleaseRunnerTests(unittest.TestCase):
    def test_artifact_summary_extracts_gate_count(self) -> None:
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "gate.json"
            path.write_text(
                json.dumps(
                    {
                        "type": "quality_preserving_release_gate",
                        "tag": "test",
                        "verdict": "PASS",
                        "gate_count": 16,
                        "failures": [],
                    }
                )
            )

            summary = runner.artifact_summary(path)

            self.assertEqual("PASS", summary["verdict"])
            self.assertEqual(16, summary["gate_count"])
            self.assertEqual(0, summary["failure_count"])

    def test_write_markdown_records_failures(self) -> None:
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "manifest.md"
            runner.write_markdown(
                path,
                {
                    "verdict": "FAIL",
                    "readiness": "not-ready",
                    "tag": "test",
                    "artifacts": {},
                    "failures": ["candidate failed"],
                },
            )

            text = path.read_text()
            self.assertIn("candidate failed", text)
            self.assertIn("Verdict: `FAIL`", text)


if __name__ == "__main__":
    unittest.main()
