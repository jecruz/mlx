#!/usr/bin/env python3
"""Static audit for request-profile scope lock discipline."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--service", type=Path, default=Path("mlx_engine/resident_service.py"))
    parser.add_argument("--output-json", type=Path, required=True)
    parser.add_argument("--tag", default="m152-qwen-a3b")
    parser.add_argument("--fail-on-fail", action="store_true")
    args = parser.parse_args()
    text = args.service.read_text()

    checks = [
        (
            "runtime_config_lock_initialized",
            "self.runtime_config_lock = threading.RLock()" in text,
        ),
        (
            "configure_runtime_locked",
            "def configure_runtime" in text
            and "with self.runtime_config_lock:" in text.split("def configure_runtime", 1)[1].split("def prune_prefix_cache", 1)[0],
        ),
        (
            "snapshot_locked",
            "def runtime_config_snapshot" in text
            and "with self.runtime_config_lock:" in text.split("def runtime_config_snapshot", 1)[1].split("def restore_runtime_config", 1)[0],
        ),
        (
            "restore_locked",
            "def restore_runtime_config" in text
            and "with self.runtime_config_lock:" in text.split("def restore_runtime_config", 1)[1].split("@contextmanager", 1)[0],
        ),
        (
            "request_scope_holds_lock",
            "def request_runtime_profile_scope" in text
            and "with self.runtime_config_lock:" in text.split("def request_runtime_profile_scope", 1)[1].split("def apply_request_runtime_profile", 1)[0],
        ),
        (
            "stream_generate_scoped",
            "def stream_generate_jsonl" in text
            and "with self.request_runtime_profile_scope(request)" in text.split("def stream_generate_jsonl", 1)[1].split("def render_chat_prompt", 1)[0],
        ),
        (
            "stream_completion_scoped",
            "def stream_openai_completion" in text
            and "with self.request_runtime_profile_scope(request)" in text.split("def stream_openai_completion", 1)[1].split("def openai_chat_completion", 1)[0],
        ),
        (
            "stream_chat_scoped",
            "def stream_openai_chat_completion" in text
            and "with self.request_runtime_profile_scope(request)" in text.split("def stream_openai_chat_completion", 1)[1],
        ),
    ]
    failures = [name for name, ok in checks if not ok]
    output = {
        "type": "runtime_profile_scope_audit",
        "tag": args.tag,
        "service": str(args.service),
        "verdict": "PASS" if not failures else "FAIL",
        "readiness": "runtime-profile-scope-locked" if not failures else "not-ready",
        "checks": [{"name": name, "pass": ok} for name, ok in checks],
        "failures": failures,
    }
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n")
    print("runtime_profile_scope_audit", output["verdict"], "checks", len(checks), "failures", len(failures), args.output_json)
    if args.fail_on_fail and output["verdict"] != "PASS":
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
