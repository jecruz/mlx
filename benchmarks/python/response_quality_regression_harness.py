#!/usr/bin/env python3
"""Capture and compare response-quality regression evidence.

M257 is intentionally quality-first: a candidate run must preserve semantic
task success, schema validity, stop behavior, and repetition bounds before any
latency improvement is counted as useful.
"""

from __future__ import annotations

import argparse
import json
import statistics
import urllib.request
from pathlib import Path
from typing import Any

from quality_gate_runner import (
    GOLDEN_CASES,
    LONG_CONTEXT_CASE,
    STOP,
    final_answer,
    repetition_score,
)


DEFAULT_CASES = GOLDEN_CASES + [LONG_CONTEXT_CASE]


def request_json(method: str, url: str, payload: dict[str, Any]) -> dict[str, Any]:
    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method=method,
    )
    with urllib.request.urlopen(req, timeout=240) as resp:
        return json.loads(resp.read().decode())


def mean(values: list[float]) -> float | None:
    return round(statistics.fmean(values), 3) if values else None


def quality_points(row: dict[str, Any]) -> int:
    points = 0
    if not row.get("missing"):
        points += 4
    if row.get("json_valid") is not False:
        points += 1
    if not row.get("visible_thinking"):
        points += 1
    if row.get("repetition_score", 1.0) <= row.get("max_repetition_score", 0.2):
        points += 2
    if not row.get("failures"):
        points += 2
    return points


def build_row(
    case: dict[str, Any],
    *,
    raw_text: str,
    metrics: dict[str, Any] | None = None,
    max_repetition_score: float = 0.2,
) -> dict[str, Any]:
    answer = final_answer(raw_text)
    required = case.get("required", [])
    missing = [item for item in required if item not in answer]
    json_valid = None
    if case.get("json_required"):
        try:
            json.loads(answer)
            json_valid = True
        except Exception:
            json_valid = False
    score = repetition_score(raw_text)
    failures = []
    if missing:
        failures.append(f"missing required markers: {missing}")
    if json_valid is False:
        failures.append("invalid json")
    if score > max_repetition_score:
        failures.append(f"repetition score too high: {score:.3f}")
    if "<think>" in raw_text and "</think>" not in raw_text:
        failures.append("unclosed visible thinking block")
    metrics = metrics or {}
    row = {
        "case": case["id"],
        "category": case["category"],
        "raw_text": raw_text,
        "final_answer": answer,
        "required": required,
        "missing": missing,
        "json_valid": json_valid,
        "visible_thinking": "<think>" in raw_text,
        "repetition_score": score,
        "max_repetition_score": max_repetition_score,
        "completion_chars": len(answer),
        "service_request_ms": metrics.get("service_request_ms"),
        "prompt_tokens": metrics.get("prompt_tokens"),
        "completion_tokens": metrics.get("completion_tokens"),
        "stop_reason": metrics.get("stop_reason"),
        "request_runtime_profile": metrics.get("request_runtime_profile"),
        "actual_prefill_tokens": metrics.get("actual_prefill_tokens"),
        "cache_hit": metrics.get("cache_hit"),
        "failures": failures,
    }
    row["quality_points"] = quality_points(row)
    return row


def capture_case(
    base_url: str,
    case: dict[str, Any],
    *,
    model: str,
    runtime_profile: str,
    temperature: float,
    top_p: float,
    seed: int | None,
    max_repetition_score: float,
) -> dict[str, Any]:
    payload = {
        "model": model,
        "prompt": case["prompt"],
        "max_tokens": case.get("max_tokens", 64),
        "stream": False,
        "stop": STOP,
        "runtime_profile": runtime_profile,
        "temperature": temperature,
        "top_p": top_p,
    }
    if seed is not None:
        payload["seed"] = seed
    response = request_json("POST", f"{base_url}/v1/completions", payload)
    raw_text = response["choices"][0]["text"]
    return build_row(
        case,
        raw_text=raw_text,
        metrics=response.get("engine_metrics") or {},
        max_repetition_score=max_repetition_score,
    )


def summarize_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    latencies = [
        float(row["service_request_ms"])
        for row in rows
        if isinstance(row.get("service_request_ms"), int | float)
    ]
    return {
        "case_count": len(rows),
        "pass_count": sum(1 for row in rows if not row.get("failures")),
        "total_quality_points": sum(int(row.get("quality_points") or 0) for row in rows),
        "max_quality_points": len(rows) * 10,
        "mean_service_request_ms": mean(latencies),
        "max_repetition_score": max((float(row.get("repetition_score") or 0) for row in rows), default=0.0),
    }


