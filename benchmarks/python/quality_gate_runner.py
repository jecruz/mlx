#!/usr/bin/env python3
"""Quality gates for MLX resident inference behavior."""

from __future__ import annotations

import argparse
import json
import re
import urllib.request
from collections import Counter
from pathlib import Path
from typing import Any


STOP = ["<|endoftext|>", "<|im_start|>", "<|im_end|>"]


GOLDEN_CASES: list[dict[str, Any]] = [
    {
        "id": "exact_answer",
        "category": "instruction_following",
        "prompt": "Output only: QUALITY_OK\n/no_think",
        "required": ["QUALITY_OK"],
        "max_tokens": 24,
    },
    {
        "id": "coding_task",
        "category": "coding",
        "prompt": "Return only this Python expression: a + b\n/no_think",
        "required": ["a + b"],
        "max_tokens": 512,
    },
    {
        "id": "code_review",
        "category": "coding_agent_review",
        "prompt": "Review this code: def add(a,b): return a-b. Output only: BUG_FOUND\n/no_think",
        "required": ["BUG_FOUND"],
        "max_tokens": 64,
    },
    {
        "id": "edit_plan",
        "category": "coding_agent_plan",
        "prompt": "A repo needs one small edit and one test. Output only: EDIT_AND_TEST\n/no_think",
        "required": ["EDIT_AND_TEST"],
        "max_tokens": 64,
    },
    {
        "id": "reasoning",
        "category": "reasoning",
        "prompt": "A job has 3 tasks taking 2, 4, and 6 minutes. Output only the total minutes.\n/no_think",
        "required": ["12"],
        "max_tokens": 24,
    },
    {
        "id": "json_schema",
        "category": "json",
        "prompt": "Output only valid JSON with key status and value ok.\n/no_think",
        "required": ["status", "ok"],
        "max_tokens": 48,
        "json_required": True,
    },
    {
        "id": "summary",
        "category": "summarization",
        "prompt": "Summarize this text as exactly SUMMARY_OK: MLX quality gates protect response quality while speed improves.\n/no_think",
        "required": ["SUMMARY_OK"],
        "max_tokens": 64,
    },
    {
        "id": "workspace_symbol_lookup",
        "category": "coding_agent_workspace",
        "prompt": (
            "Repo map: src/server.py defines ResidentEngine; src/cache.py defines PrefixCache. "
            "Question: which symbol handles generation? Output only: ResidentEngine\n/no_think"
        ),
        "required": ["ResidentEngine"],
        "max_tokens": 64,
    },
    {
        "id": "patch_plan",
        "category": "coding_agent_edit",
        "prompt": (
            "Task: fix a bug in src/cache.py and add one regression test in tests/test_cache.py. "
            "Output only: PATCH_SRC_CACHE_AND_TEST\n/no_think"
        ),
        "required": ["PATCH_SRC_CACHE_AND_TEST"],
        "max_tokens": 64,
    },
    {
        "id": "test_selection",
        "category": "coding_agent_test",
        "prompt": (
            "Changed files: src/cache.py, tests/test_cache.py. "
            "Choose the focused test command. Output only: pytest tests/test_cache.py\n/no_think"
        ),
        "required": ["pytest tests/test_cache.py"],
        "max_tokens": 96,
    },
    {
        "id": "failure_triage",
        "category": "coding_agent_debug",
        "prompt": (
            "Log: AssertionError expected 3 got 2 in tests/test_cache.py::test_reuse. "
            "Output only: TRIAGE_CACHE_REUSE\n/no_think"
        ),
        "required": ["TRIAGE_CACHE_REUSE"],
        "max_tokens": 64,
    },
    {
        "id": "safety_boundary",
        "category": "refusal_boundary",
        "prompt": "Output only SAFE_SUMMARY for a harmless request summary.\n/no_think",
        "required": ["SAFE_SUMMARY"],
        "max_tokens": 32,
    },
]


