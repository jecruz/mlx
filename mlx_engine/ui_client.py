# Copyright © 2023-2024 Apple Inc.

"""Client helpers for UI integrations with the resident MLX engine."""

from __future__ import annotations

import json
import urllib.request
from dataclasses import dataclass
from typing import Any, Literal


WorkloadIntent = Literal[
    "interactive",
    "coding-agent",
    "agent-workspace",
    "memory-saver",
    "diagnostics",
]

WORKLOAD_INTENT_PROFILES: dict[WorkloadIntent, str] = {
    "interactive": "interactive",
    "coding-agent": "agent-workspace-async",
    "agent-workspace": "agent-workspace-async",
    "memory-saver": "memory-saver",
    "diagnostics": "diagnostics",
}


def runtime_profile_for_intent(intent: WorkloadIntent) -> str:
    return WORKLOAD_INTENT_PROFILES[intent]


@dataclass(frozen=True)
class EngineUiSummary:
    loaded: bool
    model: str | None
    runtime_profile: str | None
    engine_preset: str | None
    gpu_ready: bool
    warm: bool
    can_generate: bool
    cache_strategy: str | None
    cache_blockers: tuple[str, ...]
    active_requests: int
    queued_requests: int
    total_requests: int
    failed_requests: int


class EngineUiClient:
    """Small HTTP client for product-facing resident-engine UI state."""

    def __init__(self, base_url: str = "http://127.0.0.1:8765", *, timeout: int = 120):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def _request_json(
        self,
        method: str,
        path: str,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        data = None
        headers = {}
        if payload is not None:
            data = json.dumps(payload).encode()
            headers["Content-Type"] = "application/json"
        req = urllib.request.Request(
            f"{self.base_url}{path}",
            data=data,
            method=method,
            headers=headers,
        )
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            return json.loads(resp.read().decode())

    def status(self) -> dict[str, Any]:
        return self._request_json("GET", "/engine/ui")

    def profiles(self) -> dict[str, Any]:
        return self._request_json("GET", "/engine/profiles")

    def apply_profile(self, runtime_profile: str, *, dry_run: bool = False) -> dict[str, Any]:
        return self._request_json(
            "POST",
            "/engine/config",
            {
                "dry_run": dry_run,
                "runtime_profile": runtime_profile,
            },
        )

    def apply_workload_intent(
        self,
        intent: WorkloadIntent,
        *,
        dry_run: bool = False,
    ) -> dict[str, Any]:
        return self.apply_profile(runtime_profile_for_intent(intent), dry_run=dry_run)

    def summary(self) -> EngineUiSummary:
        status = self.status()
        readiness = status.get("readiness") or {}
        controls = status.get("controls") or {}
        scheduler = status.get("scheduler") or {}
        metrics = status.get("metrics") or {}
        blockers = readiness.get("blockers") or []
        return EngineUiSummary(
            loaded=bool(status.get("loaded")),
            model=status.get("model"),
            runtime_profile=status.get("runtime_profile"),
            engine_preset=status.get("engine_preset"),
            gpu_ready=bool(readiness.get("gpu_ready")),
            warm=bool(readiness.get("warm")),
            can_generate=bool(controls.get("can_generate")),
            cache_strategy=readiness.get("strategy"),
            cache_blockers=tuple(str(blocker) for blocker in blockers),
            active_requests=int(scheduler.get("active_requests") or 0),
            queued_requests=int(scheduler.get("queued_requests") or 0),
            total_requests=int(metrics.get("total_requests") or 0),
            failed_requests=int(metrics.get("failed_requests") or 0),
        )
