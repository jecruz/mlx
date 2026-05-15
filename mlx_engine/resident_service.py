# Copyright © 2023-2024 Apple Inc.

import argparse
import copy
import gc
import hashlib
import json
import os
import queue
import sys
import threading
import time
import uuid
from collections import deque
from pathlib import Path
from typing import Any, Literal

import mlx.core as mx
import uvicorn
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from starlette.responses import StreamingResponse

ROOT = Path(__file__).resolve().parents[1]
BENCHMARKS_PYTHON = ROOT / "benchmarks" / "python"
if str(BENCHMARKS_PYTHON) not in sys.path:
    sys.path.insert(0, str(BENCHMARKS_PYTHON))

from inprocess_prompt_sweep import build_token_prompt, detect_backend, runtime_device_info


MODULE_IMPORTED_AT_EPOCH = time.time()

PolicyName = Literal["auto", "throughput_default", "balanced", "memory_saver"]
EnginePresetName = Literal[
    "custom",
    "sync-safe",
    "async-experimental",
    "memory-saver",
]
WarmupMode = Literal["sync", "async", "off"]
PrefixCachePopulationMode = Literal["sync", "async", "request", "off"]
StopValue = str | list[str]


def engine_preset_defaults(name: EnginePresetName) -> dict[str, Any]:
    presets = {
        "sync-safe": {
            "max_concurrent_requests": 1,
            "max_queued_requests": 16,
            "queue_timeout_ms": 30000,
            "prefix_cache_max_entries": 16,
            "prefix_cache_memory_limit_mb": 0.0,
            "prefix_cache_min_entries": 0,
            "prefix_cache_population_mode": "sync",
            "prefix_cache_async_idle_timeout_ms": 30000,
            "prefix_cache_async_idle_grace_ms": 0,
        },
        "async-experimental": {
            "max_concurrent_requests": 1,
            "max_queued_requests": 16,
            "queue_timeout_ms": 30000,
            "prefix_cache_max_entries": 16,
            "prefix_cache_memory_limit_mb": 0.0,
            "prefix_cache_min_entries": 0,
            "prefix_cache_population_mode": "async",
            "prefix_cache_async_idle_timeout_ms": 30000,
            "prefix_cache_async_idle_grace_ms": 50,
        },
        "memory-saver": {
            "max_concurrent_requests": 1,
            "max_queued_requests": 8,
            "queue_timeout_ms": 30000,
            "prefix_cache_max_entries": 4,
            "prefix_cache_memory_limit_mb": 64.0,
            "prefix_cache_min_entries": 1,
            "prefix_cache_population_mode": "sync",
            "prefix_cache_async_idle_timeout_ms": 30000,
            "prefix_cache_async_idle_grace_ms": 0,
        },
        "custom": {
            "max_concurrent_requests": 1,
            "max_queued_requests": 16,
            "queue_timeout_ms": 30000,
            "prefix_cache_max_entries": 16,
            "prefix_cache_memory_limit_mb": 0.0,
            "prefix_cache_min_entries": 0,
            "prefix_cache_population_mode": "sync",
            "prefix_cache_async_idle_timeout_ms": 30000,
            "prefix_cache_async_idle_grace_ms": 0,
        },
    }
    return dict(presets[name])


def normalize_stop(stop: StopValue | None) -> list[str]:
    if stop is None:
        return []
    if isinstance(stop, str):
        return [stop] if stop else []
    return [item for item in stop if item]


def trim_at_stop(text: str, stop: list[str]) -> tuple[str, bool]:
    if not text or not stop:
        return text, False
    matches = [text.find(item) for item in stop if item and item in text]
    if not matches:
        return text, False
    return text[: min(matches)], True


class Message(BaseModel):
    role: str
    content: str


class GenerateRequest(BaseModel):
    prompt: str
    max_tokens: int = Field(default=64, ge=1)
    policy: PolicyName = "auto"
    prefill_step_size: int | None = None
    stream: bool = False
    stop: StopValue | None = None


class CompletionRequest(BaseModel):
    model: str | None = None
    prompt: str
    max_tokens: int = Field(default=64, ge=1)
    policy: PolicyName = "auto"
    prefill_step_size: int | None = None
    stream: bool = False
    stop: StopValue | None = None


class ChatCompletionRequest(BaseModel):
    model: str | None = None
    messages: list[Message]
    max_tokens: int = Field(default=64, ge=1)
    policy: PolicyName = "auto"
    prefill_step_size: int | None = None
    stream: bool = False
    stop: StopValue | None = None


class ReloadRequest(BaseModel):
    model: str | None = None
    profile: str | None = None
    warmup_prompt_tokens: str | None = None
    warmup_profile_prefill: bool | None = None
    warmup_mode: WarmupMode | None = None


class EngineConfigRequest(BaseModel):
    dry_run: bool = False
    engine_preset: EnginePresetName | None = None
    max_concurrent_requests: int | None = Field(default=None, ge=1)
    max_queued_requests: int | None = Field(default=None, ge=0)
    queue_timeout_ms: int | None = Field(default=None, ge=1)
    prefix_cache_max_entries: int | None = Field(default=None, ge=0)
    prefix_cache_memory_limit_mb: float | None = Field(default=None, ge=0)
    prefix_cache_min_entries: int | None = Field(default=None, ge=0)
    prefix_cache_population_mode: PrefixCachePopulationMode | None = None
    prefix_cache_async_idle_timeout_ms: int | None = Field(default=None, ge=1)
    prefix_cache_async_idle_grace_ms: int | None = Field(default=None, ge=0)


class CachePruneRequest(BaseModel):
    target_entries: int = Field(default=0, ge=0)
    clear_mlx_cache: bool = True


class LockPriorityProbeRequest(BaseModel):
    timeout_ms: int = Field(default=5000, ge=100)


class RequestCancelled(RuntimeError):
    pass


class EngineMetrics:
    def __init__(self):
        self.started_at = time.time()
        self.total_requests = 0
        self.failed_requests = 0
        self.total_prompt_tokens = 0
        self.total_generation_tokens = 0
        self.total_run_ms = 0.0
        self.total_prefix_match_tokens = 0
        self.cache_candidate_requests = 0
        self.recent_requests = deque(maxlen=20)

    def record_success(self, row: dict[str, Any]) -> None:
        self.total_requests += 1
        self.total_prompt_tokens += int(row.get("prompt_tokens", 0))
        self.total_generation_tokens += int(row.get("generation_tokens", 0))
        self.total_run_ms += float(row.get("run_ms", 0.0))
        prefix_match_tokens = int(row.get("longest_prefix_match_tokens", 0))
        self.total_prefix_match_tokens += prefix_match_tokens
        if row.get("cache_candidate"):
            self.cache_candidate_requests += 1
        self.recent_requests.append(
            {
                "request_id": row.get("request_id"),
                "created": row.get("created"),
                "policy": row.get("effective_policy"),
                "prefill_step_size": row.get("prefill_step_size"),
                "prompt_tokens": row.get("prompt_tokens"),
                "generation_tokens": row.get("generation_tokens"),
                "run_ms": row.get("run_ms"),
                "engine_lock_wait_ms": row.get("engine_lock_wait_ms"),
                "service_request_ms": row.get("service_request_ms"),
                "scheduler_queue_wait_ms": row.get("scheduler_queue_wait_ms"),
                "scheduler_active_requests_at_admit": row.get(
                    "scheduler_active_requests_at_admit"
                ),
                "scheduler_queued_requests_at_admit": row.get(
                    "scheduler_queued_requests_at_admit"
                ),
                "stream_first_token_ms": row.get("stream_first_token_ms"),
                "stream_mean_token_gap_ms": row.get("stream_mean_token_gap_ms"),
                "stream_token_events": row.get("stream_token_events"),
                "prompt_tps": row.get("prompt_tps"),
                "generation_tps": row.get("generation_tps"),
                "stop_reason": row.get("stop_reason"),
                "prompt_hash": row.get("prompt_hash"),
                "tokenized_prompt_hash": row.get("tokenized_prompt_hash"),
                "longest_prefix_match_tokens": row.get("longest_prefix_match_tokens"),
                "prefix_reuse_ratio": row.get("prefix_reuse_ratio"),
                "estimated_recompute_tokens": row.get("estimated_recompute_tokens"),
                "cache_candidate": row.get("cache_candidate"),
                "cache_reuse_enabled": row.get("cache_reuse_enabled"),
                "cache_hit": row.get("cache_hit"),
                "cache_created": row.get("cache_created"),
                "cache_population_mode": row.get("cache_population_mode"),
                "cache_scheduled": row.get("cache_scheduled"),
                "cache_pending": row.get("cache_pending"),
                "cache_stored_from_request": row.get("cache_stored_from_request"),
                "cache_request_trimmed_tokens": row.get(
                    "cache_request_trimmed_tokens"
                ),
                "cache_split_prefill": row.get("cache_split_prefill"),
                "cache_split_prefill_reason": row.get("cache_split_prefill_reason"),
                "cache_build_deduplicated": row.get("cache_build_deduplicated"),
                "cache_build_dedup_reason": row.get("cache_build_dedup_reason"),
                "cache_prepare_ms": row.get("cache_prepare_ms"),
                "cache_scope_hash": row.get("cache_scope_hash"),
                "cached_prefix_tokens": row.get("cached_prefix_tokens"),
                "actual_prefill_tokens": row.get("actual_prefill_tokens"),
                "cache_exact_match_trimmed": row.get("cache_exact_match_trimmed"),
                "prompt_progress_events": row.get("prompt_progress_events"),
                "prompt_progress_total_tokens": row.get(
                    "prompt_progress_total_tokens"
                ),
                "prompt_progress_processed_tokens": row.get(
                    "prompt_progress_processed_tokens"
                ),
                "prompt_progress_complete": row.get("prompt_progress_complete"),
                "generated_token_count_recorded": row.get(
                    "generated_token_count_recorded"
                ),
                "generated_prefix_cache_recorded": row.get(
                    "generated_prefix_cache_recorded"
                ),
                "generated_prefix_cache_tokens": row.get(
                    "generated_prefix_cache_tokens"
                ),
                "memory_prune_applied": row.get("memory_prune_applied"),
                "memory_prune_removed_entries": row.get(
                    "memory_prune_removed_entries"
                ),
            }
        )

    def record_failure(self) -> None:
        self.total_requests += 1
        self.failed_requests += 1

    def snapshot(self) -> dict[str, Any]:
        successful = max(self.total_requests - self.failed_requests, 0)
        return {
            "uptime_s": time.time() - self.started_at,
            "total_requests": self.total_requests,
            "successful_requests": successful,
            "failed_requests": self.failed_requests,
            "total_prompt_tokens": self.total_prompt_tokens,
            "total_generation_tokens": self.total_generation_tokens,
            "mean_run_ms": self.total_run_ms / successful if successful else None,
            "total_prefix_match_tokens": self.total_prefix_match_tokens,
            "cache_candidate_requests": self.cache_candidate_requests,
            "mean_prefix_match_tokens": (
                self.total_prefix_match_tokens / successful if successful else None
            ),
            "recent_requests": list(self.recent_requests),
        }


class PromptProgressRecorder:
    def __init__(self):
        self.lock = threading.Lock()
        self.started_at = time.perf_counter()
        self.events: list[dict[str, Any]] = []

    def callback(self, processed_tokens: int, total_tokens: int) -> dict[str, Any]:
        now = time.perf_counter()
        event = {
            "processed_tokens": int(processed_tokens),
            "total_tokens": int(total_tokens),
            "elapsed_ms": 1e3 * (now - self.started_at),
        }
        with self.lock:
            self.events.append(event)
        return event

    def snapshot(self) -> dict[str, Any]:
        with self.lock:
            events = list(self.events)
        if not events:
            return {
                "prompt_progress_events": 0,
                "prompt_progress_total_tokens": None,
                "prompt_progress_processed_tokens": None,
                "prompt_progress_first_ms": None,
                "prompt_progress_last_ms": None,
                "prompt_progress_complete": False,
                "prompt_progress_trace": [],
            }
        last = events[-1]
        return {
            "prompt_progress_events": len(events),
            "prompt_progress_total_tokens": last["total_tokens"],
            "prompt_progress_processed_tokens": last["processed_tokens"],
            "prompt_progress_first_ms": events[0]["elapsed_ms"],
            "prompt_progress_last_ms": last["elapsed_ms"],
            "prompt_progress_complete": (
                last["processed_tokens"] == last["total_tokens"]
            ),
            "prompt_progress_trace": events[-8:],
        }


class RequestRegistry:
    def __init__(self, *, max_completed: int = 64):
        self.lock = threading.RLock()
        self.active: dict[str, dict[str, Any]] = {}
        self.completed = deque(maxlen=max_completed)

    @staticmethod
    def _public(entry: dict[str, Any]) -> dict[str, Any]:
        return {
            key: value
            for key, value in entry.items()
            if key not in {"cancel_event"}
        }

    def begin(
        self,
        *,
        request_id: str,
        route: str,
        prompt_tokens: int,
        policy: str,
        prefill_step_size: int | None,
    ) -> None:
        with self.lock:
            self.active[request_id] = {
                "request_id": request_id,
                "route": route,
                "status": "queued",
                "created": time.time(),
                "updated": time.time(),
                "prompt_tokens": prompt_tokens,
                "policy": policy,
                "prefill_step_size": prefill_step_size,
                "cancel_requested": False,
                "cancelled_at": None,
                "cancel_event": threading.Event(),
            }

    def update(self, request_id: str, **changes: Any) -> None:
        with self.lock:
            entry = self.active.get(request_id)
            if entry is None:
                return
            entry.update(changes)
            entry["updated"] = time.time()

    def cancel(self, request_id: str) -> dict[str, Any]:
        with self.lock:
            entry = self.active.get(request_id)
            if entry is None:
                for completed in self.completed:
                    if completed.get("request_id") == request_id:
                        return {
                            "ok": False,
                            "reason": "request_not_active",
                            "request": dict(completed),
                        }
                return {"ok": False, "reason": "request_not_found"}
            entry["cancel_requested"] = True
            entry["cancelled_at"] = time.time()
            entry["status"] = "cancelling"
            entry["updated"] = time.time()
            entry["cancel_event"].set()
            return {"ok": True, "request": self._public(entry)}

    def check_cancelled(self, request_id: str) -> None:
        with self.lock:
            entry = self.active.get(request_id)
            if entry is not None and entry["cancel_event"].is_set():
                raise RequestCancelled(f"request {request_id} cancelled")

    def finish(self, request_id: str, *, status: str, **changes: Any) -> None:
        with self.lock:
            entry = self.active.pop(request_id, None)
            if entry is None:
                return
            entry.update(changes)
            entry["status"] = status
            entry["finished"] = time.time()
            entry["updated"] = entry["finished"]
            self.completed.append(self._public(entry))

    def snapshot(self) -> dict[str, Any]:
        with self.lock:
            return {
                "active": [self._public(entry) for entry in self.active.values()],
                "completed": list(self.completed),
            }