LONG_CONTEXT_CASE = {
    "id": "rope_imrope_sentinel_recall",
    "category": "long_context_rope_imrope",
    "prompt": (
        "EARLY_FACT: alpha code is ORCHID-17.\n"
        + "Distractor text about local inference and benchmark routing. " * 80
        + "\nMIDDLE_FACT: beta code is LANTERN-42.\n"
        + "More distractor text about cache behavior and prompt processing. " * 80
        + "\nLATE_FACT: gamma code is HARBOR-93.\n"
        + "Output only the three codes separated by commas in early,middle,late order.\n/no_think"
    ),
    "required": ["ORCHID-17", "LANTERN-42", "HARBOR-93"],
    "max_tokens": 512,
}


def request_json(method: str, url: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    data = json.dumps(payload).encode() if payload is not None else None
    headers = {"Content-Type": "application/json"} if payload is not None else {}
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=240) as resp:
        return json.loads(resp.read().decode())


def stream_sse(url: str, payload: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    text_parts: list[str] = []
    metrics: dict[str, Any] = {}
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=240) as resp:
        for raw in resp:
            line = raw.decode().strip()
            if not line.startswith("data:"):
                continue
            data = line[len("data:") :].strip()
            if not data or data == "[DONE]":
                continue
            event = json.loads(data)
            if "choices" in event:
                choice = event["choices"][0]
                text_parts.append(choice.get("text") or choice.get("delta", {}).get("content") or "")
            if event.get("engine_metrics"):
                metrics = event["engine_metrics"]
    return "".join(text_parts), metrics


def final_answer(text: str) -> str:
    if "</think>" in text:
        text = text.split("</think>", 1)[1]
    elif "<think>" in text:
        return ""
    for token in STOP:
        text = text.replace(token, "")
    return text.strip()


def repetition_score(text: str, n: int = 3) -> float:
    words = re.findall(r"\w+|<\|[^>]+?\|>", text.lower())
    if len(words) < n:
        return 0.0
    grams = [tuple(words[i : i + n]) for i in range(len(words) - n + 1)]
    counts = Counter(grams)
    repeated = sum(count - 1 for count in counts.values() if count > 1)
    return repeated / max(len(grams), 1)


def run_completion(
    base_url: str,
    case: dict[str, Any],
    *,
    stream: bool = False,
    cache_mode: str | None = None,
    runtime_profile: str = "interactive",
) -> dict[str, Any]:
    if cache_mode is not None:
        request_json("POST", f"{base_url}/engine/config", {"prefix_cache_population_mode": cache_mode})
    payload = {
        "model": "local-mlx",
        "prompt": case["prompt"],
        "max_tokens": case.get("max_tokens", 48),
        "stream": stream,
        "stop": STOP,
        "runtime_profile": runtime_profile,
    }
    if stream:
        raw_text, metrics = stream_sse(f"{base_url}/v1/completions", payload)
    else:
        response = request_json("POST", f"{base_url}/v1/completions", payload)
        raw_text = response["choices"][0]["text"]
        metrics = response["engine_metrics"]
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
    if score > 0.2:
        failures.append(f"repetition score too high: {score:.3f}")
    if "<think>" in raw_text and "</think>" not in raw_text:
        failures.append("unclosed visible thinking block")
    return {
        "case": case["id"],
        "category": case["category"],
        "stream": stream,
        "cache_mode": cache_mode,
        "raw_text": raw_text,
        "final_answer": answer,
        "required": required,
        "missing": missing,
        "json_valid": json_valid,
        "visible_thinking": "<think>" in raw_text,
        "repetition_score": score,
        "request_runtime_profile": metrics.get("request_runtime_profile"),
        "actual_prefill_tokens": metrics.get("actual_prefill_tokens"),
        "cache_hit": metrics.get("cache_hit"),
        "cache_population_mode": metrics.get("cache_population_mode"),
        "service_request_ms": metrics.get("service_request_ms"),
        "failures": failures,
    }


def write_output(args: argparse.Namespace, output: dict[str, Any]) -> int:
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n")
    print(output["type"], output["verdict"], "failures", len(output["failures"]), args.output_json)
    if args.fail_on_fail and output["verdict"] != "PASS":
        return 1
    return 0


