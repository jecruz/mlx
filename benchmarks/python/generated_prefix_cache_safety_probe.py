#!/usr/bin/env python3
"""Safety probes for generated-token prefix cache recording."""

from __future__ import annotations

import argparse
import json
import threading
import urllib.request
import uuid
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
    prefill_step_size: int | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "model": "local-mlx",
        "prompt": prompt,
        "max_tokens": max_tokens,
        "policy": "auto",
    }
    if prefill_step_size is not None:
        payload["prefill_step_size"] = prefill_step_size
    return request_json("POST", f"{base_url}/v1/completions", payload)


def stream_generate(
    *,
    base_url: str,
    prompt: str,
    max_tokens: int,
    prefill_step_size: int | None = None,
) -> list[dict[str, Any]]:
    payload: dict[str, Any] = {
        "prompt": prompt,
        "max_tokens": max_tokens,
        "policy": "auto",
        "stream": True,
    }
    if prefill_step_size is not None:
        payload["prefill_step_size"] = prefill_step_size
    req = urllib.request.Request(
        f"{base_url}/generate",
        data=json.dumps(payload).encode(),
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    events = []
    with urllib.request.urlopen(req, timeout=240) as resp:
        for raw_line in resp:
            line = raw_line.decode().strip()
            if not line:
                continue
            event = json.loads(line)
            events.append(event)
            if event["type"] in {"final", "cancelled", "error"}:
                break
    return events


def cache_entries(base_url: str) -> int:
    health = request_json("GET", f"{base_url}/health")
    return int(health["prefix_kv_cache"]["entries"])


def assert_followup_hit(
    *,
    label: str,
    first_prompt: str,
    generated_text: str,
    first_metrics: dict[str, Any],
    second_metrics: dict[str, Any],
) -> None:
    print(
        label,
        first_metrics.get("prompt_tokens"),
        first_metrics.get("generation_tokens"),
        first_metrics.get("generated_token_count_recorded"),
        first_metrics.get("generated_prefix_cache_recorded"),
        first_metrics.get("generated_prefix_cache_tokens"),
        second_metrics.get("prompt_tokens"),
        second_metrics.get("longest_prefix_match_tokens"),
        second_metrics.get("cache_reuse_enabled"),
        second_metrics.get("cache_hit"),
        second_metrics.get("actual_prefill_tokens"),
    )
    if not generated_text:
        raise AssertionError(f"{label}: first response did not produce text")
    if not first_metrics.get("generated_prefix_cache_recorded"):
        raise AssertionError(f"{label}: generated prefix cache was not recorded")
    if int(first_metrics.get("generated_token_count_recorded") or 0) <= 0:
        raise AssertionError(f"{label}: generated token ids were not recorded")
    if not second_metrics.get("cache_reuse_enabled"):
        raise AssertionError(f"{label}: follow-up did not reuse prefix cache")
    if not second_metrics.get("cache_hit"):
        raise AssertionError(f"{label}: follow-up did not hit prefix cache")
    if int(second_metrics.get("actual_prefill_tokens") or 0) >= int(
        second_metrics.get("prompt_tokens") or 0
    ):
        raise AssertionError(f"{label}: follow-up did not reduce actual prefill")
    if int(second_metrics.get("longest_prefix_match_tokens") or 0) < int(
        first_metrics.get("generated_prefix_cache_tokens") or 0
    ):
        raise AssertionError(f"{label}: follow-up did not match generated prefix")


def cancel_during_prefill(base_url: str, *, repeats: int, prefill_step_size: int) -> None:
    request_json(
        "POST",
        f"{base_url}/engine/cache/prune",
        {"target_entries": 0, "clear_mlx_cache": False},
    )
    before_entries = cache_entries(base_url)
    probe_id = uuid.uuid4().hex
    prompt = "\n".join(
        [
            f"Generated cache cancellation safety probe {probe_id}.",
            *(
                f"Segment {index}: make prefill long enough to cancel before decode."
                for index in range(repeats)
            ),
        ]
    )
    payload = {
        "prompt": prompt,
        "max_tokens": 32,
        "policy": "auto",
        "prefill_step_size": prefill_step_size,
        "stream": True,
    }

    cancel_response: dict[str, Any] | None = None
    cancel_error: Exception | None = None

    def cancel(request_id: str) -> None:
        nonlocal cancel_response, cancel_error
        try:
            cancel_response = request_json(
                "POST",
                f"{base_url}/engine/requests/{request_id}/cancel",
            )
        except Exception as exc:  # pragma: no cover - diagnostic path
            cancel_error = exc

    req = urllib.request.Request(
        f"{base_url}/generate",
        data=json.dumps(payload).encode(),
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    events: list[dict[str, Any]] = []
    cancel_thread: threading.Thread | None = None
    with urllib.request.urlopen(req, timeout=240) as resp:
        for raw_line in resp:
            line = raw_line.decode().strip()
            if not line:
                continue
            event = json.loads(line)
            events.append(event)
            if event["type"] == "prompt_progress" and cancel_thread is None:
                cancel_thread = threading.Thread(
                    target=cancel,
                    args=(event["request_id"],),
                    daemon=True,
                )
                cancel_thread.start()
            if event["type"] in {"final", "cancelled", "error"}:
                break
    if cancel_thread is not None:
        cancel_thread.join(timeout=10)
    if cancel_error is not None:
        raise AssertionError(f"cancel request failed: {cancel_error}")
    if cancel_response is None or not cancel_response.get("ok"):
        raise AssertionError(f"cancel response was not ok: {cancel_response}")
    if not events or events[-1]["type"] != "cancelled":
        raise AssertionError(f"expected cancelled event, got: {events[-3:]}")
    after_entries = cache_entries(base_url)
    token_events = [event for event in events if event["type"] == "token"]
    print(
        "generated_cache_cancel_safety",
        before_entries,
        after_entries,
        len([event for event in events if event["type"] == "prompt_progress"]),
        len(token_events),
        events[-1].get("prompt_progress_events"),
    )
    if token_events:
        raise AssertionError("cancel safety probe emitted token events before cancel")
    if after_entries != before_entries:
        raise AssertionError("cancelled request changed prefix cache entries")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8765")
    parser.add_argument("--long-max-tokens", type=int, default=32)
    parser.add_argument("--stream-max-tokens", type=int, default=12)
    parser.add_argument("--cancel-repeats", type=int, default=96)
    parser.add_argument("--prefill-step-size", type=int, default=16)
    args = parser.parse_args()
    base_url = args.base_url.rstrip("/")

    health = request_json("GET", f"{base_url}/health")
    print(
        "health",
        health["ok"],
        health["device"]["default_device"],
        health.get("engine_preset"),
    )
    request_json(
        "POST",
        f"{base_url}/engine/config",
        {"engine_preset": "sync-safe", "prefix_cache_population_mode": "sync"},
    )

    request_json(
        "POST",
        f"{base_url}/engine/cache/prune",
        {"target_entries": 0, "clear_mlx_cache": False},
    )
    long_id = uuid.uuid4().hex
    long_prompt = (
        f"Generated cache long continuation probe {long_id}. "
        "Describe resident MLX inference with concrete engineering metrics: "
    )
    long_first = completion(
        base_url=base_url,
        prompt=long_prompt,
        max_tokens=args.long_max_tokens,
    )
    long_text = long_first["choices"][0]["text"]
    long_second = completion(
        base_url=base_url,
        prompt=long_prompt + long_text + " Continue with one operational caveat.",
        max_tokens=4,
    )
    assert_followup_hit(
        label="generated_cache_long_safety",
        first_prompt=long_prompt,
        generated_text=long_text,
        first_metrics=long_first["engine_metrics"],
        second_metrics=long_second["engine_metrics"],
    )

    request_json(
        "POST",
        f"{base_url}/engine/cache/prune",
        {"target_entries": 0, "clear_mlx_cache": False},
    )
    stream_id = uuid.uuid4().hex
    stream_prompt = (
        f"Generated cache stream probe {stream_id}. "
        "Write a compact continuation for a streaming local inference client: "
    )
    stream_events = stream_generate(
        base_url=base_url,
        prompt=stream_prompt,
        max_tokens=args.stream_max_tokens,
    )
    stream_final = stream_events[-1]
    if stream_final["type"] != "final":
        raise AssertionError(f"stream did not finish: {stream_final}")
    stream_text = stream_final["text"]
    stream_second = completion(
        base_url=base_url,
        prompt=stream_prompt + stream_text + " Add one reuse metric.",
        max_tokens=4,
    )
    assert_followup_hit(
        label="generated_cache_stream_safety",
        first_prompt=stream_prompt,
        generated_text=stream_text,
        first_metrics=stream_final,
        second_metrics=stream_second["engine_metrics"],
    )

    cancel_during_prefill(
        base_url,
        repeats=args.cancel_repeats,
        prefill_step_size=args.prefill_step_size,
    )
    request_json(
        "POST",
        f"{base_url}/engine/config",
        {"engine_preset": "sync-safe", "prefix_cache_population_mode": "sync"},
    )
    print("generated_prefix_cache_safety_result PASS")


if __name__ == "__main__":
    main()
