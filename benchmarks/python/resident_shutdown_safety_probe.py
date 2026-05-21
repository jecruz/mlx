#!/usr/bin/env python3
"""Validate resident-engine shutdown joins warmup and async cache-build threads."""

from __future__ import annotations

import json
import sys
import threading
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from mlx_engine.resident_service import ResidentEngine


def make_fake_engine() -> ResidentEngine:
    engine = ResidentEngine.__new__(ResidentEngine)
    engine.shutdown_requested = threading.Event()
    engine.warmup_lock = threading.RLock()
    engine.warmup_thread = None
    engine.warmup_started_at = time.time()
    engine.warmup_completed_at = None
    engine.warmup_error = None
    engine.warmup_cancelled = False
    engine.prefix_cache_build_lock = threading.RLock()
    engine.prefix_cache_build_threads = {}
    engine.prefix_cache_pending_builds = set()
    return engine


def worker_until_shutdown(engine: ResidentEngine, *, complete_warmup: bool = False):
    def worker() -> None:
        engine.shutdown_requested.wait(timeout=5)
        if complete_warmup:
            with engine.warmup_lock:
                engine.warmup_completed_at = time.time()
                engine.warmup_cancelled = True

    return worker


def main() -> None:
    engine = make_fake_engine()

    warmup_thread = threading.Thread(
        target=worker_until_shutdown(engine, complete_warmup=True),
        name="resident-warmup-m228-probe",
    )
    async_thread = threading.Thread(
        target=worker_until_shutdown(engine),
        name="prefix-cache-build-m228-probe",
    )

    warmup_thread.start()
    async_thread.start()

    engine.warmup_thread = warmup_thread
    with engine.prefix_cache_build_lock:
        engine.prefix_cache_pending_builds.add("m228")
        engine.prefix_cache_build_threads["m228"] = async_thread

    result = engine.shutdown(timeout_ms=1000)
    verdict = (
        result["shutdown_requested"]
        and result["warmup_alive_before"]
        and result["warmup_joined"]
        and not result["warmup_alive_after"]
        and result["async_threads_before"] == 1
        and result["async_threads_joined"] == 1
        and result["async_threads_alive_after"] == 0
    )

    payload = {
        "type": "resident_shutdown_safety_probe",
        "verdict": "PASS" if verdict else "FAIL",
        "result": result,
    }
    print(json.dumps(payload, indent=2, sort_keys=True))
    if not verdict:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