class PrefixOpportunityTracker:
    def __init__(self, *, max_recent: int = 32, min_match_tokens: int = 32):
        self.max_recent = max_recent
        self.min_match_tokens = min_match_tokens
        self.lock = threading.Lock()
        self.recent_prompts = deque(maxlen=max_recent)

    @staticmethod
    def _hash_text(text: str) -> str:
        return hashlib.blake2b(text.encode("utf-8"), digest_size=16).hexdigest()

    @staticmethod
    def _hash_tokens(tokens: list[int]) -> str:
        payload = ",".join(str(token) for token in tokens).encode("utf-8")
        return hashlib.blake2b(payload, digest_size=16).hexdigest()

    @staticmethod
    def _common_prefix_len(left: list[int], right: list[int]) -> int:
        count = 0
        for left_token, right_token in zip(left, right, strict=False):
            if left_token != right_token:
                break
            count += 1
        return count

    def inspect(self, *, prompt: str, tokens: list[int]) -> dict[str, Any]:
        prompt_hash = self._hash_text(prompt)
        token_hash = self._hash_tokens(tokens)
        token_count = len(tokens)

        with self.lock:
            best_match = {
                "request_id": None,
                "prompt_hash": None,
                "tokenized_prompt_hash": None,
                "tokens": [],
                "match_tokens": 0,
            }
            for prior in self.recent_prompts:
                match_tokens = self._common_prefix_len(tokens, prior["tokens"])
                if match_tokens > best_match["match_tokens"]:
                    best_match = {**prior, "match_tokens": match_tokens}

            longest_prefix_match_tokens = int(best_match["match_tokens"])
            prefix_reuse_ratio = (
                longest_prefix_match_tokens / token_count if token_count else 0.0
            )
            estimated_recompute_tokens = max(token_count - longest_prefix_match_tokens, 0)
            cache_candidate = longest_prefix_match_tokens >= self.min_match_tokens
            analysis = {
                "prompt_hash": prompt_hash,
                "tokenized_prompt_hash": token_hash,
                "prefix_signature": (
                    self._hash_tokens(tokens[: min(token_count, self.min_match_tokens)])
                    if tokens
                    else None
                ),
                "longest_prefix_match_tokens": longest_prefix_match_tokens,
                "prefix_reuse_ratio": prefix_reuse_ratio,
                "estimated_recompute_tokens": estimated_recompute_tokens,
                "cache_candidate": cache_candidate,
                "matched_request_id": best_match["request_id"],
                "matched_prompt_hash": best_match["prompt_hash"],
                "matched_tokenized_prompt_hash": best_match["tokenized_prompt_hash"],
                "prefix_tracker_recent_size": len(self.recent_prompts),
            }
            return analysis

    def record(self, *, request_id: str, prompt: str, tokens: list[int]) -> None:
        with self.lock:
            self.recent_prompts.append(
                {
                    "request_id": request_id,
                    "prompt_hash": self._hash_text(prompt),
                    "tokenized_prompt_hash": self._hash_tokens(tokens),
                    "tokens": list(tokens),
                }
            )

    def record_tokens(
        self,
        *,
        request_id: str,
        prompt: str,
        tokens: list[int],
    ) -> None:
        self.record(request_id=request_id, prompt=prompt, tokens=tokens)