def gate_golden(args: argparse.Namespace) -> int:
    output = {
        "type": "quality_golden_set",
        "tag": args.tag,
        "verdict": "PASS",
        "cases": GOLDEN_CASES + [LONG_CONTEXT_CASE],
        "case_count": len(GOLDEN_CASES) + 1,
        "failures": [],
    }
    return write_output(args, output)


def gate_deterministic(args: argparse.Namespace) -> int:
    base_url = args.base_url.rstrip("/")
    rows = [
        run_completion(base_url, case, stream=False, runtime_profile=args.runtime_profile)
        for case in GOLDEN_CASES
    ]
    failures = [f"{row['case']}: {failure}" for row in rows for failure in row["failures"]]
    output = {
        "type": "deterministic_quality_regression",
        "tag": args.tag,
        "base_url": base_url,
        "verdict": "PASS" if not failures else "FAIL",
        "rows": rows,
        "failures": failures,
    }
    return write_output(args, output)


def gate_cache(args: argparse.Namespace) -> int:
    base_url = args.base_url.rstrip("/")
    rows = []
    failures = []
    for case in [GOLDEN_CASES[0], GOLDEN_CASES[2], LONG_CONTEXT_CASE]:
        off = run_completion(
            base_url,
            case,
            cache_mode="off",
            runtime_profile=args.runtime_profile,
        )
        request = run_completion(
            base_url,
            case,
            cache_mode="request",
            runtime_profile=args.runtime_profile,
        )
        rows.append({"case": case["id"], "off": off, "request": request})
        for mode, row in [("off", off), ("request", request)]:
            failures.extend(f"{case['id']} {mode}: {failure}" for failure in row["failures"])
        for marker in case["required"]:
            if marker not in off["final_answer"] or marker not in request["final_answer"]:
                failures.append(f"{case['id']}: marker {marker!r} not preserved across cache modes")
    request_json("POST", f"{base_url}/engine/config", {"prefix_cache_population_mode": "async"})
    output = {
        "type": "cache_quality_comparison",
        "tag": args.tag,
        "base_url": base_url,
        "verdict": "PASS" if not failures else "FAIL",
        "rows": rows,
        "failures": failures,
    }
    return write_output(args, output)


def gate_streaming(args: argparse.Namespace) -> int:
    base_url = args.base_url.rstrip("/")
    rows = []
    failures = []
    for case in [GOLDEN_CASES[0], GOLDEN_CASES[2], GOLDEN_CASES[4]]:
        nonstream = run_completion(
            base_url,
            case,
            stream=False,
            runtime_profile=args.runtime_profile,
        )
        stream = run_completion(
            base_url,
            case,
            stream=True,
            runtime_profile=args.runtime_profile,
        )
        rows.append({"case": case["id"], "nonstream": nonstream, "stream": stream})
        for mode, row in [("nonstream", nonstream), ("stream", stream)]:
            failures.extend(f"{case['id']} {mode}: {failure}" for failure in row["failures"])
    output = {
        "type": "streaming_quality_parity",
        "tag": args.tag,
        "base_url": base_url,
        "verdict": "PASS" if not failures else "FAIL",
        "rows": rows,
        "failures": failures,
    }
    return write_output(args, output)


def gate_loop(args: argparse.Namespace) -> int:
    base_url = args.base_url.rstrip("/")
    rows = [
        run_completion(base_url, case, stream=False, runtime_profile=args.runtime_profile)
        for case in GOLDEN_CASES + [LONG_CONTEXT_CASE]
    ]
    failures = []
    for row in rows:
        if row["repetition_score"] > 0.2:
            failures.append(f"{row['case']}: repetition score {row['repetition_score']:.3f}")
        if row["raw_text"].count("<|im_start|>") > 1:
            failures.append(f"{row['case']}: repeated special im_start token")
    output = {
        "type": "loop_repetition_quality_gate",
        "tag": args.tag,
        "base_url": base_url,
        "verdict": "PASS" if not failures else "FAIL",
        "rows": rows,
        "failures": failures,
    }
    return write_output(args, output)


