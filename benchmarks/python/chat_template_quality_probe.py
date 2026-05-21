#!/usr/bin/env python3
"""Run deterministic quality cases through the chat template route."""

from __future__ import annotations

import argparse
import copy
import json
import re
import urllib.request
from collections import Counter
from pathlib import Path
from typing import Any

from quality_gate_runner import GOLDEN_CASES


STOP = ["<|endoftext|>", "<|im_start|>", "<|im_end|>"]
HARMONY_MARKERS = (
    "<|channel|>final<|message|>",
    "<|channel|>final>",
    "<|channel|>final",
)
PROMPT_ADAPTERS = ("none", "qwen25-coder-lower-memory")


def request_json(method: str, url: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    data = json.dumps(payload).encode() if payload is not None else None
    headers = {"Content-Type": "application/json"} if payload is not None else {}
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=240) as resp:
        return json.loads(resp.read().decode())


def final_answer(text: str) -> str:
    for marker in HARMONY_MARKERS:
        if marker in text:
            text = text.rsplit(marker, 1)[1]
            break
    if "</think>" in text:
        text = text.split("</think>", 1)[1]
    elif "<think>" in text:
        return ""
    for token in STOP + ["<|return|>", "<|end|>", "<|start|>", "<|message|>"]:
        text = text.replace(token, "")
    return text.strip()


def strip_json_markdown_fence(text: str) -> str:
    stripped = text.strip()
    if not stripped.startswith("```"):
        return text
    lines = stripped.splitlines()
    if len(lines) < 3 or lines[-1].strip() != "```":
        return text
    fence = lines[0].strip().lower()
    if fence not in {"```json", "```"}:
        return text
    return "\n".join(lines[1:-1]).strip()


def repetition_score(text: str, n: int = 3) -> float:
    words = re.findall(r"\w+|<\|[^>]+?\|>", text.lower())
    if len(words) < n:
        return 0.0
    grams = [tuple(words[i : i + n]) for i in range(len(words) - n + 1)]
    counts = Counter(grams)
    repeated = sum(count - 1 for count in counts.values() if count > 1)
    return repeated / max(len(grams), 1)


def run_case(
    base_url: str,
    case: dict[str, Any],
    *,
    system_prompt: str | None,
    normalize_json_fences: bool,
) -> dict[str, Any]:
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": case["prompt"]})
    response = request_json(
        "POST",
        f"{base_url}/v1/chat/completions",
        {
            "model": "local-mlx-chat-template-quality",
            "messages": messages,
            "max_tokens": case.get("max_tokens", 48),
            "runtime_profile": "interactive",
            "stop": STOP,
        },
    )
    raw_text = response["choices"][0]["message"]["content"]
    answer = final_answer(raw_text)
    if normalize_json_fences and case.get("json_required"):
        answer = strip_json_markdown_fence(answer)
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
    metrics = response.get("engine_metrics") or {}
    return {
        "case": case["id"],
        "category": case["category"],
        "raw_text": raw_text,
        "final_answer": answer,
        "required": required,
        "missing": missing,
        "json_valid": json_valid,
        "visible_thinking": "<think>" in raw_text,
        "repetition_score": score,
        "request_runtime_profile": metrics.get("request_runtime_profile"),
        "actual_prefill_tokens": metrics.get("actual_prefill_tokens"),
        "service_request_ms": metrics.get("service_request_ms"),
        "failures": failures,
    }


def adapt_case(case: dict[str, Any], *, prompt_adapter: str) -> dict[str, Any]:
    adapted = copy.deepcopy(case)
    if prompt_adapter == "none":
        return adapted
    if prompt_adapter != "qwen25-coder-lower-memory":
        raise ValueError(f"unsupported prompt adapter: {prompt_adapter}")
    if adapted.get("json_required"):
        adapted["prompt"] = (
            adapted["prompt"].rstrip()
            + "\nReturn raw JSON only. Do not wrap the JSON in markdown fences."
        )
    return adapted


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8773")
    parser.add_argument("--output-json", type=Path, required=True)
    parser.add_argument("--tag", default="chat-template-quality")
    parser.add_argument("--prompt-adapter", choices=PROMPT_ADAPTERS, default="none")
    parser.add_argument(
        "--system-prompt",
        default=(
            "You are a deterministic coding assistant. Follow the user's output "
            "format exactly. Do not call tools. Put only the requested final answer "
            "in the final response."
        ),
    )
    parser.add_argument("--fail-on-fail", action="store_true")
    args = parser.parse_args()

    cases = [
        adapt_case(case, prompt_adapter=args.prompt_adapter)
        for case in GOLDEN_CASES
    ]
    rows = [
        run_case(
            args.base_url.rstrip("/"),
            case,
            system_prompt=args.system_prompt,
            normalize_json_fences=args.prompt_adapter == "qwen25-coder-lower-memory",
        )
        for case in cases
    ]
    failures = [
        f"{row['case']}: {failure}"
        for row in rows
        for failure in row["failures"]
    ]
    output = {
        "type": "chat_template_quality_regression",
        "tag": args.tag,
        "base_url": args.base_url.rstrip("/"),
        "route": "/v1/chat/completions",
        "prompt_adapter": args.prompt_adapter,
        "system_prompt": args.system_prompt,
        "verdict": "PASS" if not failures else "FAIL",
        "rows": rows,
        "failures": failures,
    }
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n")
    print(output["type"], output["verdict"], "failures", len(failures), args.output_json)
    return 1 if args.fail_on_fail and failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
