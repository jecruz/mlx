#!/usr/bin/env python3
"""Probe tokenized prompt reuse cache semantics."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from mlx_engine.prefix_cache import TokenizedPromptCache


def build_report(*, performance_report: Path, m202_report: Path, tag: str) -> dict[str, Any]:
    cache = TokenizedPromptCache(max_entries=2)
    prompt = "shared repeated workspace prompt"
    scope_a = {
        "model": "model-a",
        "backend": "text",
        "tokenizer_class": "TokenizerA",
        "chat_template_hash": "template-a",
    }
    scope_b = {
        **scope_a,
        "chat_template_hash": "template-b",
    }
    key_a = cache.key_for_prompt(prompt, scope=scope_a)
    key_b = cache.key_for_prompt(prompt, scope=scope_b)

    miss = cache.get(key_a)
    cache.put(key=key_a, prompt_hash="prompt-a", scope=scope_a, tokens=[1, 2, 3, 4])
    first_hit = cache.get(key_a)
    first_hit_before_mutation = list(first_hit) if first_hit is not None else None
    if first_hit is not None:
        first_hit.append(999)
    second_hit = cache.get(key_a)
    scope_bleed = cache.get(key_b)
    cache.put(key=key_b, prompt_hash="prompt-a", scope=scope_b, tokens=[5, 6])
    cache.put(
        key=cache.key_for_prompt("third prompt", scope=scope_a),
        prompt_hash="prompt-c",
        scope=scope_a,
        tokens=[7, 8],
    )
    evicted = cache.get(key_a)
    snapshot = cache.snapshot()

    failures: list[str] = []
    if miss is not None:
        failures.append("cold lookup unexpectedly hit")
    if first_hit_before_mutation != [1, 2, 3, 4]:
        failures.append(
            f"first hit returned unexpected tokens: {first_hit_before_mutation}"
        )
    if second_hit != [1, 2, 3, 4]:
        failures.append("cached token list was mutated by caller")
    if scope_bleed is not None:
        failures.append("cache reused tokens across tokenizer scope")
    if evicted is not None:
        failures.append("old prompt remained after LRU eviction")
    if snapshot["entries"] != 2:
        failures.append(f"unexpected cache size after eviction: {snapshot['entries']}")

    performance = json.loads(performance_report.read_text())
    m202 = json.loads(m202_report.read_text())
    return {
        "type": "tokenized_prompt_reuse_probe",
        "tag": tag,
        "verdict": "PASS" if not failures else "FAIL",
        "readiness": "tokenized-prompt-reuse-ready" if not failures else "not-ready",
        "failures": failures,
        "acceptance": {
            "cold_lookup_misses": miss is None,
            "identical_prompt_hits": first_hit_before_mutation == [1, 2, 3, 4],
            "returned_tokens_are_copied": second_hit == [1, 2, 3, 4],
            "scope_separation_prevents_route_bleed": scope_bleed is None,
            "lru_eviction_bounds_cache": evicted is None and snapshot["entries"] == 2,
        },
        "cache_snapshot": snapshot,
        "performance_baseline": performance.get("current"),
        "performance_target": performance.get("target"),
        "m202_dependency": {
            "artifact": str(m202_report),
            "verdict": m202.get("verdict"),
            "readiness": m202.get("readiness"),
        },
        "expected_latency_effect": (
            "Identical repeated workspace prompts can reuse tokenized prompt IDs "
            "before prefix analysis, avoiding repeated tokenizer.encode work while "
            "keeping tokenizer/model/template scope in the cache key."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--performance-report",
        type=Path,
        default=Path(
            "artifacts/m194-performance-report/"
            "prompt-processing-performance-report-m194-qwen-a3b.json"
        ),
    )
    parser.add_argument(
        "--m202-report",
        type=Path,
        default=Path(
            "artifacts/m202-cache-lookup-fast-path/"
            "cache-lookup-fast-path-m202-qwen-a3b.json"
        ),
    )
    parser.add_argument(
        "--output-json",
        type=Path,
        default=Path(
            "artifacts/m203-tokenized-prompt-reuse/"
            "tokenized-prompt-reuse-m203-qwen-a3b.json"
        ),
    )
    parser.add_argument("--tag", default="m203-qwen-a3b")
    parser.add_argument("--fail-on-fail", action="store_true")
    args = parser.parse_args()

    report = build_report(
        performance_report=args.performance_report,
        m202_report=args.m202_report,
        tag=args.tag,
    )
    print(
        "tokenized_prompt_reuse",
        report["verdict"],
        "identical_hit",
        report["acceptance"]["identical_prompt_hits"],
        "scope_separation",
        report["acceptance"]["scope_separation_prevents_route_bleed"],
        "copy_safe",
        report["acceptance"]["returned_tokens_are_copied"],
    )
    for failure in report["failures"]:
        print("tokenized_prompt_reuse_failure", failure)
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    return 1 if args.fail_on_fail and report["verdict"] != "PASS" else 0


if __name__ == "__main__":
    raise SystemExit(main())
