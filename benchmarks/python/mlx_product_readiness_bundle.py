#!/usr/bin/env python3
"""Package MLX/Dax product-readiness evidence into one release artifact."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


DEFAULT_EVIDENCE = {
    "m97_first_hit_direct": Path(
        "artifacts/m97-direct-first-hit-profile/dax-product-first-hit-summary-m97-qwen-a3b-first-hit-direct.json"
    ),
    "m98_low_memory_direct": Path(
        "artifacts/m98-direct-low-memory-profile/dax-product-first-hit-summary-m98-qwen-a3b-low-memory-direct.json"
    ),
    "m100_wall_time": Path(
        "artifacts/m100-operator-wall-time/dax-operator-wall-time-m100-qwen-a3b.json"
    ),
    "m101_default_profile_gate": Path(
        "artifacts/m101-default-profile-decision-gate/default-profile-decision-gate-m101-qwen-a3b.json"
    ),
    "m103_overhead_target": Path(
        "artifacts/m103-operator-overhead-reduction/operator-overhead-reduction-m103-qwen-a3b.json"
    ),
    "m104_prompt_processing": Path(
        "artifacts/m104-prompt-processing-extension/prompt-processing-extension-m104-qwen-a3b.json"
    ),
    "m105_fast_invocation": Path(
        "artifacts/m105-fast-dax-invocation/fast-dax-invocation-m105-qwen-a3b.json"
    ),
    "m106_auto_selection": Path(
        "artifacts/m106-profile-auto-selection/profile-auto-selection-m106-qwen-a3b.json"
    ),
    "m107_lower_memory_strategy": Path(
        "artifacts/m107-lower-memory-mac-strategy/lower-memory-mac-strategy-m107-qwen-a3b.json"
    ),
}


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text())


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-json", type=Path, required=True)
    parser.add_argument("--tag", default="m108-qwen-a3b")
    parser.add_argument("--fail-on-fail", action="store_true")
    args = parser.parse_args()

    entries: dict[str, dict[str, Any]] = {}
    failures: list[str] = []
    for name, path in DEFAULT_EVIDENCE.items():
        if not path.exists():
            failures.append(f"{name}: missing {path}")
            continue
        payload = load_json(path)
        verdict = payload.get("verdict")
        if verdict != "PASS":
            failures.append(f"{name}: verdict={verdict!r}")
        entries[name] = {
            "path": str(path),
            "type": payload.get("type"),
            "verdict": verdict,
            "summary": {
                key: payload.get(key)
                for key in ("tag", "case_count", "row_count")
                if key in payload
            },
        }

    required_docs = [
        Path("docs/mac-local-inference-platform/progress.md"),
        Path("docs/mac-local-inference-platform/next-performance-target.md"),
        Path("docs/mac-local-inference-platform/engine-readiness.md"),
    ]
    for doc in required_docs:
        if not doc.exists():
            failures.append(f"missing doc {doc}")

    output = {
        "type": "mlx_product_readiness_bundle",
        "tag": args.tag,
        "verdict": "PASS" if not failures else "FAIL",
        "readiness": "ready-for-next-implementation-lane" if not failures else "not-ready",
        "failures": failures,
        "evidence": entries,
        "commits": {
            "m99_dax_routing": "167cac48",
            "m102_dax_controls": "08c14b5d",
        },
        "profile_decision": {
            "default_coding_agent": "agent-workspace-async",
            "immediate_second_turn": "agent-workspace-first-hit",
            "lower_memory_mac": "agent-workspace-low-memory",
            "interactive": "interactive",
            "diagnostics": "diagnostics",
        },
        "next_implementation_lane": [
            "Implement resident-dax-client fast invocation path.",
            "Add overhead_ms gate to product benchmark rows.",
            "Run extended prompt sweep across 512/1024/2048/4096 tokens.",
            "Add lower-memory peak-memory and cache-limit gates.",
            "Use auto-selection policy in the product control surface.",
        ],
        "known_open_risks": [
            "Qwen recurrent-state continuation still requires model-specific handling for generic replay-free prefix storage.",
            "Dax/operator overhead remains above target until the resident client path is implemented.",
            "Lower-memory 16-24GB Mac lane is planned but not live-bench validated on that hardware class.",
        ],
        "docs": [str(path) for path in required_docs],
    }
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n")
    print(
        "mlx_product_readiness_bundle",
        output["verdict"],
        output["readiness"],
        "evidence",
        len(entries),
        "failures",
        len(failures),
        args.output_json,
        flush=True,
    )
    for failure in failures:
        print("failure", failure, flush=True)
    return 1 if args.fail_on_fail and failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
