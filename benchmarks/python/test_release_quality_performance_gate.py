#!/usr/bin/env python3
"""Unit tests for release_quality_performance_gate."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent))
import release_quality_performance_gate as gate


def comparison_payload(*, candidate_points: int = 130, verdict: str = "PASS") -> dict:
    summary = {
        "case_count": 13,
        "pass_count": 13,
        "total_quality_points": 130,
        "max_quality_points": 130,
        "max_repetition_score": 0.0,
        "mean_service_request_ms": 370.487,
    }
    candidate_summary = dict(summary)
    candidate_summary["total_quality_points"] = candidate_points
    return {
        "type": "response_quality_regression_comparison",
        "verdict": verdict,
        "readiness": "response-quality-regression-ready",
        "baseline": {"path": "baseline.json", "summary": summary},
        "candidate": {"path": "candidate.json", "summary": candidate_summary},
        "failures": [],
    }


class ReleaseQualityPerformanceGateTests(unittest.TestCase):
    def test_response_quality_comparison_ready_passes_m258_baseline(self) -> None:
        self.assertEqual([], gate.response_quality_comparison_ready(comparison_payload()))

    def test_response_quality_comparison_rejects_quality_point_drop(self) -> None:
        failures = gate.response_quality_comparison_ready(
            comparison_payload(candidate_points=129)
        )
        self.assertTrue(any("candidate.quality_points" in failure for failure in failures))

    def test_response_quality_comparison_rejects_self_comparison(self) -> None:
        payload = comparison_payload()
        payload["candidate"]["path"] = payload["baseline"]["path"]
        failures = gate.response_quality_comparison_ready(payload)
        self.assertTrue(any("reuses the baseline" in failure for failure in failures))

    def test_response_quality_summary_includes_points_and_latency(self) -> None:
        summary = gate.summarize_payload(comparison_payload())
        self.assertEqual("130/130", summary["baseline_quality_points"])
        self.assertEqual("130/130", summary["candidate_quality_points"])
        self.assertEqual(370.487, summary["candidate_mean_service_request_ms"])

    def test_release_gate_fails_when_response_quality_argument_omitted(self) -> None:
        with TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            code = gate.main_with_args(
                SimpleNamespace(
                    output_json=tmp_path / "gate.json",
                    output_md=None,
                    tag="test",
                    response_quality_comparison_json=None,
                    fail_on_fail=True,
                )
            )
            self.assertEqual(1, code)
            self.assertIn(
                "missing --response-quality-comparison-json",
                (tmp_path / "gate.json").read_text(),
            )


if __name__ == "__main__":
    unittest.main()