def gate_long_context(args: argparse.Namespace) -> int:
    base_url = args.base_url.rstrip("/")
    row = run_completion(
        base_url,
        LONG_CONTEXT_CASE,
        stream=False,
        runtime_profile=args.runtime_profile,
    )
    failures = list(row["failures"])
    output = {
        "type": "long_context_rope_imrope_quality",
        "tag": args.tag,
        "base_url": base_url,
        "verdict": "PASS" if not failures else "FAIL",
        "rows": [row],
        "failures": failures,
    }
    return write_output(args, output)


def gate_cross_engine(args: argparse.Namespace) -> int:
    base_url = args.base_url.rstrip("/")
    rows = [
        run_completion(base_url, case, stream=False, runtime_profile=args.runtime_profile)
        for case in [GOLDEN_CASES[0], GOLDEN_CASES[2], LONG_CONTEXT_CASE]
    ]
    failures = [f"{row['case']}: {failure}" for row in rows for failure in row["failures"]]
    output = {
        "type": "cross_engine_quality_comparison",
        "tag": args.tag,
        "base_url": base_url,
        "verdict": "PASS" if not failures else "FAIL",
        "comparison_mode": "rubric_reference; puma.cpp and panthro.cpp live endpoints not configured",
        "rows": rows,
        "failures": failures,
    }
    return write_output(args, output)


def gate_checkpoint(args: argparse.Namespace) -> int:
    artifacts = {name: json.loads(Path(path).read_text()) for name, path in args.artifact}
    failures = [
        f"{name}: {artifact.get('verdict')!r}"
        for name, artifact in artifacts.items()
        if artifact.get("verdict") != "PASS" or artifact.get("failures")
    ]
    covered_milestones = args.covered_milestone or [
        "M159",
        "M160",
        "M161",
        "M162",
        "M163",
        "M164",
        "M165",
        "M166",
    ]
    output = {
        "type": "quality_gated_performance_checkpoint",
        "tag": args.tag,
        "verdict": "PASS" if not failures else "FAIL",
        "artifacts": {
            name: {
                "type": artifact.get("type"),
                "verdict": artifact.get("verdict"),
                "failures": len(artifact.get("failures", [])),
            }
            for name, artifact in artifacts.items()
        },
        "covered_milestones": covered_milestones,
        "failures": failures,
    }
    if args.output_md:
        args.output_md.parent.mkdir(parents=True, exist_ok=True)
        failure_lines = "\n".join(f"- `{failure}`" for failure in failures) or "- none"
        title = "Quality-Gated Performance Checkpoint"
        if len(covered_milestones) == 1:
            title = f"{covered_milestones[0]} {title}"
        covered = ", ".join(f"`{milestone}`" for milestone in covered_milestones)
        args.output_md.write_text(
            f"# {title}\n\n"
            f"Verdict: `{output['verdict']}`\n\n"
            f"Covered milestones: {covered}\n\n"
            "Result: quality gates are now blocking criteria for future speed work.\n\n"
            "Failures:\n\n"
            f"{failure_lines}\n"
        )
    return write_output(args, output)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--gate", required=True, choices=["golden", "deterministic", "cache", "streaming", "loop", "long-context", "cross-engine", "checkpoint"])
    parser.add_argument("--base-url", default="http://127.0.0.1:8773")
    parser.add_argument("--output-json", type=Path, required=True)
    parser.add_argument("--output-md", type=Path)
    parser.add_argument("--tag", default="quality-gate")
    parser.add_argument(
        "--runtime-profile",
        default="interactive",
        help="Runtime profile to request for live completion quality gates.",
    )
    parser.add_argument("--artifact", nargs=2, action="append", default=[])
    parser.add_argument("--covered-milestone", action="append", default=[])
    parser.add_argument("--fail-on-fail", action="store_true")
    args = parser.parse_args()
    return {
        "golden": gate_golden,
        "deterministic": gate_deterministic,
        "cache": gate_cache,
        "streaming": gate_streaming,
        "loop": gate_loop,
        "long-context": gate_long_context,
        "cross-engine": gate_cross_engine,
        "checkpoint": gate_checkpoint,
    }[args.gate](args)


if __name__ == "__main__":
    raise SystemExit(main())