def capture(args: argparse.Namespace) -> int:
    rows = [
        capture_case(
            args.base_url.rstrip("/"),
            case,
            model=args.model,
            runtime_profile=args.runtime_profile,
            temperature=args.temperature,
            top_p=args.top_p,
            seed=args.seed,
            max_repetition_score=args.max_repetition_score,
        )
        for case in DEFAULT_CASES
    ]
    failures = [f"{row['case']}: {failure}" for row in rows for failure in row["failures"]]
    output = {
        "type": "response_quality_regression_capture",
        "tag": args.tag,
        "base_url": args.base_url.rstrip("/"),
        "model": args.model,
        "runtime_profile": args.runtime_profile,
        "deterministic_settings": {
            "temperature": args.temperature,
            "top_p": args.top_p,
            "seed": args.seed,
            "stop": STOP,
        },
        "verdict": "PASS" if not failures else "FAIL",
        "summary": summarize_rows(rows),
        "rows": rows,
        "failures": failures,
    }
    write_json(args.output_json, output)
    write_markdown(args.output_md, output)
    print("response_quality_capture", output["verdict"], "failures", len(failures), args.output_json)
    return 1 if args.fail_on_fail and failures else 0


def rows_by_case(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {row["case"]: row for row in payload.get("rows", [])}


def compare_rows(
    baseline: dict[str, Any],
    candidate: dict[str, Any],
    *,
    max_quality_point_drop: int,
    max_repetition_delta: float,
    max_length_drift_ratio: float,
) -> tuple[list[dict[str, Any]], list[str]]:
    baseline_rows = rows_by_case(baseline)
    candidate_rows = rows_by_case(candidate)
    comparisons = []
    failures = []
    for case_id, base in baseline_rows.items():
        cand = candidate_rows.get(case_id)
        if not cand:
            failures.append(f"{case_id}: candidate row missing")
            comparisons.append({"case": case_id, "verdict": "FAIL", "reason": "candidate row missing"})
            continue
        row_failures = []
        base_points = int(base.get("quality_points") or quality_points(base))
        cand_points = int(cand.get("quality_points") or quality_points(cand))
        point_drop = base_points - cand_points
        if cand.get("failures"):
            row_failures.append(f"candidate failures: {cand.get('failures')!r}")
        if point_drop > max_quality_point_drop:
            row_failures.append(f"quality point drop {point_drop} > {max_quality_point_drop}")
        base_rep = float(base.get("repetition_score") or 0.0)
        cand_rep = float(cand.get("repetition_score") or 0.0)
        rep_delta = cand_rep - base_rep
        if rep_delta > max_repetition_delta:
            row_failures.append(f"repetition delta {rep_delta:.3f} > {max_repetition_delta:.3f}")
        base_len = max(int(base.get("completion_chars") or len(base.get("final_answer") or "")), 1)
        cand_len = int(cand.get("completion_chars") or len(cand.get("final_answer") or ""))
        length_drift = abs(cand_len - base_len) / base_len
        if length_drift > max_length_drift_ratio and cand_points < base_points:
            row_failures.append(
                f"length drift {length_drift:.3f} > {max_length_drift_ratio:.3f} with quality drop"
            )
        for marker in base.get("required", []):
            if marker not in str(cand.get("final_answer", "")):
                row_failures.append(f"required marker {marker!r} missing from candidate")
        comparison = {
            "case": case_id,
            "category": base.get("category"),
            "verdict": "PASS" if not row_failures else "FAIL",
            "baseline_quality_points": base_points,
            "candidate_quality_points": cand_points,
            "quality_point_drop": point_drop,
            "baseline_repetition_score": base_rep,
            "candidate_repetition_score": cand_rep,
            "repetition_delta": round(rep_delta, 6),
            "baseline_completion_chars": base_len,
            "candidate_completion_chars": cand_len,
            "length_drift_ratio": round(length_drift, 6),
            "failures": row_failures,
        }
        comparisons.append(comparison)
        failures.extend(f"{case_id}: {failure}" for failure in row_failures)
    extra = sorted(set(candidate_rows) - set(baseline_rows))
    for case_id in extra:
        comparisons.append({"case": case_id, "verdict": "WARN", "reason": "candidate-only row"})
    return comparisons, failures


def compare(args: argparse.Namespace) -> int:
    baseline = load_json(args.baseline_json)
    candidate = load_json(args.candidate_json)
    comparisons, failures = compare_rows(
        baseline,
        candidate,
        max_quality_point_drop=args.max_quality_point_drop,
        max_repetition_delta=args.max_repetition_delta,
        max_length_drift_ratio=args.max_length_drift_ratio,
    )
    baseline_summary = summarize_rows(baseline.get("rows", []))
    candidate_summary = summarize_rows(candidate.get("rows", []))
    output = {
        "type": "response_quality_regression_comparison",
        "tag": args.tag,
        "baseline": {
            "path": str(args.baseline_json),
            "type": baseline.get("type"),
            "tag": baseline.get("tag"),
            "verdict": baseline.get("verdict"),
            "summary": baseline_summary,
        },
        "candidate": {
            "path": str(args.candidate_json),
            "type": candidate.get("type"),
            "tag": candidate.get("tag"),
            "verdict": candidate.get("verdict"),
            "summary": candidate_summary,
        },
        "thresholds": {
            "max_quality_point_drop": args.max_quality_point_drop,
            "max_repetition_delta": args.max_repetition_delta,
            "max_length_drift_ratio": args.max_length_drift_ratio,
        },
        "verdict": "PASS" if not failures else "FAIL",
        "readiness": "response-quality-regression-ready" if not failures else "response-quality-regression-blocked",
        "comparisons": comparisons,
        "failures": failures,
    }
    write_json(args.output_json, output)
    write_markdown(args.output_md, output)
    print("response_quality_comparison", output["verdict"], "failures", len(failures), args.output_json)
    return 1 if args.fail_on_fail and failures else 0


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text())


