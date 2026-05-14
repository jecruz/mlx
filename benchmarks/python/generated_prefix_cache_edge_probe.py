#!/usr/bin/env python3
"""Edge probes for generated-prefix cache correctness.

These checks cover two safety-sensitive boundaries:

- max-token/EOS completions can record generated-prefix caches when the returned
  text retokenizes to exactly the prompt tokens plus generated token IDs.
- stop-string-trimmed completions must not record generated-prefix caches when
  trimming makes returned text diverge from the generated token IDs.
"""

from __future__ import annotations

import argparse
import json
import uuid
import urllib.request
from typing import Any


def request_json(method: str, url: str, payload: dict[str, Any] | None = None):
    data = None
    headers = {}
    if payload is not None:
        data = json.dumps(payload).encode()
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    with urllib.request.urlopen(req, timeout=240) as resp:
        return json.loads(resp.read().decode())


def completion(
    *,
    base_url: str,
    prompt: str,
    max_tokens: int,
    stop: str | list[str] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "model": "local-mlx",
        "prompt": prompt,
        "max_tokens": max_tokens,
        "policy": "auto",
    }
    if stop is not None:
        payload["stop"] = stop
    return request_json("POST", f"{base_url}/v1/completions", payload)


def stream_completion(
    *,
    base_url: str,
    prompt: str,
    max_tokens: int,
    stop: str | list[str] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "model": "local-mlx",
        "prompt": prompt,
        "max_tokens": max_tokens,
        "policy": "auto",
        "stream": True,
    }
    if stop is not None:
        payload["stop"] = stop

    req = urllib.request.Request(
        f"{base_url}/v1/completions",
        data=json.dumps(payload).encode(),
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    final: dict[str, Any] | None = None
    with urllib.request.urlopen(req, timeout=240) as resp:
        for raw_line in resp:
            line = raw_line.decode().strip()
            if not line.startswith("data: "):
                continue
            data = line.removeprefix("data: ")
            if data == "[DONE]":
                break
            chunk = json.loads(data)
            if "engine_metrics" in chunk:
                final = chunk
    if final is None:
        raise AssertionError("stream did not return final engine metrics")
    return final


def prune_cache(base_url: str) -> None:
    request_json(
        "POST",
        f"{base_url}/engine/cache/prune",
        {"target_entries": 0, "clear_mlx_cache": False},
    )


def configure_sync_safe(base_url: str) -> None:
    request_json(
        "POST",
        f"{base_url}/engine/config",
        {"engine_preset": "sync-safe", "prefix_cache_population_mode": "sync"},
    )


def assert_max_token_cache_path(base_url: str) -> None:
    probe_id = uuid.uuid4().hex
    prompt = (
        f"Generated-prefix max-token edge probe {probe_id}. "
        "Continue this engineering note with one compact phrase: "
    )
    first = completion(base_url=base_url, prompt=prompt, max_tokens=1)
    text = first["choices"][0]["text"]
    metrics = first["engine_metrics"]
    print(
        "edge_max_token",
        bool(text),
        metrics.get("stop_reason"),
        metrics.get("generated_token_count_recorded"),
        metrics.get("generated_prefix_cache_recorded"),
        metrics.get("generated_prefix_cache_reason"),
        metrics.get("generated_prefix_token_boundary_safe"),
    )
    if not text:
        raise AssertionError("max-token edge probe generated empty text")
    if int(metrics.get("generated_token_count_recorded") or 0) <= 0:
        raise AssertionError("max-token edge probe recorded no generated token IDs")
    if not metrics.get("generated_prefix_token_boundary_safe"):
        raise AssertionError("max-token edge probe unexpectedly failed boundary guard")
    if not metrics.get("generated_prefix_cache_recorded"):
        raise AssertionError("max-token edge probe did not record generated prefix")

    second = completion(
        base_url=base_url,
        prompt=prompt + text + " Add one metric.",
        max_tokens=2,
    )
    second_metrics = second["engine_metrics"]
    print(
        "edge_max_token_followup",
        second_metrics.get("cache_reuse_enabled"),
        second_metrics.get("cache_hit"),
        second_metrics.get("actual_prefill_tokens"),
        second_metrics.get("prompt_tokens"),
    )
    if not second_metrics.get("cache_reuse_enabled"):
        raise AssertionError("max-token follow-up did not reuse generated prefix")
    if not second_metrics.get("cache_hit"):
        raise AssertionError("max-token follow-up did not hit generated prefix cache")


def assert_stop_trim_cache_guard(base_url: str) -> None:
    probe_id = uuid.uuid4().hex
    prompt = (
        f"Generated-prefix stop-trim edge probe {probe_id}. "
        "Write one short sentence about resident MLX inference."
    )
    first = completion(base_url=base_url, prompt=prompt, max_tokens=32, stop="e")
    text = first["choices"][0]["text"]
    metrics = first["engine_metrics"]
    print(
        "edge_stop_trim",
        repr(text[:40]),
        metrics.get("stop_reason"),
        metrics.get("generated_token_count_recorded"),
        metrics.get("generated_prefix_cache_recorded"),
        metrics.get("generated_prefix_cache_reason"),
        metrics.get("generated_prefix_token_boundary_safe"),
        metrics.get("generated_prefix_retokenized_tokens"),
        metrics.get("generated_prefix_combined_tokens"),
    )
    if "e" in text:
        raise AssertionError("stop-trim edge probe leaked the stop string")
    if metrics.get("stop_reason") != "stop":
        raise AssertionError(f"stop-trim edge probe did not stop: {metrics}")
    if metrics.get("generated_prefix_cache_recorded"):
        raise AssertionError("stop-trim edge probe incorrectly recorded generated prefix")
    if metrics.get("generated_prefix_cache_reason") != "token_boundary_mismatch":
        raise AssertionError(
            "stop-trim edge probe did not report token boundary mismatch"
        )
    if metrics.get("generated_prefix_token_boundary_safe") is not False:
        raise AssertionError("stop-trim edge probe did not mark boundary unsafe")


def assert_stream_stop_trim_cache_guard(base_url: str) -> None:
    probe_id = uuid.uuid4().hex
    prompt = (
        f"Generated-prefix stream stop-trim edge probe {probe_id}. "
        "Write one short sentence about local inference scheduling."
    )
    final = stream_completion(base_url=base_url, prompt=prompt, max_tokens=32, stop="e")
    metrics = final["engine_metrics"]
    print(
        "edge_stream_stop_trim",
        metrics.get("stop_reason"),
        metrics.get("generated_token_count_recorded"),
        metrics.get("generated_prefix_cache_recorded"),
        metrics.get("generated_prefix_cache_reason"),
        metrics.get("generated_prefix_token_boundary_safe"),
    )
    if metrics.get("stop_reason") != "stop":
        raise AssertionError(f"stream stop-trim edge probe did not stop: {metrics}")
    if metrics.get("generated_prefix_cache_recorded"):
        raise AssertionError("stream stop-trim incorrectly recorded generated prefix")
    if metrics.get("generated_prefix_cache_reason") != "token_boundary_mismatch":
        raise AssertionError("stream stop-trim did not report boundary mismatch")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8765")
    args = parser.parse_args()
    base_url = args.base_url.rstrip("/")

    health = request_json("GET", f"{base_url}/health")
    print("health", health["ok"], health["device"]["default_device"])
    configure_sync_safe(base_url)
    prune_cache(base_url)
    assert_max_token_cache_path(base_url)
    prune_cache(base_url)
    assert_stop_trim_cache_guard(base_url)
    prune_cache(base_url)
    assert_stream_stop_trim_cache_guard(base_url)
    print("generated_prefix_cache_edge_result PASS")


if __name__ == "__main__":
    main()
