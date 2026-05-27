#!/usr/bin/env python3
"""Unit tests for response_quality_regression_harness."""

from __future__ import annotations

import unittest
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent))
import response_quality_regression_harness as harness


CASE = {
    "id": "exact_answer",
    "category": "instruction_following",
    "required": ["QUALITY_OK"],
}


class ResponseQualityRegressionHarnessTests(unittest.TestCase):
    def test_compare_passes_identical_quality(self) -> None:
        row = harness.build_row(CASE, raw_text="QUALITY_OK")
        baseline = {"rows": [row]}
        candidate = {"rows": [dict(row)]}

        comparisons, failures = harness.compare_rows(
            baseline,
            candidate,
            max_quality_point_drop=0,
            max_repetition_delta=0.05,
            max_length_drift_ratio=0.5,
        )

        self.assertEqual([], failures)
        self.assertEqual("PASS", comparisons[0]["verdict"])

    def test_compare_fails_missing_required_marker(self) -> None:
        baseline_row = harness.build_row(CASE, raw_text="QUALITY_OK")
        candidate_row = harness.build_row(CASE, raw_text="WRONG")

        _, failures = harness.compare_rows(
            {"rows": [baseline_row]},
            {"rows": [candidate_row]},
            max_quality_point_drop=0,
            max_repetition_delta=0.05,
            max_length_drift_ratio=0.5,
        )

        self.assertTrue(any("required marker" in failure for failure in failures))
        self.assertTrue(any("candidate failures" in failure for failure in failures))

    def test_compare_fails_repetition_regression(self) -> None:
        baseline_row = harness.build_row(CASE, raw_text="QUALITY_OK")
        candidate_row = harness.build_row(
            CASE,
            raw_text="QUALITY_OK loop loop loop loop loop loop loop loop loop",
        )

        _, failures = harness.compare_rows(
            {"rows": [baseline_row]},
            {"rows": [candidate_row]},
            max_quality_point_drop=10,
            max_repetition_delta=0.0,
            max_length_drift_ratio=1.0,
        )

        self.assertTrue(any("repetition delta" in failure for failure in failures))

    def test_compare_command_rejects_failed_candidate_artifact(self) -> None:
        row = harness.build_row(CASE, raw_text="QUALITY_OK")
        with TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            baseline = tmp_path / "baseline.json"
            candidate = tmp_path / "candidate.json"
            output = tmp_path / "output.json"
            baseline.write_text('{"verdict": "PASS", "rows": [' + harness.json.dumps(row) + "]}")
            candidate.write_text('{"verdict": "FAIL", "rows": [' + harness.json.dumps(row) + "]}")

            code = harness.compare(
                SimpleNamespace(
                    baseline_json=baseline,
                    candidate_json=candidate,
                    output_json=output,
                    output_md=None,
                    tag="test",
                    max_quality_point_drop=0,
                    max_repetition_delta=0.05,
                    max_length_drift_ratio=0.5,
                    fail_on_fail=True,
                )
            )

            self.assertEqual(1, code)
            self.assertIn("candidate verdict", output.read_text())


if __name__ == "__main__":
    unittest.main()