def write_json(path: Path, output: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n")


def write_markdown(path: Path | None, output: dict[str, Any]) -> None:
    if path is None:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    failures = output.get("failures") or []
    failure_lines = "\n".join(f"- `{failure}`" for failure in failures) or "- none"
    lines = [
        "# M257 Response Quality Regression Harness",
        "",
        f"Type: `{output.get('type')}`",
        f"Verdict: `{output.get('verdict')}`",
        f"Tag: `{output.get('tag')}`",
        "",
        "## Summary",
        "",
    ]
    if output.get("type") == "response_quality_regression_comparison":
        base = output["baseline"]["summary"]
        cand = output["candidate"]["summary"]
        lines.extend(
            [
                f"- baseline quality points: `{base.get('total_quality_points')}/{base.get('max_quality_points')}`",
                f"- candidate quality points: `{cand.get('total_quality_points')}/{cand.get('max_quality_points')}`",
                f"- baseline mean service ms: `{base.get('mean_service_request_ms')}`",
                f"- candidate mean service ms: `{cand.get('mean_service_request_ms')}`",
                "",
                "## Case Comparisons",
                "",
                "| Case | Verdict | Baseline | Candidate | Repetition Delta | Length Drift |",
                "| --- | --- | ---: | ---: | ---: | ---: |",
            ]
        )
        for row in output.get("comparisons", []):
            lines.append(
                f"| `{row.get('case')}` | `{row.get('verdict')}` | "
                f"{row.get('baseline_quality_points', '')} | "
                f"{row.get('candidate_quality_points', '')} | "
                f"{row.get('repetition_delta', '')} | "
                f"{row.get('length_drift_ratio', '')} |"
            )
    else:
        summary = output.get("summary") or {}
        lines.extend(
            [
                f"- cases: `{summary.get('case_count')}`",
                f"- passed cases: `{summary.get('pass_count')}`",
                f"- quality points: `{summary.get('total_quality_points')}/{summary.get('max_quality_points')}`",
                f"- mean service ms: `{summary.get('mean_service_request_ms')}`",
                f"- max repetition score: `{summary.get('max_repetition_score')}`",
            ]
        )
    lines.extend(["", "## Failures", "", failure_lines, ""])
    path.write_text("\n".join(lines))


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description=__doc__)
    sub = root.add_subparsers(dest="command", required=True)

    capture_parser = sub.add_parser("capture", help="Capture live quality rows from an engine endpoint.")
    capture_parser.add_argument("--base-url", default="http://127.0.0.1:8773")
    capture_parser.add_argument("--model", default="local-mlx")
    capture_parser.add_argument("--runtime-profile", default="interactive")
    capture_parser.add_argument("--temperature", type=float, default=0.0)
    capture_parser.add_argument("--top-p", type=float, default=1.0)
    capture_parser.add_argument("--seed", type=int)
    capture_parser.add_argument("--max-repetition-score", type=float, default=0.2)
    capture_parser.add_argument("--output-json", type=Path, required=True)
    capture_parser.add_argument("--output-md", type=Path)
    capture_parser.add_argument("--tag", default="m257-response-quality-capture")
    capture_parser.add_argument("--fail-on-fail", action="store_true")
    capture_parser.set_defaults(func=capture)

    compare_parser = sub.add_parser("compare", help="Compare candidate quality against a baseline artifact.")
    compare_parser.add_argument("--baseline-json", type=Path, required=True)
    compare_parser.add_argument("--candidate-json", type=Path, required=True)
    compare_parser.add_argument("--output-json", type=Path, required=True)
    compare_parser.add_argument("--output-md", type=Path)
    compare_parser.add_argument("--tag", default="m257-response-quality-comparison")
    compare_parser.add_argument("--max-quality-point-drop", type=int, default=0)
    compare_parser.add_argument("--max-repetition-delta", type=float, default=0.05)
    compare_parser.add_argument("--max-length-drift-ratio", type=float, default=0.5)
    compare_parser.add_argument("--fail-on-fail", action="store_true")
    compare_parser.set_defaults(func=compare)
    return root


def main() -> int:
    args = parser().parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