class PrefixKVCacheStore:
    def __init__(self, *, max_entries: int = 16):
        self.max_entries = max_entries
        self.lock = threading.RLock()
        self.entries = {}
        self.lru = deque()
        self.evictions = 0
        self.prunes = 0

    @staticmethod
    def key_for_tokens(tokens: list[int], *, scope: dict[str, Any] | None = None) -> str:
        payload = json.dumps(
            {
                "scope": scope or {},
                "tokens": tokens,
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return hashlib.blake2b(payload, digest_size=16).hexdigest()

    def get(self, key: str):
        with self.lock:
            entry = self.entries.get(key)
            if entry is None:
                return None
            try:
                self.lru.remove(key)
            except ValueError:
                pass
            self.lru.append(key)
            entry["hits"] += 1
            return entry

    def put(
        self,
        *,
        key: str,
        tokens: list[int],
        scope: dict[str, Any],
        prompt_cache,
    ) -> None:
        with self.lock:
            if key in self.entries:
                try:
                    self.lru.remove(key)
                except ValueError:
                    pass
            self.entries[key] = {
                "tokens": list(tokens),
                "scope": dict(scope),
                "prompt_cache": prompt_cache,
                "hits": 0,
            }
            self.lru.append(key)
            while len(self.lru) > self.max_entries:
                old_key = self.lru.popleft()
                self.entries.pop(old_key, None)
                self.evictions += 1

    def prune_to(self, target_entries: int) -> dict[str, Any]:
        target_entries = max(target_entries, 0)
        with self.lock:
            before = len(self.entries)
            removed = []
            while len(self.lru) > target_entries:
                old_key = self.lru.popleft()
                if old_key in self.entries:
                    self.entries.pop(old_key, None)
                    removed.append(old_key)
            if removed:
                self.evictions += len(removed)
                self.prunes += 1
            return {
                "before_entries": before,
                "after_entries": len(self.entries),
                "removed_entries": len(removed),
                "removed_keys": removed,
                "evictions": self.evictions,
                "prunes": self.prunes,
            }

    def configure(self, *, max_entries: int | None = None) -> dict[str, Any]:
        with self.lock:
            before = self.snapshot()
            if max_entries is not None:
                self.max_entries = max(max_entries, 0)
            removed = []
            while len(self.lru) > self.max_entries:
                old_key = self.lru.popleft()
                if old_key in self.entries:
                    self.entries.pop(old_key, None)
                    removed.append(old_key)
            if removed:
                self.evictions += len(removed)
                self.prunes += 1
            return {
                "before": before,
                "after": self.snapshot(),
                "removed_entries": len(removed),
                "removed_keys": removed,
            }

    def snapshot(self) -> dict[str, Any]:
        with self.lock:
            return {
                "entries": len(self.entries),
                "max_entries": self.max_entries,
                "evictions": self.evictions,
                "prunes": self.prunes,
                "keys": [
                    {
                        "key": key,
                        "tokens": len(self.entries[key]["tokens"]),
                        "hits": self.entries[key]["hits"],
                        "scope": self.entries[key]["scope"],
                    }
                    for key in self.lru
                    if key in self.entries
                ],
            }


class SchedulerRejected(RuntimeError):
    pass


class RequestScheduler:
    def __init__(
        self,
        *,
        max_concurrent_requests: int = 1,
        max_queued_requests: int = 16,
        queue_timeout_ms: int = 30000,
    ):
        self.max_concurrent_requests = max_concurrent_requests
        self.max_queued_requests = max_queued_requests
        self.queue_timeout_ms = queue_timeout_ms
        self.condition = threading.Condition(threading.RLock())
        self.active_requests = 0
        self.queued_requests = 0
        self.total_admitted = 0
        self.total_completed = 0
        self.total_rejected = 0
        self.total_queue_wait_ms = 0.0
        self.max_observed_queue_wait_ms = 0.0

    def admit(self):
        return SchedulerAdmission(self)

    def snapshot(self) -> dict[str, Any]:
        with self.condition:
            return {
                "max_concurrent_requests": self.max_concurrent_requests,
                "max_queued_requests": self.max_queued_requests,
                "queue_timeout_ms": self.queue_timeout_ms,
                "active_requests": self.active_requests,
                "queued_requests": self.queued_requests,
                "total_admitted": self.total_admitted,
                "total_completed": self.total_completed,
                "total_rejected": self.total_rejected,
                "mean_queue_wait_ms": (
                    self.total_queue_wait_ms / self.total_admitted
                    if self.total_admitted
                    else 0.0
                ),
                "max_observed_queue_wait_ms": self.max_observed_queue_wait_ms,
            }

    def wait_until_idle(self, *, timeout_ms: int) -> bool:
        deadline = time.perf_counter() + timeout_ms / 1000
        with self.condition:
            while self.active_requests > 0 or self.queued_requests > 0:
                remaining = deadline - time.perf_counter()
                if remaining <= 0:
                    return False
                self.condition.wait(timeout=remaining)
            return True

    def wait_until_idle_for(
        self,
        *,
        timeout_ms: int,
        grace_ms: int,
    ) -> tuple[bool, float, int]:
        wait_t0 = time.perf_counter()
        deadline = wait_t0 + timeout_ms / 1000
        idle_since: float | None = None
        resets = 0
        grace_s = max(grace_ms, 0) / 1000

        with self.condition:
            while True:
                now = time.perf_counter()
                busy = self.active_requests > 0 or self.queued_requests > 0
                if busy:
                    if idle_since is not None:
                        resets += 1
                        idle_since = None
                    remaining = deadline - now
                    if remaining <= 0:
                        return False, 1e3 * (time.perf_counter() - wait_t0), resets
                    self.condition.wait(timeout=remaining)
                    continue

                if grace_s <= 0:
                    return True, 1e3 * (time.perf_counter() - wait_t0), resets

                if idle_since is None:
                    idle_since = now

                grace_remaining = grace_s - (now - idle_since)
                if grace_remaining <= 0:
                    return True, 1e3 * (time.perf_counter() - wait_t0), resets

                remaining = deadline - now
                if remaining <= 0:
                    return False, 1e3 * (time.perf_counter() - wait_t0), resets
                self.condition.wait(timeout=min(remaining, grace_remaining))

    def configure(
        self,
        *,
        max_concurrent_requests: int | None = None,
        max_queued_requests: int | None = None,
        queue_timeout_ms: int | None = None,
    ) -> dict[str, Any]:
        with self.condition:
            before = self.snapshot()
            if max_concurrent_requests is not None:
                self.max_concurrent_requests = max(max_concurrent_requests, 1)
            if max_queued_requests is not None:
                self.max_queued_requests = max(max_queued_requests, 0)
            if queue_timeout_ms is not None:
                self.queue_timeout_ms = max(queue_timeout_ms, 1)
            self.condition.notify_all()
            return {
                "before": before,
                "after": self.snapshot(),
            }


class SchedulerAdmission:
    def __init__(self, scheduler: RequestScheduler):
        self.scheduler = scheduler
        self.info: dict[str, Any] | None = None

    def __enter__(self) -> dict[str, Any]:
        start = time.perf_counter()
        scheduler = self.scheduler
        deadline = start + scheduler.queue_timeout_ms / 1000

        with scheduler.condition:
            if (
                scheduler.active_requests >= scheduler.max_concurrent_requests
                and scheduler.queued_requests >= scheduler.max_queued_requests
            ):
                scheduler.total_rejected += 1
                raise SchedulerRejected("resident engine queue is full")

            scheduler.queued_requests += 1
            scheduler.condition.notify_all()
            try:
                while scheduler.active_requests >= scheduler.max_concurrent_requests:
                    remaining = deadline - time.perf_counter()
                    if remaining <= 0:
                        scheduler.total_rejected += 1
                        raise SchedulerRejected("resident engine queue wait timed out")
                    scheduler.condition.wait(timeout=remaining)

                scheduler.queued_requests -= 1
                scheduler.active_requests += 1
                scheduler.condition.notify_all()
                scheduler.total_admitted += 1
                queue_wait_ms = 1e3 * (time.perf_counter() - start)
                scheduler.total_queue_wait_ms += queue_wait_ms
                scheduler.max_observed_queue_wait_ms = max(
                    scheduler.max_observed_queue_wait_ms,
                    queue_wait_ms,
                )
                self.info = {
                    "scheduler_queue_wait_ms": queue_wait_ms,
                    "scheduler_max_concurrent_requests": (
                        scheduler.max_concurrent_requests
                    ),
                    "scheduler_active_requests_at_admit": scheduler.active_requests,
                    "scheduler_queued_requests_at_admit": scheduler.queued_requests,
                }
                return self.info
            except Exception:
                scheduler.queued_requests = max(scheduler.queued_requests - 1, 0)
                scheduler.condition.notify_all()
                raise

    def __exit__(self, exc_type, exc, tb) -> None:
        scheduler = self.scheduler
        with scheduler.condition:
            scheduler.active_requests = max(scheduler.active_requests - 1, 0)
            scheduler.total_completed += 1
            scheduler.condition.notify_all()


class EngineExecutionLock:
    def __init__(self):
        self.condition = threading.Condition()
        self.active = False
        self.active_kind: str | None = None
        self.foreground_waiters = 0
        self.background_waiters = 0
        self.foreground_acquires = 0
        self.background_acquires = 0
        self.background_priority_deferrals = 0

    def acquire_foreground(self) -> float:
        wait_t0 = time.perf_counter()
        with self.condition:
            self.foreground_waiters += 1
            try:
                while self.active:
                    self.condition.wait()
                self.active = True
                self.active_kind = "foreground"
                self.foreground_acquires += 1
                return 1e3 * (time.perf_counter() - wait_t0)
            finally:
                self.foreground_waiters = max(self.foreground_waiters - 1, 0)

    def acquire_background(self) -> tuple[float, int]:
        wait_t0 = time.perf_counter()
        deferrals = 0
        with self.condition:
            self.background_waiters += 1
            try:
                while self.active or self.foreground_waiters > 0:
                    if self.foreground_waiters > 0:
                        deferrals += 1
                    self.condition.wait()
                self.active = True
                self.active_kind = "background"
                self.background_acquires += 1
                self.background_priority_deferrals += deferrals
                return 1e3 * (time.perf_counter() - wait_t0), deferrals
            finally:
                self.background_waiters = max(self.background_waiters - 1, 0)

    def release(self) -> None:
        with self.condition:
            self.active = False
            self.active_kind = None
            self.condition.notify_all()

    def snapshot(self) -> dict[str, Any]:
        with self.condition:
            return {
                "active": self.active,
                "active_kind": self.active_kind,
                "foreground_waiters": self.foreground_waiters,
                "background_waiters": self.background_waiters,
                "foreground_acquires": self.foreground_acquires,
                "background_acquires": self.background_acquires,
                "background_priority_deferrals": self.background_priority_deferrals,
            }


class ResidentEngine:
    def __init__(
        self,
        *,
        model_path: str,
        profile_path: Path | None,
        warmup_prompt_tokens: list[int],
        warmup_profile_prefill: bool,
        require_gpu: bool,
        max_concurrent_requests: int,
        max_queued_requests: int,
        queue_timeout_ms: int,
        engine_preset: EnginePresetName,
        prefix_cache_max_entries: int,
        prefix_cache_memory_limit_mb: float,
        prefix_cache_min_entries: int,
        prefix_cache_population_mode: str,
        prefix_cache_async_idle_timeout_ms: int,
        prefix_cache_async_idle_grace_ms: int,
        warmup_mode: WarmupMode,
        startup_context: dict[str, Any] | None = None,
    ):
        engine_init_t0 = time.perf_counter()
        engine_init_epoch = time.time()
        self.startup_timings = dict(startup_context or {})
        self.startup_timings["engine_init_started_at_epoch"] = engine_init_epoch
        parent_started_at = self.startup_timings.get("parent_started_at_epoch")
        if isinstance(parent_started_at, int | float):
            self.startup_timings["parent_start_to_module_import_ms"] = (
                1e3 * (MODULE_IMPORTED_AT_EPOCH - parent_started_at)
            )
            self.startup_timings["parent_start_to_engine_init_start_ms"] = (
                1e3 * (engine_init_epoch - parent_started_at)
            )
        self.model_path = model_path
        self.profile_path = profile_path
        self.warmup_prompt_tokens = warmup_prompt_tokens
        self.warmup_profile_prefill = warmup_profile_prefill
        self.warmup_mode = warmup_mode
        self.warmup_lock = threading.RLock()
        self.warmup_results: list[dict[str, Any]] = []
        self.warmup_error: str | None = None
        self.warmup_thread: threading.Thread | None = None
        self.warmup_started_at: float | None = None
        self.warmup_completed_at: float | None = None
        t0 = time.perf_counter()
        self.device_info = runtime_device_info()
        self.startup_timings["runtime_device_info_ms"] = 1e3 * (
            time.perf_counter() - t0
        )
        self.metrics = EngineMetrics()
        self.request_registry = RequestRegistry()
        if require_gpu and not (
            self.device_info["metal_available"]
            and "gpu" in self.device_info["default_device"]
        ):
            raise RuntimeError("MLX is not using a Metal GPU")

        t0 = time.perf_counter()
        self.validate_model_access(model_path)
        self.startup_timings["validate_model_access_ms"] = 1e3 * (
            time.perf_counter() - t0
        )
        t0 = time.perf_counter()
        self.backend = detect_backend(model_path)
        self.startup_timings["detect_backend_ms"] = 1e3 * (time.perf_counter() - t0)
        if self.backend != "text":
            raise RuntimeError("resident_mlx_service.py currently supports text models only")

        t0 = time.perf_counter()
        from mlx_lm.generate import generate_step, stream_generate
        from mlx_lm.models.cache import can_trim_prompt_cache, make_prompt_cache, trim_prompt_cache
        from mlx_lm.utils import load, load_model, load_tokenizer
        self.startup_timings["import_mlx_lm_helpers_ms"] = 1e3 * (
            time.perf_counter() - t0
        )

        self.generate_step = generate_step
        self.can_trim_prompt_cache = can_trim_prompt_cache
        self.make_prompt_cache = make_prompt_cache
        self.trim_prompt_cache = trim_prompt_cache
        self.stream_generate = stream_generate
        self.load_model = load_model
        self.load_tokenizer = load_tokenizer
        t0 = time.perf_counter()
        self.profile = self._load_profile(profile_path)
        self.startup_timings["load_profile_ms"] = 1e3 * (time.perf_counter() - t0)
        t0 = time.perf_counter()
        self.engine_preset = engine_preset
        self.state_lock = threading.RLock()
        self.execution_lock = EngineExecutionLock()
        self.prefix_tracker = PrefixOpportunityTracker()
        self.prefix_kv_cache = PrefixKVCacheStore(max_entries=prefix_cache_max_entries)
        self.prefix_cache_memory_limit_bytes = (
            int(prefix_cache_memory_limit_mb * 1024 * 1024)
            if prefix_cache_memory_limit_mb > 0
            else None
        )
        self.prefix_cache_min_entries = max(prefix_cache_min_entries, 0)
        self.prefix_cache_memory_prunes = 0
        self.last_prefix_cache_prune: dict[str, Any] | None = None
        if prefix_cache_population_mode not in {"sync", "async", "request", "off"}:
            raise ValueError(
                "prefix cache population mode must be sync, async, request, or off"
            )
        self.prefix_cache_population_mode = prefix_cache_population_mode
        self.prefix_cache_pending_builds: set[str] = set()
        self.prefix_cache_build_lock = threading.RLock()
        self.prefix_cache_async_builds_started = 0
        self.prefix_cache_async_builds_completed = 0
        self.prefix_cache_async_builds_failed = 0
        self.prefix_cache_async_builds_skipped = 0
        self.prefix_cache_async_background_wait_ms = 0.0
        self.prefix_cache_async_priority_deferrals = 0
        self.prefix_cache_existing_build_reuses = 0
        self.prefix_cache_pending_build_deduplications = 0
        self.prefix_cache_async_idle_timeout_ms = prefix_cache_async_idle_timeout_ms
        self.prefix_cache_async_idle_grace_ms = prefix_cache_async_idle_grace_ms
        self.prefix_cache_async_idle_grace_wait_ms = 0.0
        self.prefix_cache_async_idle_grace_resets = 0
        self.last_prefix_cache_async_error: str | None = None
        self.scheduler = RequestScheduler(
            max_concurrent_requests=max_concurrent_requests,
            max_queued_requests=max_queued_requests,
            queue_timeout_ms=queue_timeout_ms,
        )
        self.startup_timings["engine_state_init_ms"] = 1e3 * (
            time.perf_counter() - t0
        )

        load_t0 = time.perf_counter()
        try:
            self.model, self.tokenizer = load(model_path)
            self.load_strict = True
            self.load_fallback_reason = None
        except ValueError as exc:
            message = str(exc)
            if "parameters not in model" not in message or "vision_tower" not in message:
                raise
            self.model, _config = load_model(Path(model_path), strict=False)
            self.tokenizer = load_tokenizer(model_path)
            self.load_strict = False
            self.load_fallback_reason = "extra_vision_tower_weights_ignored"
        self.load_ms = 1e3 * (time.perf_counter() - load_t0)
        self.startup_timings["model_load_ms"] = self.load_ms
        self.started_at = time.time()
        if self.warmup_mode == "sync":
            warmup_t0 = time.perf_counter()
            self._run_warmup()
            self.startup_timings["warmup_ms"] = 1e3 * (time.perf_counter() - warmup_t0)
        elif self.warmup_mode == "async":
            self.startup_timings["warmup_ms"] = 0.0
            self.warmup_thread = threading.Thread(
                target=self._run_warmup,
                name="resident-warmup",
                daemon=True,
            )
            self.warmup_thread.start()
        elif self.warmup_mode == "off":
            self.startup_timings["warmup_ms"] = 0.0
            self.warmup_started_at = None
            self.warmup_completed_at = self.started_at
        else:
            raise ValueError("warmup mode must be sync, async, or off")
        self.startup_timings["engine_init_total_ms"] = 1e3 * (
            time.perf_counter() - engine_init_t0
        )

    @staticmethod
    def mlx_memory_snapshot() -> dict[str, Any]:
        snapshot = {}
        for name in ("get_active_memory", "get_cache_memory", "get_peak_memory"):
            func = getattr(mx, name, None)
            if func is None:
                continue
            key = name.removeprefix("get_") + "_bytes"
            try:
                snapshot[key] = int(func())
            except Exception as exc:
                snapshot[key + "_error"] = str(exc)
        return snapshot

    def prefix_cache_policy_snapshot(self) -> dict[str, Any]:
        with self.prefix_cache_build_lock:
            return {
                "memory_limit_bytes": self.prefix_cache_memory_limit_bytes,
                "min_entries": self.prefix_cache_min_entries,
                "memory_prunes": self.prefix_cache_memory_prunes,
                "last_prune": self.last_prefix_cache_prune,
                "population_mode": self.prefix_cache_population_mode,
                "pending_async_builds": len(self.prefix_cache_pending_builds),
                "async_builds_started": self.prefix_cache_async_builds_started,
                "async_builds_completed": self.prefix_cache_async_builds_completed,
                "async_builds_failed": self.prefix_cache_async_builds_failed,
                "async_builds_skipped": self.prefix_cache_async_builds_skipped,
                "async_background_wait_ms": (
                    self.prefix_cache_async_background_wait_ms
                ),
                "async_priority_deferrals": (
                    self.prefix_cache_async_priority_deferrals
                ),
                "existing_build_reuses": self.prefix_cache_existing_build_reuses,
                "pending_build_deduplications": (
                    self.prefix_cache_pending_build_deduplications
                ),
                "async_idle_timeout_ms": self.prefix_cache_async_idle_timeout_ms,
                "async_idle_grace_ms": self.prefix_cache_async_idle_grace_ms,
                "async_idle_grace_wait_ms": (
                    self.prefix_cache_async_idle_grace_wait_ms
                ),
                "async_idle_grace_resets": (
                    self.prefix_cache_async_idle_grace_resets
                ),
                "last_async_error": self.last_prefix_cache_async_error,
            }

    @staticmethod
    def prompt_cache_trim_blocker_reason(cache_entry) -> str | None:
        class_name = type(cache_entry).__name__
        if class_name == "ArraysCache":
            return "array_or_recurrent_state_not_suffix_trimmable"
        if class_name == "CacheList":
            blockers = []
            for child in getattr(cache_entry, "caches", []):
                reason = ResidentEngine.prompt_cache_trim_blocker_reason(child)
                if reason is not None:
                    blockers.append(f"{type(child).__name__}:{reason}")
            return ",".join(blockers) if blockers else None
        try:
            if cache_entry.is_trimmable():
                return None
        except Exception as exc:
            return f"trimmability_check_error:{exc}"
        return f"{class_name}_not_trimmable"

    def prompt_cache_capabilities_snapshot(self) -> dict[str, Any]:
        prompt_cache = self.make_prompt_cache(self.model)
        entries = []
        for index, cache_entry in enumerate(prompt_cache):
            is_trimmable = False
            blocker_reason = None
            try:
                is_trimmable = bool(cache_entry.is_trimmable())
            except Exception as exc:
                blocker_reason = f"trimmability_check_error:{exc}"
                entries.append(
                    {
                        "index": index,
                        "class": type(cache_entry).__name__,
                        "trimmable": False,
                        "trim_blocker_reason": blocker_reason,
                    }
                )
                continue
            if not is_trimmable:
                blocker_reason = self.prompt_cache_trim_blocker_reason(cache_entry)
            entries.append(
                {
                    "index": index,
                    "class": type(cache_entry).__name__,
                    "trimmable": is_trimmable,
                    "trim_blocker_reason": blocker_reason,
                }
            )
        non_trimmable_entries = [
            entry for entry in entries if not bool(entry["trimmable"])
        ]
        return {
            "entry_count": len(entries),
            "all_trimmable": all(entry["trimmable"] for entry in entries),
            "trimmable_entries": sum(1 for entry in entries if entry["trimmable"]),
            "non_trimmable_entries": len(non_trimmable_entries),
            "non_trimmable_classes": sorted(
                {entry["class"] for entry in non_trimmable_entries}
            ),
            "trim_blocker_reasons": sorted(
                {
                    entry["trim_blocker_reason"]
                    for entry in non_trimmable_entries
                    if entry.get("trim_blocker_reason")
                }
            ),
            "classes": sorted({entry["class"] for entry in entries}),
            "entries": entries,
        }

    def configure_runtime(self, config: dict[str, Any]) -> dict[str, Any]:
        changes: dict[str, Any] = {}
        if "engine_preset" in config:
            before = self.engine_preset
            self.engine_preset = config["engine_preset"]
            changes["engine_preset"] = {
                "before": before,
                "after": self.engine_preset,
            }

        scheduler_keys = {
            "max_concurrent_requests",
            "max_queued_requests",
            "queue_timeout_ms",
        }
        scheduler_config = {
            key: config[key]
            for key in scheduler_keys
            if key in config
        }
        if scheduler_config:
            changes["scheduler"] = self.scheduler.configure(**scheduler_config)

        if "prefix_cache_max_entries" in config:
            changes["prefix_kv_cache"] = self.prefix_kv_cache.configure(
                max_entries=config["prefix_cache_max_entries"],
            )

        policy_changes = {}
        with self.prefix_cache_build_lock:
            if "prefix_cache_memory_limit_mb" in config:
                before = self.prefix_cache_memory_limit_bytes
                limit_mb = float(config["prefix_cache_memory_limit_mb"])
                self.prefix_cache_memory_limit_bytes = (
                    int(limit_mb * 1024 * 1024) if limit_mb > 0 else None
                )
                policy_changes["memory_limit_bytes"] = {
                    "before": before,
                    "after": self.prefix_cache_memory_limit_bytes,
                }
            if "prefix_cache_min_entries" in config:
                before = self.prefix_cache_min_entries
                self.prefix_cache_min_entries = max(
                    int(config["prefix_cache_min_entries"]),
                    0,
                )
                policy_changes["min_entries"] = {
                    "before": before,
                    "after": self.prefix_cache_min_entries,
                }
            if "prefix_cache_population_mode" in config:
                before = self.prefix_cache_population_mode
                mode = config["prefix_cache_population_mode"]
                if mode not in {"sync", "async", "request", "off"}:
                    raise ValueError(
                        "prefix cache population mode must be sync, async, request, or off"
                    )
                self.prefix_cache_population_mode = mode
                policy_changes["population_mode"] = {
                    "before": before,
                    "after": self.prefix_cache_population_mode,
                }
            if "prefix_cache_async_idle_timeout_ms" in config:
                before = self.prefix_cache_async_idle_timeout_ms
                self.prefix_cache_async_idle_timeout_ms = max(
                    int(config["prefix_cache_async_idle_timeout_ms"]),
                    1,
                )
                policy_changes["async_idle_timeout_ms"] = {
                    "before": before,
                    "after": self.prefix_cache_async_idle_timeout_ms,
                }
            if "prefix_cache_async_idle_grace_ms" in config:
                before = self.prefix_cache_async_idle_grace_ms
                self.prefix_cache_async_idle_grace_ms = max(
                    int(config["prefix_cache_async_idle_grace_ms"]),
                    0,
                )
                policy_changes["async_idle_grace_ms"] = {
                    "before": before,
                    "after": self.prefix_cache_async_idle_grace_ms,
                }
        if policy_changes:
            changes["prefix_cache_policy"] = policy_changes

        if (
            "prefix_cache_memory_limit_mb" in config
            or "prefix_cache_min_entries" in config
        ):
            changes["memory_pressure_check"] = self.maybe_apply_memory_pressure_policy(
                reason="runtime_config_update",
            )

        return {
            "ok": True,
            "dry_run": False,
            "applied": config,
            "changes": changes,
            "engine": self.metadata(),
        }

    def prune_prefix_cache(
        self,
        *,
        target_entries: int,
        clear_mlx_cache: bool,
        reason: str,
        memory_before: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        with self.state_lock:
            memory_before = memory_before or self.mlx_memory_snapshot()
            prune = self.prefix_kv_cache.prune_to(target_entries)
            if clear_mlx_cache and hasattr(mx, "clear_cache"):
                mx.clear_cache()
            gc.collect()
            memory_after = self.mlx_memory_snapshot()
        row = {
            "reason": reason,
            "target_entries": target_entries,
            "clear_mlx_cache": clear_mlx_cache,
            "memory_before": memory_before,
            "memory_after": memory_after,
            **prune,
        }
        if prune["removed_entries"]:
            self.prefix_cache_memory_prunes += 1
            self.last_prefix_cache_prune = row
        return row

    def maybe_apply_memory_pressure_policy(self, *, reason: str) -> dict[str, Any]:
        memory = self.mlx_memory_snapshot()
        limit = self.prefix_cache_memory_limit_bytes
        cache_memory = memory.get("cache_memory_bytes")
        if limit is None or cache_memory is None or cache_memory <= limit:
            return {
                "memory_prune_applied": False,
                "memory_prune_reason": None,
                "memory_prune_removed_entries": 0,
                "memory_prune_cache_memory_bytes": cache_memory,
                "memory_prune_limit_bytes": limit,
            }
        prune = self.prune_prefix_cache(
            target_entries=self.prefix_cache_min_entries,
            clear_mlx_cache=True,
            reason=reason,
            memory_before=memory,
        )
        return {
            "memory_prune_applied": prune["removed_entries"] > 0,
            "memory_prune_reason": reason,
            "memory_prune_removed_entries": prune["removed_entries"],
            "memory_prune_cache_memory_bytes": cache_memory,
            "memory_prune_limit_bytes": limit,
        }

    def build_prefix_cache_locked(
        self,
        *,
        key: str,
        prefix_tokens: list[int],
        scope: dict[str, Any],
        prefill_step_size: int | None,
    ):
        existing = self.prefix_kv_cache.get(key)
        if existing is not None and existing["scope"] == scope:
            return existing

        prompt_cache = self.make_prompt_cache(self.model)
        prefix_array = mx.array(prefix_tokens)
        for _ in self.generate_step(
            prefix_array,
            self.model,
            max_tokens=0,
            prompt_cache=prompt_cache,
            prefill_step_size=prefill_step_size or 2048,
        ):
            pass
        # Materialize cache state before it is copied or reused.
        mx.eval([c.state for c in prompt_cache])
        self.prefix_kv_cache.put(
            key=key,
            tokens=prefix_tokens,
            scope=scope,
            prompt_cache=prompt_cache,
        )
        return self.prefix_kv_cache.get(key)

    def schedule_prefix_cache_build(
        self,
        *,
        key: str,
        prefix_tokens: list[int],
        scope: dict[str, Any],
        prefill_step_size: int | None,
    ) -> bool:
        with self.prefix_cache_build_lock:
            existing = self.prefix_kv_cache.get(key)
            if existing is not None and existing["scope"] == scope:
                self.prefix_cache_existing_build_reuses += 1
                return False
            if key in self.prefix_cache_pending_builds:
                self.prefix_cache_pending_build_deduplications += 1
                return False
            self.prefix_cache_pending_builds.add(key)
            self.prefix_cache_async_builds_started += 1

        def worker() -> None:
            try:
                idle, grace_wait_ms, grace_resets = self.scheduler.wait_until_idle_for(
                    timeout_ms=self.prefix_cache_async_idle_timeout_ms,
                    grace_ms=self.prefix_cache_async_idle_grace_ms,
                )
                with self.prefix_cache_build_lock:
                    self.prefix_cache_async_idle_grace_wait_ms += grace_wait_ms
                    self.prefix_cache_async_idle_grace_resets += grace_resets
                if not idle:
                    with self.prefix_cache_build_lock:
                        self.prefix_cache_async_builds_skipped += 1
                        self.last_prefix_cache_async_error = (
                            "async prefix cache build skipped: engine did not become "
                            "idle before timeout"
                        )
                    return
                background_wait_ms, priority_deferrals = (
                    self.execution_lock.acquire_background()
                )
                try:
                    self.build_prefix_cache_locked(
                        key=key,
                        prefix_tokens=prefix_tokens,
                        scope=scope,
                        prefill_step_size=prefill_step_size,
                    )
                finally:
                    self.execution_lock.release()
                with self.prefix_cache_build_lock:
                    self.prefix_cache_async_builds_completed += 1
                    self.prefix_cache_async_background_wait_ms += background_wait_ms
                    self.prefix_cache_async_priority_deferrals += priority_deferrals
                    self.last_prefix_cache_async_error = None
                self.maybe_apply_memory_pressure_policy(reason="async_cache_build")
            except Exception as exc:
                with self.prefix_cache_build_lock:
                    self.prefix_cache_async_builds_failed += 1
                    self.last_prefix_cache_async_error = str(exc)
            finally:
                with self.prefix_cache_build_lock:
                    self.prefix_cache_pending_builds.discard(key)

        thread = threading.Thread(
            target=worker,
            name=f"prefix-cache-build-{key[:8]}",
            daemon=True,
        )
        thread.start()
        return True

    def schedule_deferred_prefix_cache_build(
        self,
        cache_info: dict[str, Any],
    ) -> dict[str, Any]:
        build = cache_info.pop("_async_cache_build", None)
        if build is None:
            return cache_info
        cache_info["cache_scheduled"] = self.schedule_prefix_cache_build(**build)
        return cache_info

    def cache_scope(self, metadata: dict[str, Any]) -> dict[str, Any]:
        tokenizer = (
            self.tokenizer.tokenizer
            if hasattr(self.tokenizer, "tokenizer")
            else self.tokenizer
        )
        chat_template = getattr(tokenizer, "chat_template", None)
        return {
            "model": self.model_path,
            "profile_path": str(self.profile_path) if self.profile_path else None,
            "backend": self.backend,
            "effective_policy": metadata["effective_policy"],
            "prefill_step_size": metadata["prefill_step_size"],
            "tokenizer_class": type(tokenizer).__name__,
            "chat_template_hash": (
                hashlib.blake2b(str(chat_template).encode("utf-8"), digest_size=16).hexdigest()
                if chat_template is not None
                else None
            ),
        }

    def _load_profile(self, profile_path: Path | None):
        if profile_path is None:
            return {}
        return json.loads(profile_path.read_text())

    @staticmethod
    def validate_model_access(model_path: str) -> None:
        config_path = Path(model_path) / "config.json"
        try:
            with config_path.open("rb") as f:
                f.read(1)
        except FileNotFoundError as exc:
            raise RuntimeError(f"model config not found: {config_path}") from exc
        except PermissionError as exc:
            raise RuntimeError(
                "model config is not readable by this process: "
                f"{config_path}. Grant the launching Terminal/tmux/Python process "
                "permission to read the model volume, or launch the service from a "
                "terminal context that already has that permission."
            ) from exc

    @staticmethod
    def discover_profile(model_path: str, explicit_profile: Path | None) -> Path | None:
        if explicit_profile is not None:
            return explicit_profile

        model_dir = Path(model_path)
        model_name = model_dir.name
        candidates = [
            model_dir / "mlx-engine-profile.json",
            model_dir / "prefill-profile.json",
            model_dir / f"{model_name}-prefill-profile.json",
            Path.cwd() / f"{model_name}-prefill-profile.json",
        ]
        for candidate in candidates:
            if candidate.is_file():
                return candidate
        return None

    def effective_policy(self, policy: PolicyName, prompt_tokens: int | None) -> PolicyName:
        if policy != "auto":
            return policy
        return (
            "memory_saver"
            if prompt_tokens is not None and prompt_tokens < 512
            else "throughput_default"
        )

    def selected_prefill_step_size(
        self,
        policy: PolicyName,
        override: int | None = None,
        prompt_tokens: int | None = None,
    ) -> int | None:
        step_size, _selection = self.selected_prefill_policy(
            policy,
            override=override,
            prompt_tokens=prompt_tokens,
        )
        return step_size

    def selected_prefill_band(
        self,
        prompt_tokens: int | None,
    ) -> dict[str, Any] | None:
        bands = self.profile.get("prompt_token_bands") or []
        if not bands or prompt_tokens is None:
            return None
        ordered = sorted(
            bands,
            key=lambda band: int(band.get("max_prompt_tokens") or 0),
        )
        for band in ordered:
            if prompt_tokens <= int(band.get("max_prompt_tokens") or 0):
                return band
        return ordered[-1]

    def selected_prefill_policy(
        self,
        policy: PolicyName,
        *,
        override: int | None = None,
        prompt_tokens: int | None = None,
    ) -> tuple[int | None, dict[str, Any]]:
        effective_policy = self.effective_policy(policy, prompt_tokens)
        if override is not None:
            return override, {
                "source": "request_override",
                "effective_policy": effective_policy,
                "band_min_prompt_tokens": None,
                "band_max_prompt_tokens": None,
            }

        band = self.selected_prefill_band(prompt_tokens)
        if band is not None:
            selected = (band.get("policy") or {}).get(effective_policy)
            if selected is not None:
                return selected.get("prefill_step_size"), {
                    "source": "prompt_token_band",
                    "effective_policy": effective_policy,
                    "band_min_prompt_tokens": band.get("min_prompt_tokens"),
                    "band_max_prompt_tokens": band.get("max_prompt_tokens"),
                }

        policy_block = self.profile.get("policy", {})
        selected = policy_block.get(effective_policy, {})
        return selected.get("prefill_step_size"), {
            "source": "global_policy",
            "effective_policy": effective_policy,
            "band_min_prompt_tokens": None,
            "band_max_prompt_tokens": None,
        }

    def prompt_token_count(self, prompt: str) -> int:
        return len(self.prompt_tokens(prompt))

    def prompt_tokens(self, prompt: str) -> list[int]:
        tokenizer = self.tokenizer.tokenizer if hasattr(self.tokenizer, "tokenizer") else self.tokenizer
        return list(tokenizer.encode(prompt))

    def request_metadata(
        self,
        *,
        prompt: str,
        policy: PolicyName,
        prefill_step_size_override: int | None,
    ) -> dict[str, Any]:
        tokens = self.prompt_tokens(prompt)
        prompt_tokens_estimate = len(tokens)
        prefill_step_size, prefill_selection = self.selected_prefill_policy(
            policy,
            override=prefill_step_size_override,
            prompt_tokens=prompt_tokens_estimate,
        )
        request_id = f"req_{uuid.uuid4().hex}"
        prefix_analysis = self.prefix_tracker.inspect(prompt=prompt, tokens=tokens)
        return {
            "request_id": request_id,
            "created": int(time.time()),
            "model": self.model_path,
            "backend": self.backend,
            "policy": policy,
            "effective_policy": prefill_selection["effective_policy"],
            "prefill_step_size": prefill_step_size,
            "prefill_selection_source": prefill_selection["source"],
            "prefill_band_min_prompt_tokens": (
                prefill_selection["band_min_prompt_tokens"]
            ),
            "prefill_band_max_prompt_tokens": (
                prefill_selection["band_max_prompt_tokens"]
            ),
            "prompt_tokens_estimate": prompt_tokens_estimate,
            "default_device": self.device_info["default_device"],
            "metal_available": self.device_info["metal_available"],
            "_prompt": prompt,
            "_prompt_tokens": tokens,
            **prefix_analysis,
        }

    def record_prefix_prompt(self, metadata: dict[str, Any]) -> None:
        self.prefix_tracker.record(
            request_id=metadata["request_id"],
            prompt=metadata["_prompt"],
            tokens=metadata["_prompt_tokens"],
        )

    def record_generated_prefix_prompt(
        self,
        *,
        metadata: dict[str, Any],
        text: str,
        generated_token_ids: list[int],
    ) -> tuple[list[int] | None, dict[str, Any]]:
        tokens = list(metadata["_prompt_tokens"]) + list(generated_token_ids)
        retokenized_tokens = self.prompt_tokens(metadata["_prompt"] + text)
        token_boundary_safe = retokenized_tokens == tokens
        if not token_boundary_safe:
            return None, {
                "generated_prefix_cache_recorded": False,
                "generated_prefix_cache_tokens": 0,
                "generated_prefix_cache_reason": "token_boundary_mismatch",
                "generated_prefix_token_boundary_safe": False,
                "generated_prefix_retokenized_tokens": len(retokenized_tokens),
                "generated_prefix_combined_tokens": len(tokens),
            }
        self.prefix_tracker.record_tokens(
            request_id=f"{metadata['request_id']}:generated",
            prompt=metadata["_prompt"] + text,
            tokens=tokens,
        )
        return tokens, {
            "generated_prefix_token_boundary_safe": True,
            "generated_prefix_retokenized_tokens": len(retokenized_tokens),
            "generated_prefix_combined_tokens": len(tokens),
        }

    def store_generated_prefix_cache(
        self,
        *,
        metadata: dict[str, Any],
        full_tokens: list[int],
        prompt_cache,
    ) -> dict[str, Any]:
        if (
            prompt_cache is None
            or not full_tokens
            or self.prefix_cache_population_mode == "off"
        ):
            return {
                "generated_prefix_cache_recorded": False,
                "generated_prefix_cache_tokens": 0,
                "generated_prefix_cache_reason": "disabled_or_empty",
            }

        scope = self.cache_scope(metadata)
        key = PrefixKVCacheStore.key_for_tokens(full_tokens, scope=scope)
        with self.prefix_cache_build_lock:
            if self.prefix_kv_cache.get(key) is not None:
                return {
                    "generated_prefix_cache_recorded": False,
                    "generated_prefix_cache_tokens": len(full_tokens),
                    "generated_prefix_cache_reason": "already_cached",
                }
            mx.eval([c.state for c in prompt_cache])
            self.prefix_kv_cache.put(
                key=key,
                tokens=full_tokens,
                scope=scope,
                prompt_cache=copy.deepcopy(prompt_cache),
            )
        return {
            "generated_prefix_cache_recorded": True,
            "generated_prefix_cache_tokens": len(full_tokens),
            "generated_prefix_cache_reason": "stored",
        }

    def store_request_prefix_cache(
        self,
        *,
        cache_info: dict[str, Any],
        prompt_cache,
        generated_token_count: int,
    ) -> dict[str, Any]:
        store = cache_info.pop("_request_cache_store", None)
        if store is None:
            return {}
        if prompt_cache is None:
            return {
                "cache_stored_from_request": False,
                "cache_request_store_reason": "missing_prompt_cache",
            }

        key = store["key"]
        scope = store["scope"]
        prefix_tokens = store["prefix_tokens"]
        prefill_step_size = store["prefill_step_size"]
        trim_tokens = int(store["suffix_tokens"]) + int(generated_token_count)

        with self.prefix_cache_build_lock:
            existing = self.prefix_kv_cache.get(key)
            if existing is not None and existing["scope"] == scope:
                return {
                    "cache_stored_from_request": False,
                    "cache_request_trimmed_tokens": trim_tokens,
                    "cache_request_store_reason": "already_cached",
                }

            request_cache = copy.deepcopy(prompt_cache)
            if not self.can_trim_prompt_cache(request_cache):
                scheduled = self.schedule_prefix_cache_build(
                    key=key,
                    prefix_tokens=prefix_tokens,
                    scope=scope,
                    prefill_step_size=prefill_step_size,
                )
                return {
                    "cache_stored_from_request": False,
                    "cache_scheduled": scheduled,
                    "cache_request_trimmed_tokens": trim_tokens,
                    "cache_request_store_reason": "not_trimmable_fallback_async",
                }
            trimmed = self.trim_prompt_cache(request_cache, trim_tokens)
            if trimmed != trim_tokens:
                scheduled = self.schedule_prefix_cache_build(
                    key=key,
                    prefix_tokens=prefix_tokens,
                    scope=scope,
                    prefill_step_size=prefill_step_size,
                )
                return {
                    "cache_stored_from_request": False,
                    "cache_scheduled": scheduled,
                    "cache_request_trimmed_tokens": trimmed,
                    "cache_request_store_reason": "trim_incomplete_fallback_async",
                }
            mx.eval([c.state for c in request_cache])
            self.prefix_kv_cache.put(
                key=key,
                tokens=prefix_tokens,
                scope=scope,
                prompt_cache=request_cache,
            )

        return {
            "cache_stored_from_request": True,
            "cache_request_trimmed_tokens": trim_tokens,
            "cache_request_store_reason": "stored",
        }

    @staticmethod
    def public_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
        return {
            key: value
            for key, value in metadata.items()
            if key not in {"_prompt", "_prompt_tokens"}
        }

    def prepare_prefix_cache_reuse(
        self,
        *,
        metadata: dict[str, Any],
    ) -> tuple[list[int] | str, Any | None, dict[str, Any]]:
        tokens = metadata["_prompt_tokens"]
        match_tokens = int(metadata.get("longest_prefix_match_tokens") or 0)
        cache_info = {
            "cache_reuse_enabled": False,
            "cache_hit": False,
            "cache_created": False,
            "cache_prepare_ms": 0.0,
            "cache_scope_hash": None,
            "cached_prefix_tokens": 0,
            "actual_prefill_tokens": len(tokens),
            "cache_exact_match_trimmed": False,
            "cache_population_mode": self.prefix_cache_population_mode,
            "cache_scheduled": False,
            "cache_pending": False,
            "cache_stored_from_request": False,
            "cache_request_trimmed_tokens": 0,
            "cache_request_store_reason": None,
            "cache_split_prefill": False,
            "cache_split_prefill_reason": None,
            "cache_build_deduplicated": False,
            "cache_build_dedup_reason": None,
        }
        prepare_t0 = time.perf_counter()
        if (
            not metadata.get("cache_candidate")
            or match_tokens <= 0
            or len(tokens) <= 1
        ):
            cache_info["cache_prepare_ms"] = 1e3 * (time.perf_counter() - prepare_t0)
            return metadata["_prompt"], None, cache_info

        cache_prefix_tokens = min(match_tokens, len(tokens) - 1)
        prefix_tokens = tokens[:cache_prefix_tokens]
        rest_tokens = tokens[cache_prefix_tokens:]
        exact_match_trimmed = match_tokens >= len(tokens)
        scope = self.cache_scope(metadata)
        scope_hash = hashlib.blake2b(
            json.dumps(scope, sort_keys=True, separators=(",", ":")).encode("utf-8"),
            digest_size=16,
        ).hexdigest()
        key = PrefixKVCacheStore.key_for_tokens(prefix_tokens, scope=scope)

        if self.prefix_cache_population_mode == "async":
            entry = self.prefix_kv_cache.get(key)
            if entry is not None and entry["scope"] == scope:
                request_cache = copy.deepcopy(entry["prompt_cache"])
                cache_info.update(
                    {
                        "cache_reuse_enabled": True,
                        "cache_hit": True,
                        "cache_prepare_ms": 1e3
                        * (time.perf_counter() - prepare_t0),
                        "cache_scope_hash": scope_hash,
                        "cached_prefix_tokens": cache_prefix_tokens,
                        "actual_prefill_tokens": len(rest_tokens),
                        "cache_exact_match_trimmed": exact_match_trimmed,
                    }
                )
                return rest_tokens, request_cache, cache_info

            with self.prefix_cache_build_lock:
                cache_info["cache_pending"] = key in self.prefix_cache_pending_builds
                if cache_info["cache_pending"]:
                    self.prefix_cache_pending_build_deduplications += 1
            if not cache_info["cache_pending"]:
                cache_info["cache_scheduled"] = True
                cache_info["_async_cache_build"] = {
                    "key": key,
                    "prefix_tokens": prefix_tokens,
                    "scope": scope,
                    "prefill_step_size": metadata["prefill_step_size"],
                }
            else:
                cache_info["cache_build_deduplicated"] = True
                cache_info["cache_build_dedup_reason"] = "pending_async_build"
            cache_info["cache_prepare_ms"] = 1e3 * (
                time.perf_counter() - prepare_t0
            )
            cache_info["cache_scope_hash"] = scope_hash
            return metadata["_prompt"], None, cache_info

        if self.prefix_cache_population_mode == "request":
            entry = self.prefix_kv_cache.get(key)
            if entry is not None and entry["scope"] == scope:
                request_cache = copy.deepcopy(entry["prompt_cache"])
                cache_info.update(
                    {
                        "cache_reuse_enabled": True,
                        "cache_hit": True,
                        "cache_prepare_ms": 1e3
                        * (time.perf_counter() - prepare_t0),
                        "cache_scope_hash": scope_hash,
                        "cached_prefix_tokens": cache_prefix_tokens,
                        "actual_prefill_tokens": len(rest_tokens),
                        "cache_exact_match_trimmed": exact_match_trimmed,
                    }
                )
                return rest_tokens, request_cache, cache_info

            prompt_cache = self.make_prompt_cache(self.model)
            if not self.can_trim_prompt_cache(prompt_cache):
                self.execution_lock.acquire_foreground()
                try:
                    entry = self.build_prefix_cache_locked(
                        key=key,
                        prefix_tokens=prefix_tokens,
                        scope=scope,
                        prefill_step_size=metadata["prefill_step_size"],
                    )
                finally:
                    self.execution_lock.release()
                request_cache = copy.deepcopy(entry["prompt_cache"])
                cache_info.update(
                    {
                        "cache_reuse_enabled": True,
                        "cache_created": True,
                        "cache_prepare_ms": 1e3
                        * (time.perf_counter() - prepare_t0),
                        "cache_scope_hash": scope_hash,
                        "cached_prefix_tokens": cache_prefix_tokens,
                        "actual_prefill_tokens": len(rest_tokens),
                        "cache_exact_match_trimmed": exact_match_trimmed,
                        "cache_split_prefill": True,
                        "cache_split_prefill_reason": (
                            "non_trimmable_request_cache"
                        ),
                        "cache_request_store_reason": "split_prefill",
                    }
                )
                return rest_tokens, request_cache, cache_info

            cache_info.update(
                {
                    "cache_prepare_ms": 1e3 * (time.perf_counter() - prepare_t0),
                    "cache_scope_hash": scope_hash,
                    "cached_prefix_tokens": cache_prefix_tokens,
                    "_request_cache_store": {
                        "key": key,
                        "prefix_tokens": prefix_tokens,
                        "scope": scope,
                        "suffix_tokens": len(rest_tokens),
                        "prefill_step_size": metadata["prefill_step_size"],
                    },
                }
            )
            return metadata["_prompt"], None, cache_info

        entry = self.prefix_kv_cache.get(key)
        if entry is not None and entry["scope"] != scope:
            entry = None
        if entry is None:
            if self.prefix_cache_population_mode == "off":
                cache_info.update(
                    {
                        "cache_prepare_ms": 1e3 * (time.perf_counter() - prepare_t0),
                        "cache_scope_hash": scope_hash,
                        "cache_pending": False,
                    }
                )
                return metadata["_prompt"], None, cache_info
            self.execution_lock.acquire_foreground()
            try:
                entry = self.build_prefix_cache_locked(
                    key=key,
                    prefix_tokens=prefix_tokens,
                    scope=scope,
                    prefill_step_size=metadata["prefill_step_size"],
                )
            finally:
                self.execution_lock.release()
            cache_info["cache_created"] = True

        request_cache = copy.deepcopy(entry["prompt_cache"])

        cache_info.update(
            {
                "cache_reuse_enabled": True,
                "cache_hit": not cache_info["cache_created"],
                "cache_prepare_ms": 1e3 * (time.perf_counter() - prepare_t0),
                "cache_scope_hash": scope_hash,
                "cached_prefix_tokens": cache_prefix_tokens,
                "actual_prefill_tokens": len(rest_tokens),
                "cache_exact_match_trimmed": exact_match_trimmed,
            }
        )
        return rest_tokens, request_cache, cache_info

    def _run(
        self,
        *,
        prompt,
        max_tokens: int,
        prefill_step_size: int | None,
        stop: StopValue | None = None,
        request_id: str | None = None,
        prompt_cache=None,
    ):
        kwargs = {"max_tokens": max_tokens}
        if prefill_step_size is not None:
            kwargs["prefill_step_size"] = prefill_step_size
        owned_prompt_cache = prompt_cache is None
        if owned_prompt_cache:
            prompt_cache = self.make_prompt_cache(self.model)
        if prompt_cache is not None:
            kwargs["prompt_cache"] = prompt_cache
        progress = PromptProgressRecorder()
        if self.backend == "text":

            def progress_callback(processed_tokens: int, total_tokens: int) -> None:
                if request_id is not None:
                    self.request_registry.update(
                        request_id,
                        status="prefill",
                        prompt_progress_processed_tokens=int(processed_tokens),
                        prompt_progress_total_tokens=int(total_tokens),
                    )
                    self.request_registry.check_cancelled(request_id)
                progress.callback(processed_tokens, total_tokens)

            kwargs["prompt_progress_callback"] = progress_callback

        run_t0 = time.perf_counter()
        result = None
        text_parts = []
        generated_token_ids = []
        stop_sequences = normalize_stop(stop)
        forced_stop_reason = None
        engine_lock_wait_ms = self.execution_lock.acquire_foreground()
        try:
            if request_id is not None:
                self.request_registry.update(
                    request_id,
                    status="generating",
                    engine_lock_wait_ms=engine_lock_wait_ms,
                )
            for response in self.stream_generate(
                self.model, self.tokenizer, prompt, **kwargs
            ):
                if request_id is not None:
                    self.request_registry.check_cancelled(request_id)
                result = response
                generated_token_ids.append(int(response.token))
                if response.text:
                    candidate = "".join(text_parts) + response.text
                    trimmed, stop_met = trim_at_stop(candidate, stop_sequences)
                    if stop_met:
                        text_parts = [trimmed]
                        forced_stop_reason = "stop"
                        break
                    text_parts.append(response.text)
        finally:
            self.execution_lock.release()
        run_ms = 1e3 * (time.perf_counter() - run_t0)
        if result is None:
            raise RuntimeError("No generation response returned")
        stop_reason = getattr(result, "finish_reason", None) or getattr(
            result, "stop_reason", None
        )
        return {
            "text": "".join(text_parts),
            "run_ms": run_ms,
            "engine_lock_wait_ms": engine_lock_wait_ms,
            "prompt_tokens": int(result.prompt_tokens),
            "generation_tokens": int(result.generation_tokens),
            "prompt_tps": float(result.prompt_tps),
            "generation_tps": float(result.generation_tps),
            "peak_memory_gb": float(result.peak_memory),
            "stop_reason": forced_stop_reason or stop_reason or "max_tokens_or_eos",
            "generated_token_count_recorded": len(generated_token_ids),
            "_generated_token_ids": generated_token_ids,
            "_prompt_cache": prompt_cache,
            "_owned_prompt_cache": owned_prompt_cache,
            **progress.snapshot(),
        }

    def _stream_run(
        self,
        *,
        prompt,
        max_tokens: int,
        prefill_step_size: int | None,
        stop: StopValue | None = None,
        metadata: dict[str, Any],
        prompt_cache=None,
        cache_info: dict[str, Any] | None = None,
        full_prompt_tokens: int | None = None,
        prompt_tokens_for_generated_cache: list[int] | None = None,
        prompt_text_for_generated_cache: str | None = None,
        request_t0: float | None = None,
    ):
        kwargs = {"max_tokens": max_tokens}
        if prefill_step_size is not None:
            kwargs["prefill_step_size"] = prefill_step_size
        if prompt_cache is not None:
            kwargs["prompt_cache"] = prompt_cache
        progress = PromptProgressRecorder()
        if self.backend == "text":

            def progress_callback(processed_tokens: int, total_tokens: int) -> None:
                self.request_registry.update(
                    metadata["request_id"],
                    status="prefill",
                    prompt_progress_processed_tokens=int(processed_tokens),
                    prompt_progress_total_tokens=int(total_tokens),
                )
                self.request_registry.check_cancelled(metadata["request_id"])
                progress.callback(processed_tokens, total_tokens)

            kwargs["prompt_progress_callback"] = progress_callback
        cache_info = cache_info or {
            "cache_reuse_enabled": False,
            "cache_hit": False,
            "cache_created": False,
            "cache_prepare_ms": 0.0,
            "cache_scope_hash": None,
            "cached_prefix_tokens": 0,
            "actual_prefill_tokens": None,
            "cache_exact_match_trimmed": False,
        }

        run_t0 = time.perf_counter()
        result = None
        text_parts = []
        first_token_ms = None
        last_token_t = None
        token_gap_ms = []
        token_events = 0
        stop_sequences = normalize_stop(stop)
        forced_stop_reason = None
        engine_lock_wait_ms = self.execution_lock.acquire_foreground()
        try:
            self.request_registry.update(
                metadata["request_id"],
                status="generating",
                engine_lock_wait_ms=engine_lock_wait_ms,
            )
            for response in self.stream_generate(
                self.model, self.tokenizer, prompt, **kwargs
            ):
                self.request_registry.check_cancelled(metadata["request_id"])
                result = response
                if response.text:
                    token_t = time.perf_counter()
                    if first_token_ms is None:
                        first_token_ms = 1e3 * (token_t - run_t0)
                    if last_token_t is not None:
                        token_gap_ms.append(1e3 * (token_t - last_token_t))
                    last_token_t = token_t
                    token_events += 1
                    candidate = "".join(text_parts) + response.text
                    trimmed, stop_met = trim_at_stop(candidate, stop_sequences)
                    if stop_met:
                        text_to_emit = trimmed[len("".join(text_parts)) :]
                        text_parts = [trimmed]
                        forced_stop_reason = "stop"
                        if text_to_emit:
                            yield {
                                "type": "token",
                                "request_id": metadata["request_id"],
                                "created": metadata["created"],
                                "text": text_to_emit,
                            }
                        break
                    text_parts.append(response.text)
                    yield {
                        "type": "token",
                        "request_id": metadata["request_id"],
                        "created": metadata["created"],
                        "text": response.text,
                    }
        finally:
            self.execution_lock.release()

        run_ms = 1e3 * (time.perf_counter() - run_t0)
        if result is None:
            raise RuntimeError("No generation response returned")
        stop_reason = getattr(result, "finish_reason", None) or getattr(
            result, "stop_reason", None
        )
        actual_prefill_tokens = int(result.prompt_tokens)
        row = {
            **metadata,
            **cache_info,
            "text": "".join(text_parts),
            "run_ms": run_ms,
            "engine_lock_wait_ms": engine_lock_wait_ms,
            "prompt_tokens": (
                int(full_prompt_tokens)
                if full_prompt_tokens is not None
                else actual_prefill_tokens
            ),
            "actual_prefill_tokens": actual_prefill_tokens,
            "generation_tokens": int(result.generation_tokens),
            "prompt_tps": float(result.prompt_tps),
            "generation_tps": float(result.generation_tps),
            "peak_memory_gb": float(result.peak_memory),
            "stop_reason": forced_stop_reason or stop_reason or "max_tokens_or_eos",
            "stream_first_token_ms": first_token_ms,
            "stream_mean_token_gap_ms": (
                sum(token_gap_ms) / len(token_gap_ms) if token_gap_ms else None
            ),
            "stream_token_events": token_events,
            "service_request_ms": (
                1e3 * (time.perf_counter() - request_t0)
                if request_t0 is not None
                else None
            ),
            **progress.snapshot(),
        }
        row = self.schedule_deferred_prefix_cache_build(row)
        row.update(self.maybe_apply_memory_pressure_policy(reason="stream_request"))
        self.metrics.record_success(row)
        yield {"type": "final", **row}

    def _stream_run_live_jsonl(
        self,
        *,
        prompt,
        max_tokens: int,
        prefill_step_size: int | None,
        stop: StopValue | None = None,
        metadata: dict[str, Any],
        prompt_cache=None,
        cache_info: dict[str, Any] | None = None,
        full_prompt_tokens: int | None = None,
        prompt_tokens_for_generated_cache: list[int] | None = None,
        prompt_text_for_generated_cache: str | None = None,
        request_t0: float | None = None,
    ):
        event_queue: queue.Queue[dict[str, Any]] = queue.Queue()
        cache_info = cache_info or {
            "cache_reuse_enabled": False,
            "cache_hit": False,
            "cache_created": False,
            "cache_prepare_ms": 0.0,
            "cache_scope_hash": None,
            "cached_prefix_tokens": 0,
            "actual_prefill_tokens": None,
            "cache_exact_match_trimmed": False,
        }

        def worker() -> None:
            kwargs = {"max_tokens": max_tokens}
            if prefill_step_size is not None:
                kwargs["prefill_step_size"] = prefill_step_size
            worker_prompt_cache = prompt_cache
            owned_prompt_cache = worker_prompt_cache is None
            if owned_prompt_cache:
                worker_prompt_cache = self.make_prompt_cache(self.model)
            if worker_prompt_cache is not None:
                kwargs["prompt_cache"] = worker_prompt_cache

            progress = PromptProgressRecorder()
            if self.backend == "text":

                def live_progress_callback(
                    processed_tokens: int, total_tokens: int
                ) -> None:
                    event = progress.callback(processed_tokens, total_tokens)
                    self.request_registry.update(
                        metadata["request_id"],
                        status="prefill",
                        prompt_progress_processed_tokens=event["processed_tokens"],
                        prompt_progress_total_tokens=event["total_tokens"],
                    )
                    event_queue.put(
                        {
                            "type": "prompt_progress",
                            "request_id": metadata["request_id"],
                            "created": metadata["created"],
                            "processed_tokens": event["processed_tokens"],
                            "total_tokens": event["total_tokens"],
                            "elapsed_ms": event["elapsed_ms"],
                            "complete": (
                                event["processed_tokens"] == event["total_tokens"]
                            ),
                        }
                    )
                    self.request_registry.check_cancelled(metadata["request_id"])

                kwargs["prompt_progress_callback"] = live_progress_callback

            run_t0 = time.perf_counter()
            result = None
            text_parts = []
            generated_token_ids = []
            first_token_ms = None
            last_token_t = None
            token_gap_ms = []
            token_events = 0
            stop_sequences = normalize_stop(stop)
            forced_stop_reason = None
            engine_lock_wait_ms = self.execution_lock.acquire_foreground()
            try:
                self.request_registry.update(
                    metadata["request_id"],
                    status="generating",
                    engine_lock_wait_ms=engine_lock_wait_ms,
                )
                for response in self.stream_generate(
                    self.model, self.tokenizer, prompt, **kwargs
                ):
                    self.request_registry.check_cancelled(metadata["request_id"])
                    result = response
                    generated_token_ids.append(int(response.token))
                    if response.text:
                        token_t = time.perf_counter()
                        if first_token_ms is None:
                            first_token_ms = 1e3 * (token_t - run_t0)
                        if last_token_t is not None:
                            token_gap_ms.append(1e3 * (token_t - last_token_t))
                        last_token_t = token_t
                        token_events += 1
                        candidate = "".join(text_parts) + response.text
                        trimmed, stop_met = trim_at_stop(candidate, stop_sequences)
                        if stop_met:
                            text_to_emit = trimmed[len("".join(text_parts)) :]
                            text_parts = [trimmed]
                            forced_stop_reason = "stop"
                            if text_to_emit:
                                event_queue.put(
                                    {
                                        "type": "token",
                                        "request_id": metadata["request_id"],
                                        "created": metadata["created"],
                                        "text": text_to_emit,
                                    }
                                )
                            break
                        text_parts.append(response.text)
                        event_queue.put(
                            {
                                "type": "token",
                                "request_id": metadata["request_id"],
                                "created": metadata["created"],
                                "text": response.text,
                            }
                        )
            except RequestCancelled as exc:
                event_queue.put(
                    {
                        "type": "cancelled",
                        "request_id": metadata["request_id"],
                        "created": metadata["created"],
                        "reason": str(exc),
                        **progress.snapshot(),
                    }
                )
                return
            except Exception as exc:
                event_queue.put(
                    {
                        "type": "error",
                        "request_id": metadata["request_id"],
                        "created": metadata["created"],
                        "error": str(exc),
                    }
                )
                return
            finally:
                self.execution_lock.release()

            run_ms = 1e3 * (time.perf_counter() - run_t0)
            if result is None:
                event_queue.put(
                    {
                        "type": "error",
                        "request_id": metadata["request_id"],
                        "created": metadata["created"],
                        "error": "No generation response returned",
                    }
                )
                return
            stop_reason = getattr(result, "finish_reason", None) or getattr(
                result, "stop_reason", None
            )
            actual_prefill_tokens = int(result.prompt_tokens)
            request_cache_info = self.store_request_prefix_cache(
                cache_info=cache_info,
                prompt_cache=worker_prompt_cache,
                generated_token_count=len(generated_token_ids),
            )
            row = {
                **metadata,
                **cache_info,
                **request_cache_info,
                "text": "".join(text_parts),
                "run_ms": run_ms,
                "engine_lock_wait_ms": engine_lock_wait_ms,
                "prompt_tokens": (
                    int(full_prompt_tokens)
                    if full_prompt_tokens is not None
                    else actual_prefill_tokens
                ),
                "actual_prefill_tokens": actual_prefill_tokens,
                "generation_tokens": int(result.generation_tokens),
                "prompt_tps": float(result.prompt_tps),
                "generation_tps": float(result.generation_tps),
                "peak_memory_gb": float(result.peak_memory),
                "stop_reason": forced_stop_reason or stop_reason or "max_tokens_or_eos",
                "generated_token_count_recorded": len(generated_token_ids),
                "stream_first_token_ms": first_token_ms,
                "stream_mean_token_gap_ms": (
                    sum(token_gap_ms) / len(token_gap_ms) if token_gap_ms else None
                ),
                "stream_token_events": token_events,
                "service_request_ms": (
                    1e3 * (time.perf_counter() - request_t0)
                    if request_t0 is not None
                    else None
                ),
                **progress.snapshot(),
            }
            try:
                generated_metadata = dict(metadata)
                if prompt_tokens_for_generated_cache is not None:
                    generated_metadata["_prompt_tokens"] = prompt_tokens_for_generated_cache
                if prompt_text_for_generated_cache is not None:
                    generated_metadata["_prompt"] = prompt_text_for_generated_cache
                full_generated_tokens, generated_cache_info = self.record_generated_prefix_prompt(
                    metadata=generated_metadata,
                    text=row["text"],
                    generated_token_ids=generated_token_ids,
                )
                row.update(generated_cache_info)
                if full_generated_tokens is not None:
                    row.update(
                        self.store_generated_prefix_cache(
                            metadata=generated_metadata,
                            full_tokens=full_generated_tokens,
                            prompt_cache=worker_prompt_cache,
                        )
                    )
            except Exception as exc:
                event_queue.put(
                    {
                        "type": "error",
                        "request_id": metadata["request_id"],
                        "created": metadata["created"],
                        "error": f"generated prefix cache recording failed: {exc}",
                    }
                )
                return
            row = self.schedule_deferred_prefix_cache_build(row)
            row.update(self.maybe_apply_memory_pressure_policy(reason="stream_request"))
            self.metrics.record_success(row)
            event_queue.put({"type": "final", **row})

        thread = threading.Thread(
            target=worker,
            name=f"stream-jsonl-{metadata['request_id']}",
            daemon=True,
        )
        thread.start()
        while True:
            event = event_queue.get()
            yield event
            if event["type"] in {"final", "error", "cancelled"}:
                break
        thread.join(timeout=1)

    def warmup_targets(self) -> list[dict[str, Any]]:
        targets: list[dict[str, Any]] = []
        seen_prompt_tokens: set[int] = set()
        seen_profile_steps: set[str] = set()

        for prompt_tokens in self.warmup_prompt_tokens:
            if prompt_tokens in seen_prompt_tokens:
                continue
            seen_prompt_tokens.add(prompt_tokens)
            targets.append(
                {
                    "prompt_tokens": prompt_tokens,
                    "source": "configured",
                }
            )

        if not self.warmup_profile_prefill:
            return targets

        for band in sorted(
            self.profile.get("prompt_token_bands") or [],
            key=lambda item: int(item.get("max_prompt_tokens") or 0),
        ):
            prompt_tokens = int(band.get("max_prompt_tokens") or 0)
            if prompt_tokens <= 0:
                continue
            step_size = (
                (band.get("policy") or {})
                .get("throughput_default", {})
                .get("prefill_step_size")
            )
            step_key = "default" if step_size is None else str(step_size)
            if step_key in seen_profile_steps:
                continue
            seen_profile_steps.add(step_key)
            if prompt_tokens in seen_prompt_tokens:
                continue
            seen_prompt_tokens.add(prompt_tokens)
            targets.append(
                {
                    "prompt_tokens": prompt_tokens,
                    "source": "profile_band",
                    "band_min_prompt_tokens": band.get("min_prompt_tokens"),
                    "band_max_prompt_tokens": band.get("max_prompt_tokens"),
                }
            )

        return targets

    def _warmup(self):
        results = []
        tokenizer = self.tokenizer.tokenizer if hasattr(self.tokenizer, "tokenizer") else self.tokenizer
        for target in self.warmup_targets():
            prompt_tokens = int(target["prompt_tokens"])
            prefill_step_size, prefill_selection = self.selected_prefill_policy(
                "throughput_default",
                prompt_tokens=prompt_tokens,
            )
            token_prompt = build_token_prompt(tokenizer, prompt_tokens)
            row = self._run(
                prompt=token_prompt,
                max_tokens=1,
                prefill_step_size=prefill_step_size,
            )
            row.pop("_generated_token_ids", None)
            row.pop("_prompt_cache", None)
            row.pop("_owned_prompt_cache", None)
            row["warmup_prompt_tokens"] = prompt_tokens
            row["warmup_source"] = target["source"]
            row["prefill_step_size"] = prefill_step_size
            row["prefill_selection_source"] = prefill_selection["source"]
            row["prefill_band_min_prompt_tokens"] = (
                prefill_selection["band_min_prompt_tokens"]
            )
            row["prefill_band_max_prompt_tokens"] = (
                prefill_selection["band_max_prompt_tokens"]
            )
            results.append(row)
        return results

    def _run_warmup(self) -> None:
        with self.warmup_lock:
            self.warmup_started_at = time.time()
            self.warmup_completed_at = None
            self.warmup_error = None
        warmup_t0 = time.perf_counter()
        try:
            results = self._warmup() if self.warmup_prompt_tokens else []
            elapsed_ms = 1e3 * (time.perf_counter() - warmup_t0)
            with self.warmup_lock:
                self.warmup_results = results
                self.warmup_completed_at = time.time()
                self.warmup_error = None
            self.startup_timings["warmup_ms"] = elapsed_ms
        except Exception as exc:
            elapsed_ms = 1e3 * (time.perf_counter() - warmup_t0)
            with self.warmup_lock:
                self.warmup_completed_at = time.time()
                self.warmup_error = str(exc)
            self.startup_timings["warmup_ms"] = elapsed_ms
            if self.warmup_mode == "sync":
                raise

    def warmup_snapshot(self) -> dict[str, Any]:
        with self.warmup_lock:
            running = (
                self.warmup_started_at is not None
                and self.warmup_completed_at is None
                and self.warmup_error is None
            )
            completed = self.warmup_completed_at is not None and self.warmup_error is None
            return {
                "mode": self.warmup_mode,
                "profile_prefill": self.warmup_profile_prefill,
                "running": running,
                "completed": completed,
                "error": self.warmup_error,
                "started_at": self.warmup_started_at,
                "completed_at": self.warmup_completed_at,
                "result_count": len(self.warmup_results),
                "targets": self.warmup_targets(),
            }

    def health(self):
        startup_timings = dict(self.startup_timings)
        parent_started_at = startup_timings.get("parent_started_at_epoch")
        if isinstance(parent_started_at, int | float):
            startup_timings["parent_start_to_health_response_ms"] = (
                1e3 * (time.time() - parent_started_at)
            )
        return {
            "ok": True,
            "model": self.model_path,
            "backend": self.backend,
            "device": self.device_info,
            "load_ms": self.load_ms,
            "load_strict": self.load_strict,
            "load_fallback_reason": self.load_fallback_reason,
            "startup_timings": startup_timings,
            "uptime_s": time.time() - self.started_at,
            "warmup_prompt_tokens": self.warmup_prompt_tokens,
            "warmup_profile_prefill": self.warmup_profile_prefill,
            "warmup_results": self.warmup_results,
            "warmup": self.warmup_snapshot(),
            "profile_path": str(self.profile_path) if self.profile_path else None,
            "engine_preset": self.engine_preset,
            "metrics": self.metrics.snapshot(),
            "prefix_kv_cache": self.prefix_kv_cache.snapshot(),
            "prefix_cache_policy": self.prefix_cache_policy_snapshot(),
            "prompt_cache_capabilities": self.prompt_cache_capabilities_snapshot(),
            "execution_lock": self.execution_lock.snapshot(),
            "scheduler": self.scheduler.snapshot(),
            "mlx_memory": self.mlx_memory_snapshot(),
            "requests": self.request_registry.snapshot(),
        }

    def metadata(self):
        return {
            "model": self.model_path,
            "backend": self.backend,
            "profile_path": str(self.profile_path) if self.profile_path else None,
            "engine_preset": self.engine_preset,
            "profile_loaded": bool(self.profile),
            "policy_names": sorted(self.profile.get("policy", {}).keys()),
            "device": self.device_info,
            "load_ms": self.load_ms,
            "load_strict": self.load_strict,
            "load_fallback_reason": self.load_fallback_reason,
            "started_at": self.started_at,
            "uptime_s": time.time() - self.started_at,
            "warmup_prompt_tokens": self.warmup_prompt_tokens,
            "warmup_profile_prefill": self.warmup_profile_prefill,
            "warmup_results": self.warmup_results,
            "warmup": self.warmup_snapshot(),
            "metrics": self.metrics.snapshot(),
            "prefix_kv_cache": self.prefix_kv_cache.snapshot(),
            "prefix_cache_policy": self.prefix_cache_policy_snapshot(),
            "prompt_cache_capabilities": self.prompt_cache_capabilities_snapshot(),
            "execution_lock": self.execution_lock.snapshot(),
            "scheduler": self.scheduler.snapshot(),
            "mlx_memory": self.mlx_memory_snapshot(),
            "requests": self.request_registry.snapshot(),
        }

    def requests_snapshot(self) -> dict[str, Any]:
        return self.request_registry.snapshot()

    def cancel_request(self, request_id: str) -> dict[str, Any]:
        return self.request_registry.cancel(request_id)

    def execution_lock_priority_probe(self, *, timeout_ms: int) -> dict[str, Any]:
        order = []
        errors = []
        before = self.execution_lock.snapshot()
        probe_started = time.perf_counter()

        self.execution_lock.acquire_foreground()
        try:
            background_ready = threading.Event()
            foreground_ready = threading.Event()

            def background_probe() -> None:
                try:
                    background_ready.set()
                    wait_ms, deferrals = self.execution_lock.acquire_background()
                    try:
                        order.append(
                            {
                                "kind": "background",
                                "wait_ms": wait_ms,
                                "deferrals": deferrals,
                            }
                        )
                    finally:
                        self.execution_lock.release()
                except Exception as exc:
                    errors.append(f"background: {exc}")

            def foreground_probe() -> None:
                try:
                    foreground_ready.set()
                    wait_ms = self.execution_lock.acquire_foreground()
                    try:
                        order.append({"kind": "foreground", "wait_ms": wait_ms})
                    finally:
                        self.execution_lock.release()
                except Exception as exc:
                    errors.append(f"foreground: {exc}")

            background = threading.Thread(
                target=background_probe,
                name="execution-lock-priority-background-probe",
                daemon=True,
            )
            foreground = threading.Thread(
                target=foreground_probe,
                name="execution-lock-priority-foreground-probe",
                daemon=True,
            )
            background.start()
            if not background_ready.wait(timeout=timeout_ms / 1000):
                raise RuntimeError("background probe did not start")

            deadline = time.perf_counter() + timeout_ms / 1000
            while self.execution_lock.snapshot()["background_waiters"] < 1:
                if time.perf_counter() > deadline:
                    raise RuntimeError("background probe did not wait on lock")
                time.sleep(0.001)

            foreground.start()
            if not foreground_ready.wait(timeout=timeout_ms / 1000):
                raise RuntimeError("foreground probe did not start")

            deadline = time.perf_counter() + timeout_ms / 1000
            while self.execution_lock.snapshot()["foreground_waiters"] < 1:
                if time.perf_counter() > deadline:
                    raise RuntimeError("foreground probe did not wait on lock")
                time.sleep(0.001)
        finally:
            self.execution_lock.release()

        background.join(timeout=timeout_ms / 1000)
        foreground.join(timeout=timeout_ms / 1000)
        after = self.execution_lock.snapshot()
        elapsed_ms = 1e3 * (time.perf_counter() - probe_started)
        ordered_kinds = [entry["kind"] for entry in order]
        return {
            "ok": (
                not errors
                and ordered_kinds == ["foreground", "background"]
                and after["background_priority_deferrals"]
                > before["background_priority_deferrals"]
            ),
            "order": order,
            "errors": errors,
            "elapsed_ms": elapsed_ms,
            "before": before,
            "after": after,
            "background_priority_deferrals_delta": (
                after["background_priority_deferrals"]
                - before["background_priority_deferrals"]
            ),
        }

    def generate(self, request: GenerateRequest):
        request_t0 = time.perf_counter()
        with self.scheduler.admit() as admission:
            metadata = self.request_metadata(
                prompt=request.prompt,
                policy=request.policy,
                prefill_step_size_override=request.prefill_step_size,
            )
            run_prompt, prompt_cache, cache_info = self.prepare_prefix_cache_reuse(
                metadata=metadata,
            )
            self.request_registry.begin(
                request_id=metadata["request_id"],
                route="/generate",
                prompt_tokens=metadata["prompt_tokens_estimate"],
                policy=metadata["effective_policy"],
                prefill_step_size=metadata["prefill_step_size"],
            )
            try:
                row = self._run(
                    prompt=run_prompt,
                    max_tokens=request.max_tokens,
                    prefill_step_size=metadata["prefill_step_size"],
                    stop=request.stop,
                    request_id=metadata["request_id"],
                    prompt_cache=prompt_cache,
                )
                actual_prefill_tokens = row["prompt_tokens"]
                generated_token_ids = row.pop("_generated_token_ids", [])
                row_prompt_cache = row.pop("_prompt_cache", None)
                row.pop("_owned_prompt_cache", None)
                request_cache_info = self.store_request_prefix_cache(
                    cache_info=cache_info,
                    prompt_cache=row_prompt_cache,
                    generated_token_count=len(generated_token_ids),
                )
                row.update(self.public_metadata(metadata))
                row.update(cache_info)
                row.update(request_cache_info)
                row.update(admission)
                row["actual_prefill_tokens"] = actual_prefill_tokens
                row["prompt_tokens"] = metadata["prompt_tokens_estimate"]
                row["service_request_ms"] = 1e3 * (time.perf_counter() - request_t0)
                self.record_prefix_prompt(metadata)
                full_generated_tokens, generated_cache_info = self.record_generated_prefix_prompt(
                    metadata=metadata,
                    text=row["text"],
                    generated_token_ids=generated_token_ids,
                )
                row.update(generated_cache_info)
                if full_generated_tokens is not None:
                    row.update(
                        self.store_generated_prefix_cache(
                            metadata=metadata,
                            full_tokens=full_generated_tokens,
                            prompt_cache=row_prompt_cache,
                        )
                    )
                row = self.schedule_deferred_prefix_cache_build(row)
                row.update(self.maybe_apply_memory_pressure_policy(reason="request"))
                self.metrics.record_success(row)
                self.request_registry.finish(
                    metadata["request_id"],
                    status="completed",
                    service_request_ms=row["service_request_ms"],
                    generation_tokens=row["generation_tokens"],
                )
                return row
            except RequestCancelled:
                self.request_registry.finish(
                    metadata["request_id"],
                    status="cancelled",
                    service_request_ms=1e3 * (time.perf_counter() - request_t0),
                )
                raise

    def stream_generate_jsonl(self, request: GenerateRequest):
        request_t0 = time.perf_counter()
        with self.scheduler.admit() as admission:
            metadata = self.request_metadata(
                prompt=request.prompt,
                policy=request.policy,
                prefill_step_size_override=request.prefill_step_size,
            )
            run_prompt, prompt_cache, cache_info = self.prepare_prefix_cache_reuse(
                metadata=metadata,
            )
            cache_info.update(admission)
            self.request_registry.begin(
                request_id=metadata["request_id"],
                route="/generate:stream",
                prompt_tokens=metadata["prompt_tokens_estimate"],
                policy=metadata["effective_policy"],
                prefill_step_size=metadata["prefill_step_size"],
            )
            for event in self._stream_run_live_jsonl(
                prompt=run_prompt,
                max_tokens=request.max_tokens,
                prefill_step_size=metadata["prefill_step_size"],
                stop=request.stop,
                metadata=self.public_metadata(metadata),
                prompt_cache=prompt_cache,
                cache_info=cache_info,
                full_prompt_tokens=metadata["prompt_tokens_estimate"],
                prompt_tokens_for_generated_cache=metadata["_prompt_tokens"],
                prompt_text_for_generated_cache=metadata["_prompt"],
                request_t0=request_t0,
            ):
                if event["type"] == "final":
                    self.record_prefix_prompt(metadata)
                    self.request_registry.finish(
                        metadata["request_id"],
                        status="completed",
                        service_request_ms=event.get("service_request_ms"),
                        generation_tokens=event.get("generation_tokens"),
                    )
                elif event["type"] == "cancelled":
                    self.request_registry.finish(
                        metadata["request_id"],
                        status="cancelled",
                        service_request_ms=1e3 * (time.perf_counter() - request_t0),
                        prompt_progress_events=event.get("prompt_progress_events"),
                    )
                elif event["type"] == "error":
                    self.request_registry.finish(
                        metadata["request_id"],
                        status="failed",
                        error=event.get("error"),
                        service_request_ms=1e3 * (time.perf_counter() - request_t0),
                    )
                yield json.dumps(event) + "\n"

    def render_chat_prompt(self, messages: list[Message]) -> str:
        rendered_messages = [message.model_dump() for message in messages]
        if hasattr(self.tokenizer, "apply_chat_template"):
            return self.tokenizer.apply_chat_template(
                rendered_messages,
                tokenize=False,
                add_generation_prompt=True,
            )
        tokenizer = self.tokenizer.tokenizer if hasattr(self.tokenizer, "tokenizer") else self.tokenizer
        if hasattr(tokenizer, "apply_chat_template"):
            return tokenizer.apply_chat_template(
                rendered_messages,
                tokenize=False,
                add_generation_prompt=True,
            )
        return (
            "\n".join(f"{message.role}: {message.content}" for message in messages)
            + "\nassistant:"
        )

    def openai_completion(self, request: CompletionRequest):
        row = self.generate(
            GenerateRequest(
                prompt=request.prompt,
                max_tokens=request.max_tokens,
                policy=request.policy,
                prefill_step_size=request.prefill_step_size,
                stream=request.stream,
                stop=request.stop,
            )
        )
        return {
            "id": f"cmpl-{row['request_id']}",
            "object": "text_completion",
            "created": row["created"],
            "model": request.model or self.model_path,
            "choices": [
                {
                    "text": row["text"],
                    "index": 0,
                    "finish_reason": row["stop_reason"],
                }
            ],
            "usage": {
                "prompt_tokens": row["prompt_tokens"],
                "completion_tokens": row["generation_tokens"],
                "total_tokens": row["prompt_tokens"] + row["generation_tokens"],
            },
            "engine_metrics": row,
        }

    def stream_openai_completion(self, request: CompletionRequest):
        request_t0 = time.perf_counter()
        with self.scheduler.admit() as admission:
            metadata = self.request_metadata(
                prompt=request.prompt,
                policy=request.policy,
                prefill_step_size_override=request.prefill_step_size,
            )
            run_prompt, prompt_cache, cache_info = self.prepare_prefix_cache_reuse(
                metadata=metadata,
            )
            cache_info.update(admission)
            self.request_registry.begin(
                request_id=metadata["request_id"],
                route="/v1/completions:stream",
                prompt_tokens=metadata["prompt_tokens_estimate"],
                policy=metadata["effective_policy"],
                prefill_step_size=metadata["prefill_step_size"],
            )
            for event in self._stream_run_live_jsonl(
                prompt=run_prompt,
                max_tokens=request.max_tokens,
                prefill_step_size=metadata["prefill_step_size"],
                stop=request.stop,
                metadata=self.public_metadata(metadata),
                prompt_cache=prompt_cache,
                cache_info=cache_info,
                full_prompt_tokens=metadata["prompt_tokens_estimate"],
                prompt_tokens_for_generated_cache=metadata["_prompt_tokens"],
                prompt_text_for_generated_cache=metadata["_prompt"],
                request_t0=request_t0,
            ):
                if event["type"] == "prompt_progress":
                    comment = {
                        "request_id": event["request_id"],
                        "processed_tokens": event["processed_tokens"],
                        "total_tokens": event["total_tokens"],
                        "complete": event["complete"],
                    }
                    yield f": prompt_progress {json.dumps(comment)}\n\n"
                elif event["type"] == "token":
                    chunk = {
                        "id": f"cmpl-{event['request_id']}",
                        "object": "text_completion.chunk",
                        "created": event["created"],
                        "model": request.model or self.model_path,
                        "choices": [
                            {
                                "text": event["text"],
                                "index": 0,
                                "finish_reason": None,
                            }
                        ],
                    }
                    yield f"data: {json.dumps(chunk)}\n\n"
                elif event["type"] == "final":
                    self.record_prefix_prompt(metadata)
                    self.request_registry.finish(
                        metadata["request_id"],
                        status="completed",
                        service_request_ms=event.get("service_request_ms"),
                        generation_tokens=event.get("generation_tokens"),
                    )
                    chunk = {
                        "id": f"cmpl-{event['request_id']}",
                        "object": "text_completion.chunk",
                        "created": event["created"],
                        "model": request.model or self.model_path,
                        "choices": [
                            {
                                "text": "",
                                "index": 0,
                                "finish_reason": event["stop_reason"],
                            }
                        ],
                        "usage": {
                            "prompt_tokens": event["prompt_tokens"],
                            "completion_tokens": event["generation_tokens"],
                            "total_tokens": event["prompt_tokens"] + event["generation_tokens"],
                        },
                        "engine_metrics": event,
                    }
                    yield f"data: {json.dumps(chunk)}\n\n"
                elif event["type"] == "cancelled":
                    self.request_registry.finish(
                        metadata["request_id"],
                        status="cancelled",
                        service_request_ms=1e3 * (time.perf_counter() - request_t0),
                        prompt_progress_events=event.get("prompt_progress_events"),
                    )
                    chunk = {
                        "id": f"cmpl-{event['request_id']}",
                        "object": "text_completion.chunk",
                        "created": event["created"],
                        "model": request.model or self.model_path,
                        "choices": [
                            {
                                "text": "",
                                "index": 0,
                                "finish_reason": "cancelled",
                            }
                        ],
                        "engine_metrics": event,
                    }
                    yield f"data: {json.dumps(chunk)}\n\n"
                elif event["type"] == "error":
                    self.request_registry.finish(
                        metadata["request_id"],
                        status="failed",
                        error=event.get("error"),
                        service_request_ms=1e3 * (time.perf_counter() - request_t0),
                    )
                    raise RuntimeError(event.get("error", "stream error"))
        yield "data: [DONE]\n\n"

    def openai_chat_completion(self, request: ChatCompletionRequest):
        if not request.messages:
            raise ValueError("messages must not be empty")
        prompt = self.render_chat_prompt(request.messages)
        row = self.generate(
            GenerateRequest(
                prompt=prompt,
                max_tokens=request.max_tokens,
                policy=request.policy,
                prefill_step_size=request.prefill_step_size,
                stream=request.stream,
                stop=request.stop,
            )
        )
        return {
            "id": f"chatcmpl-{row['request_id']}",
            "object": "chat.completion",
            "created": row["created"],
            "model": request.model or self.model_path,
            "choices": [
                {
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": row["text"],
                    },
                    "finish_reason": row["stop_reason"],
                }
            ],
            "usage": {
                "prompt_tokens": row["prompt_tokens"],
                "completion_tokens": row["generation_tokens"],
                "total_tokens": row["prompt_tokens"] + row["generation_tokens"],
            },
            "engine_metrics": row,
        }

    def stream_openai_chat_completion(self, request: ChatCompletionRequest):
        if not request.messages:
            raise ValueError("messages must not be empty")
        prompt = self.render_chat_prompt(request.messages)
        request_t0 = time.perf_counter()
        with self.scheduler.admit() as admission:
            metadata = self.request_metadata(
                prompt=prompt,
                policy=request.policy,
                prefill_step_size_override=request.prefill_step_size,
            )
            run_prompt, prompt_cache, cache_info = self.prepare_prefix_cache_reuse(
                metadata=metadata,
            )
            cache_info.update(admission)
            self.request_registry.begin(
                request_id=metadata["request_id"],
                route="/v1/chat/completions:stream",
                prompt_tokens=metadata["prompt_tokens_estimate"],
                policy=metadata["effective_policy"],
                prefill_step_size=metadata["prefill_step_size"],
            )
            for event in self._stream_run_live_jsonl(
                prompt=run_prompt,
                max_tokens=request.max_tokens,
                prefill_step_size=metadata["prefill_step_size"],
                stop=request.stop,
                metadata=self.public_metadata(metadata),
                prompt_cache=prompt_cache,
                cache_info=cache_info,
                full_prompt_tokens=metadata["prompt_tokens_estimate"],
                prompt_tokens_for_generated_cache=metadata["_prompt_tokens"],
                prompt_text_for_generated_cache=metadata["_prompt"],
                request_t0=request_t0,
            ):
                if event["type"] == "prompt_progress":
                    comment = {
                        "request_id": event["request_id"],
                        "processed_tokens": event["processed_tokens"],
                        "total_tokens": event["total_tokens"],
                        "complete": event["complete"],
                    }
                    yield f": prompt_progress {json.dumps(comment)}\n\n"
                elif event["type"] == "token":
                    chunk = {
                        "id": f"chatcmpl-{event['request_id']}",
                        "object": "chat.completion.chunk",
                        "created": event["created"],
                        "model": request.model or self.model_path,
                        "choices": [
                            {
                                "index": 0,
                                "delta": {"content": event["text"]},
                                "finish_reason": None,
                            }
                        ],
                    }
                    yield f"data: {json.dumps(chunk)}\n\n"
                elif event["type"] == "final":
                    self.record_prefix_prompt(metadata)
                    self.request_registry.finish(
                        metadata["request_id"],
                        status="completed",
                        service_request_ms=event.get("service_request_ms"),
                        generation_tokens=event.get("generation_tokens"),
                    )
                    chunk = {
                        "id": f"chatcmpl-{event['request_id']}",
                        "object": "chat.completion.chunk",
                        "created": event["created"],
                        "model": request.model or self.model_path,
                        "choices": [
                            {
                                "index": 0,
                                "delta": {},
                                "finish_reason": event["stop_reason"],
                            }
                        ],
                        "usage": {
                            "prompt_tokens": event["prompt_tokens"],
                            "completion_tokens": event["generation_tokens"],
                            "total_tokens": event["prompt_tokens"] + event["generation_tokens"],
                        },
                        "engine_metrics": event,
                    }
                    yield f"data: {json.dumps(chunk)}\n\n"
                elif event["type"] == "cancelled":
                    self.request_registry.finish(
                        metadata["request_id"],
                        status="cancelled",
                        service_request_ms=1e3 * (time.perf_counter() - request_t0),
                        prompt_progress_events=event.get("prompt_progress_events"),
                    )
                    chunk = {
                        "id": f"chatcmpl-{event['request_id']}",
                        "object": "chat.completion.chunk",
                        "created": event["created"],
                        "model": request.model or self.model_path,
                        "choices": [
                            {
                                "index": 0,
                                "delta": {},
                                "finish_reason": "cancelled",
                            }
                        ],
                        "engine_metrics": event,
                    }
                    yield f"data: {json.dumps(chunk)}\n\n"
                elif event["type"] == "error":
                    self.request_registry.finish(
                        metadata["request_id"],
                        status="failed",
                        error=event.get("error"),
                        service_request_ms=1e3 * (time.perf_counter() - request_t0),
                    )
                    raise RuntimeError(event.get("error", "stream error"))
        yield "data: [DONE]\n\n"


class EngineManager:
    def __init__(
        self,
        *,
        model_path: str,
        profile_path: Path | None,
        warmup_prompt_tokens: list[int],
        warmup_profile_prefill: bool,
        require_gpu: bool,
        max_concurrent_requests: int,
        max_queued_requests: int,
        queue_timeout_ms: int,
        engine_preset: EnginePresetName,
        prefix_cache_max_entries: int,
        prefix_cache_memory_limit_mb: float,
        prefix_cache_min_entries: int,
        prefix_cache_population_mode: str,
        prefix_cache_async_idle_timeout_ms: int,
        prefix_cache_async_idle_grace_ms: int,
        warmup_mode: WarmupMode,
        startup_context: dict[str, Any] | None = None,
    ):
        self.lock = threading.Lock()
        self.require_gpu = require_gpu
        self.warmup_prompt_tokens = warmup_prompt_tokens
        self.warmup_profile_prefill = warmup_profile_prefill
        self.warmup_mode = warmup_mode
        self.max_concurrent_requests = max_concurrent_requests
        self.max_queued_requests = max_queued_requests
        self.queue_timeout_ms = queue_timeout_ms
        self.engine_preset = engine_preset
        self.prefix_cache_max_entries = prefix_cache_max_entries
        self.prefix_cache_memory_limit_mb = prefix_cache_memory_limit_mb
        self.prefix_cache_min_entries = prefix_cache_min_entries
        self.prefix_cache_population_mode = prefix_cache_population_mode
        self.prefix_cache_async_idle_timeout_ms = prefix_cache_async_idle_timeout_ms
        self.prefix_cache_async_idle_grace_ms = prefix_cache_async_idle_grace_ms
        self.reload_count = 0
        self.unload_count = 0
        self.last_reload_error: str | None = None
        self.last_unloaded_at: float | None = None
        self.last_model_path = model_path
        self.last_profile_path = profile_path
        self.engine = ResidentEngine(
            model_path=model_path,
            profile_path=profile_path,
            warmup_prompt_tokens=warmup_prompt_tokens,
            warmup_profile_prefill=warmup_profile_prefill,
            require_gpu=require_gpu,
            max_concurrent_requests=max_concurrent_requests,
            max_queued_requests=max_queued_requests,
            queue_timeout_ms=queue_timeout_ms,
            engine_preset=engine_preset,
            prefix_cache_max_entries=prefix_cache_max_entries,
            prefix_cache_memory_limit_mb=prefix_cache_memory_limit_mb,
            prefix_cache_min_entries=prefix_cache_min_entries,
            prefix_cache_population_mode=prefix_cache_population_mode,
            prefix_cache_async_idle_timeout_ms=prefix_cache_async_idle_timeout_ms,
            prefix_cache_async_idle_grace_ms=prefix_cache_async_idle_grace_ms,
            warmup_mode=warmup_mode,
            startup_context=startup_context,
        )

    def current(self) -> ResidentEngine:
        if self.engine is None:
            raise RuntimeError("No model is loaded; call /engine/reload before inference")
        return self.engine

    def metadata(self):
        engine = self.engine
        if engine is None:
            return {
                "ok": True,
                "loaded": False,
                "model": self.last_model_path,
                "profile_path": str(self.last_profile_path) if self.last_profile_path else None,
                "reload_count": self.reload_count,
                "unload_count": self.unload_count,
                "last_reload_error": self.last_reload_error,
                "last_unloaded_at": self.last_unloaded_at,
                "warmup_prompt_tokens": self.warmup_prompt_tokens,
                "warmup_profile_prefill": self.warmup_profile_prefill,
                "warmup_mode": self.warmup_mode,
                "engine_preset": self.engine_preset,
                "scheduler_config": {
                    "max_concurrent_requests": self.max_concurrent_requests,
                    "max_queued_requests": self.max_queued_requests,
                    "queue_timeout_ms": self.queue_timeout_ms,
                },
                "prefix_cache_max_entries": self.prefix_cache_max_entries,
                "prefix_cache_memory_limit_mb": self.prefix_cache_memory_limit_mb,
                "prefix_cache_min_entries": self.prefix_cache_min_entries,
                "prefix_cache_population_mode": self.prefix_cache_population_mode,
                "prefix_cache_async_idle_timeout_ms": (
                    self.prefix_cache_async_idle_timeout_ms
                ),
                "prefix_cache_async_idle_grace_ms": (
                    self.prefix_cache_async_idle_grace_ms
                ),
            }
        return {
            "ok": True,
            "loaded": True,
            "reload_count": self.reload_count,
            "unload_count": self.unload_count,
            "last_reload_error": self.last_reload_error,
            "last_unloaded_at": self.last_unloaded_at,
            **engine.metadata(),
        }

    def planned_config_snapshot(self, config: dict[str, Any]) -> dict[str, Any]:
        metadata = self.metadata()
        scheduler = metadata.get("scheduler", {})
        prefix_kv_cache = metadata.get("prefix_kv_cache", {})
        prefix_policy = metadata.get("prefix_cache_policy", {})
        planned = {
            "engine_preset": config.get(
                "engine_preset",
                metadata.get("engine_preset", self.engine_preset),
            ),
            "scheduler": {
                "max_concurrent_requests": config.get(
                    "max_concurrent_requests",
                    scheduler.get("max_concurrent_requests", self.max_concurrent_requests),
                ),
                "max_queued_requests": config.get(
                    "max_queued_requests",
                    scheduler.get("max_queued_requests", self.max_queued_requests),
                ),
                "queue_timeout_ms": config.get(
                    "queue_timeout_ms",
                    scheduler.get("queue_timeout_ms", self.queue_timeout_ms),
                ),
            },
            "prefix_kv_cache": {
                "max_entries": config.get(
                    "prefix_cache_max_entries",
                    prefix_kv_cache.get("max_entries", self.prefix_cache_max_entries),
                ),
            },
            "prefix_cache_policy": {
                "memory_limit_bytes": prefix_policy.get("memory_limit_bytes"),
                "min_entries": config.get(
                    "prefix_cache_min_entries",
                    prefix_policy.get("min_entries", self.prefix_cache_min_entries),
                ),
                "population_mode": config.get(
                    "prefix_cache_population_mode",
                    prefix_policy.get(
                        "population_mode",
                        self.prefix_cache_population_mode,
                    ),
                ),
                "async_idle_timeout_ms": config.get(
                    "prefix_cache_async_idle_timeout_ms",
                    prefix_policy.get(
                        "async_idle_timeout_ms",
                        self.prefix_cache_async_idle_timeout_ms,
                    ),
                ),
                "async_idle_grace_ms": config.get(
                    "prefix_cache_async_idle_grace_ms",
                    prefix_policy.get(
                        "async_idle_grace_ms",
                        self.prefix_cache_async_idle_grace_ms,
                    ),
                ),
            },
        }
        if "prefix_cache_memory_limit_mb" in config:
            limit_mb = float(config["prefix_cache_memory_limit_mb"])
            planned["prefix_cache_policy"]["memory_limit_bytes"] = (
                int(limit_mb * 1024 * 1024) if limit_mb > 0 else None
            )
        return planned

    @staticmethod
    def config_from_request(request: EngineConfigRequest) -> dict[str, Any]:
        config = {}
        if request.engine_preset is not None:
            config.update(engine_preset_defaults(request.engine_preset))
            config["engine_preset"] = request.engine_preset

        for key in (
            "max_concurrent_requests",
            "max_queued_requests",
            "queue_timeout_ms",
            "prefix_cache_max_entries",
            "prefix_cache_memory_limit_mb",
            "prefix_cache_min_entries",
            "prefix_cache_population_mode",
            "prefix_cache_async_idle_timeout_ms",
            "prefix_cache_async_idle_grace_ms",
        ):
            value = getattr(request, key)
            if value is not None:
                config[key] = value
        return config

    def configure(self, request: EngineConfigRequest):
        config = self.config_from_request(request)
        if request.dry_run:
            return {
                "ok": True,
                "dry_run": True,
                "applied": {},
                "planned": config,
                "planned_state": self.planned_config_snapshot(config),
                "engine": self.metadata(),
            }
        if not config:
            return {
                "ok": True,
                "dry_run": False,
                "applied": {},
                "changes": {},
                "engine": self.metadata(),
            }

        with self.lock:
            self.max_concurrent_requests = int(
                config.get("max_concurrent_requests", self.max_concurrent_requests)
            )
            self.max_queued_requests = int(
                config.get("max_queued_requests", self.max_queued_requests)
            )
            self.queue_timeout_ms = int(
                config.get("queue_timeout_ms", self.queue_timeout_ms)
            )
            self.engine_preset = config.get("engine_preset", self.engine_preset)
            self.prefix_cache_max_entries = int(
                config.get("prefix_cache_max_entries", self.prefix_cache_max_entries)
            )
            self.prefix_cache_memory_limit_mb = float(
                config.get(
                    "prefix_cache_memory_limit_mb",
                    self.prefix_cache_memory_limit_mb,
                )
            )
            self.prefix_cache_min_entries = int(
                config.get("prefix_cache_min_entries", self.prefix_cache_min_entries)
            )
            self.prefix_cache_population_mode = config.get(
                "prefix_cache_population_mode",
                self.prefix_cache_population_mode,
            )
            self.prefix_cache_async_idle_timeout_ms = int(
                config.get(
                    "prefix_cache_async_idle_timeout_ms",
                    self.prefix_cache_async_idle_timeout_ms,
                )
            )
            self.prefix_cache_async_idle_grace_ms = int(
                config.get(
                    "prefix_cache_async_idle_grace_ms",
                    self.prefix_cache_async_idle_grace_ms,
                )
            )

            if self.engine is None:
                return {
                    "ok": True,
                    "dry_run": False,
                    "applied": config,
                    "changes": {"loaded": False},
                    "engine": self.metadata(),
                }
            return self.engine.configure_runtime(config)

    def reload(self, request: ReloadRequest):
        with self.lock:
            old_engine = self.engine
            model_path = request.model or (
                old_engine.model_path if old_engine is not None else self.last_model_path
            )
            profile_arg = Path(request.profile) if request.profile else None
            profile_path = ResidentEngine.discover_profile(model_path, profile_arg)
            warmup_prompt_tokens = (
                parse_warmup_tokens(request.warmup_prompt_tokens)
                if request.warmup_prompt_tokens
                else self.warmup_prompt_tokens
            )
            warmup_profile_prefill = (
                request.warmup_profile_prefill
                if request.warmup_profile_prefill is not None
                else self.warmup_profile_prefill
            )
            warmup_mode = request.warmup_mode or self.warmup_mode

            try:
                # Avoid replacing the active engine until the replacement is fully loaded.
                new_engine = ResidentEngine(
                    model_path=model_path,
                    profile_path=profile_path,
                    warmup_prompt_tokens=warmup_prompt_tokens,
                    warmup_profile_prefill=warmup_profile_prefill,
                    require_gpu=self.require_gpu,
                    max_concurrent_requests=self.max_concurrent_requests,
                    max_queued_requests=self.max_queued_requests,
                    queue_timeout_ms=self.queue_timeout_ms,
                    engine_preset=self.engine_preset,
                    prefix_cache_max_entries=self.prefix_cache_max_entries,
                    prefix_cache_memory_limit_mb=self.prefix_cache_memory_limit_mb,
                    prefix_cache_min_entries=self.prefix_cache_min_entries,
                    prefix_cache_population_mode=self.prefix_cache_population_mode,
                    prefix_cache_async_idle_timeout_ms=(
                        self.prefix_cache_async_idle_timeout_ms
                    ),
                    prefix_cache_async_idle_grace_ms=(
                        self.prefix_cache_async_idle_grace_ms
                    ),
                    warmup_mode=warmup_mode,
                )
                if old_engine is not None:
                    old_engine.execution_lock.acquire_foreground()
                try:
                    self.engine = new_engine
                    self.last_model_path = model_path
                    self.last_profile_path = profile_path
                    self.warmup_prompt_tokens = warmup_prompt_tokens
                    self.warmup_profile_prefill = warmup_profile_prefill
                    self.warmup_mode = warmup_mode
                    self.reload_count += 1
                    self.last_reload_error = None
                    self.last_unloaded_at = None
                finally:
                    if old_engine is not None:
                        old_engine.execution_lock.release()
                if old_engine is not None:
                    del old_engine
                gc.collect()
                if hasattr(mx, "clear_cache"):
                    mx.clear_cache()
                return self.metadata()
            except Exception as exc:
                self.last_reload_error = str(exc)
                raise

    def unload(self):
        with self.lock:
            old_engine = self.engine
            if old_engine is None:
                return self.metadata()
            old_engine.execution_lock.acquire_foreground()
            try:
                self.last_model_path = old_engine.model_path
                self.last_profile_path = old_engine.profile_path
                self.engine = None
                self.unload_count += 1
                self.last_unloaded_at = time.time()
            finally:
                old_engine.execution_lock.release()
            del old_engine
            gc.collect()
            if hasattr(mx, "clear_cache"):
                mx.clear_cache()
            return self.metadata()


def parse_args():
    parser = argparse.ArgumentParser(description="Run a resident MLX text engine.")
    parser.add_argument("--model", required=True)
    parser.add_argument("--profile", type=Path, default=None)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--warmup-prompt-tokens", default="64,512")
    parser.add_argument(
        "--warmup-profile-prefill",
        action=argparse.BooleanOptionalAction,
        default=False,
        help=(
            "Add one representative warmup prompt per profile-selected prefill "
            "step size."
        ),
    )
    parser.add_argument(
        "--warmup-mode",
        choices=("sync", "async", "off"),
        default="sync",
        help="Run startup warmup before readiness, in the background, or not at all.",
    )
    parser.add_argument("--require-gpu", action="store_true")
    parser.add_argument("--max-concurrent-requests", type=int, default=1)
    parser.add_argument("--max-queued-requests", type=int, default=16)
    parser.add_argument("--queue-timeout-ms", type=int, default=30000)
    parser.add_argument(
        "--engine-preset",
        choices=("custom", "sync-safe", "async-experimental", "memory-saver"),
        default="custom",
        help="Operator preset label applied by the launcher or direct CLI.",
    )
    parser.add_argument("--prefix-cache-max-entries", type=int, default=16)
    parser.add_argument("--prefix-cache-memory-limit-mb", type=float, default=0.0)
    parser.add_argument("--prefix-cache-min-entries", type=int, default=0)
    parser.add_argument(
        "--prefix-cache-population-mode",
        choices=("sync", "async", "request", "off"),
        default="sync",
    )
    parser.add_argument("--prefix-cache-async-idle-timeout-ms", type=int, default=30000)
    parser.add_argument("--prefix-cache-async-idle-grace-ms", type=int, default=0)
    return parser.parse_args()


def parse_warmup_tokens(raw: str):
    tokens = [int(part.strip()) for part in raw.split(",") if part.strip()]
    if any(token <= 0 for token in tokens):
        raise ValueError("warmup prompt tokens must be positive")
    return tokens


def create_app(manager: EngineManager):
    app = FastAPI(title="Resident MLX Engine", version="0.2")

    @app.get("/health")
    def health():
        if manager.engine is None:
            state = manager.metadata()
            return {
                "ok": False,
                "loaded": False,
                "reason": "no_model_loaded",
                **state,
            }
        health = manager.current().health()
        health["loaded"] = True
        return health

    @app.get("/engine")
    def engine_metadata():
        return manager.metadata()

    @app.post("/engine/config")
    def configure_engine(request: EngineConfigRequest):
        try:
            return manager.configure(request)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    @app.post("/engine/reload")
    def reload_engine(request: ReloadRequest):
        try:
            return manager.reload(request)
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc

    @app.post("/engine/unload")
    def unload_engine():
        return manager.unload()

    @app.post("/engine/cache/prune")
    def prune_engine_cache(request: CachePruneRequest):
        try:
            engine = manager.current()
            return engine.prune_prefix_cache(
                target_entries=request.target_entries,
                clear_mlx_cache=request.clear_mlx_cache,
                reason="manual",
            )
        except Exception as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    @app.post("/engine/lock/priority-probe")
    def execution_lock_priority_probe(request: LockPriorityProbeRequest):
        try:
            return manager.current().execution_lock_priority_probe(
                timeout_ms=request.timeout_ms,
            )
        except Exception as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    @app.get("/profile")
    def profile():
        try:
            return manager.current().profile
        except Exception as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    @app.get("/metrics")
    def metrics():
        try:
            return manager.current().metrics.snapshot()
        except Exception as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    @app.get("/engine/requests")
    def engine_requests():
        try:
            return manager.current().requests_snapshot()
        except Exception as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    @app.post("/engine/requests/{request_id}/cancel")
    def cancel_engine_request(request_id: str):
        try:
            result = manager.current().cancel_request(request_id)
            if not result.get("ok"):
                raise HTTPException(status_code=404, detail=result)
            return result
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    @app.post("/generate")
    def generate(request: GenerateRequest):
        try:
            engine = manager.current()
            if request.stream:
                return StreamingResponse(
                    engine.stream_generate_jsonl(request),
                    media_type="application/x-ndjson",
                )
            return engine.generate(request)
        except SchedulerRejected as exc:
            if "engine" in locals():
                engine.metrics.record_failure()
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        except RequestCancelled as exc:
            if "engine" in locals():
                engine.metrics.record_failure()
            raise HTTPException(status_code=499, detail=str(exc)) from exc
        except Exception as exc:
            if "engine" in locals():
                engine.metrics.record_failure()
            raise HTTPException(status_code=500, detail=str(exc)) from exc

    @app.post("/v1/completions")
    def completions(request: CompletionRequest):
        try:
            engine = manager.current()
            if request.stream:
                return StreamingResponse(
                    engine.stream_openai_completion(request),
                    media_type="text/event-stream",
                )
            return engine.openai_completion(request)
        except SchedulerRejected as exc:
            if "engine" in locals():
                engine.metrics.record_failure()
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        except Exception as exc:
            if "engine" in locals():
                engine.metrics.record_failure()
            raise HTTPException(status_code=500, detail=str(exc)) from exc

    @app.post("/v1/chat/completions")
    def chat_completions(request: ChatCompletionRequest):
        try:
            engine = manager.current()
            if request.stream:
                return StreamingResponse(
                    engine.stream_openai_chat_completion(request),
                    media_type="text/event-stream",
                )
            return engine.openai_chat_completion(request)
        except SchedulerRejected as exc:
            if "engine" in locals():
                engine.metrics.record_failure()
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        except Exception as exc:
            if "engine" in locals():
                engine.metrics.record_failure()
            raise HTTPException(status_code=500, detail=str(exc)) from exc

    return app


def main():
    main_started_at_epoch = time.time()
    args = parse_args()
    parent_started_at_epoch = None
    raw_parent_started_at = os.environ.get("MLX_ENGINE_PARENT_STARTED_AT_EPOCH")
    if raw_parent_started_at:
        try:
            parent_started_at_epoch = float(raw_parent_started_at)
        except ValueError:
            parent_started_at_epoch = None
    profile_t0 = time.perf_counter()
    profile_path = ResidentEngine.discover_profile(args.model, args.profile)
    startup_context = {
        "parent_started_at_epoch": parent_started_at_epoch,
        "module_imported_at_epoch": MODULE_IMPORTED_AT_EPOCH,
        "main_started_at_epoch": main_started_at_epoch,
        "profile_discovery_ms": 1e3 * (time.perf_counter() - profile_t0),
    }
    manager = EngineManager(
        model_path=args.model,
        profile_path=profile_path,
        warmup_prompt_tokens=parse_warmup_tokens(args.warmup_prompt_tokens),
        warmup_profile_prefill=args.warmup_profile_prefill,
        require_gpu=args.require_gpu,
        max_concurrent_requests=args.max_concurrent_requests,
        max_queued_requests=args.max_queued_requests,
        queue_timeout_ms=args.queue_timeout_ms,
        engine_preset=args.engine_preset,
        prefix_cache_max_entries=args.prefix_cache_max_entries,
        prefix_cache_memory_limit_mb=args.prefix_cache_memory_limit_mb,
        prefix_cache_min_entries=args.prefix_cache_min_entries,
        prefix_cache_population_mode=args.prefix_cache_population_mode,
        prefix_cache_async_idle_timeout_ms=args.prefix_cache_async_idle_timeout_ms,
        prefix_cache_async_idle_grace_ms=args.prefix_cache_async_idle_grace_ms,
        warmup_mode=args.warmup_mode,
        startup_context=startup_context,
    )
    uvicorn.run(create_app(manager), host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()
