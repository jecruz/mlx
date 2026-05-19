# Copyright © 2023-2024 Apple Inc.

"""Client helpers for UI integrations with the resident MLX engine."""

from __future__ import annotations

import json
import urllib.request
from dataclasses import dataclass
from typing import Any, Literal


ProductMode = Literal[
    "chat",
    "coding-agent",
    "coding-agent-first-hit",
    "coding-agent-low-memory",
    "diagnostics",
]
WorkloadIntent = Literal[
    "interactive",
    "coding-agent",
    "agent-workspace",
    "coding-agent-first-hit",
    "first-hit",
    "coding-agent-low-memory",
    "low-memory",
    "memory-saver",
    "diagnostics",
]

WORKLOAD_INTENT_PROFILES: dict[WorkloadIntent, str] = {
    "interactive": "interactive",
    "coding-agent": "agent-workspace-async",
    "agent-workspace": "agent-workspace-async",
    "coding-agent-first-hit": "agent-workspace-first-hit",
    "first-hit": "agent-workspace-first-hit",
    "coding-agent-low-memory": "agent-workspace-low-memory",
    "low-memory": "agent-workspace-low-memory",
    "memory-saver": "memory-saver",
    "diagnostics": "diagnostics",
}


def runtime_profile_for_intent(intent: WorkloadIntent) -> str:
    return WORKLOAD_INTENT_PROFILES[intent]


@dataclass(frozen=True)
class ProductRequestMetadata:
    workload_intent: WorkloadIntent
    runtime_profile: str | None = None
    memory_class_gb: int | None = None
    immediate_second_turn: bool = False
    low_memory: bool = False
    diagnostics_workload: bool = False
    interactive_workload: bool = False
    agentic_workload: bool = False
    repeated_workspace: bool = False

    def request_fields(self) -> dict[str, Any]:
        fields = {
            "workload_intent": self.workload_intent,
            "runtime_profile": self.runtime_profile,
            "memory_class_gb": self.memory_class_gb,
            "immediate_second_turn": self.immediate_second_turn,
            "low_memory": self.low_memory,
            "diagnostics_workload": self.diagnostics_workload,
            "interactive_workload": self.interactive_workload,
            "agentic_workload": self.agentic_workload,
            "repeated_workspace": self.repeated_workspace,
        }
        return {key: value for key, value in fields.items() if value is not None}

    @property
    def expected_runtime_profile(self) -> str:
        if self.runtime_profile is not None:
            return self.runtime_profile
        if self.diagnostics_workload or self.workload_intent == "diagnostics":
            return "diagnostics"
        if self.workload_intent == "memory-saver":
            return "memory-saver"
        if (
            self.low_memory
            or self.workload_intent in {"coding-agent-low-memory", "low-memory"}
            or self.memory_class_gb in (16, 24, 32)
        ):
            return "agent-workspace-low-memory"
        if (
            self.immediate_second_turn
            or self.workload_intent in {"coding-agent-first-hit", "first-hit"}
        ):
            return "agent-workspace-first-hit"
        if (
            self.agentic_workload
            or self.repeated_workspace
            or self.workload_intent in {"coding-agent", "agent-workspace"}
        ):
            return "agent-workspace-async"
        return runtime_profile_for_intent(self.workload_intent)


def metadata_for_product_mode(
    mode: ProductMode,
    *,
    memory_class_gb: int | None = None,
    runtime_profile: str | None = None,
) -> ProductRequestMetadata:
    if mode == "chat":
        return ProductRequestMetadata(
            workload_intent="interactive",
            runtime_profile=runtime_profile,
            interactive_workload=True,
        )
    if mode == "coding-agent":
        return ProductRequestMetadata(
            workload_intent="coding-agent",
            runtime_profile=runtime_profile,
            memory_class_gb=memory_class_gb,
            agentic_workload=True,
            repeated_workspace=True,
        )
    if mode == "coding-agent-first-hit":
        return ProductRequestMetadata(
            workload_intent="first-hit",
            runtime_profile=runtime_profile,
            memory_class_gb=memory_class_gb,
            immediate_second_turn=True,
            agentic_workload=True,
            repeated_workspace=True,
        )
    if mode == "coding-agent-low-memory":
        return ProductRequestMetadata(
            workload_intent="coding-agent",
            runtime_profile=runtime_profile,
            memory_class_gb=memory_class_gb or 32,
            low_memory=True,
            agentic_workload=True,
            repeated_workspace=True,
        )
    if mode == "diagnostics":
        return ProductRequestMetadata(
            workload_intent="diagnostics",
            runtime_profile=runtime_profile,
            diagnostics_workload=True,
        )
    raise ValueError(f"unknown product mode: {mode}")


def apply_product_mode(
    payload: dict[str, Any],
    mode: ProductMode,
    *,
    memory_class_gb: int | None = None,
    runtime_profile: str | None = None,
) -> dict[str, Any]:
    return {
        **payload,
        **metadata_for_product_mode(
            mode,
            memory_class_gb=memory_class_gb,
            runtime_profile=runtime_profile,
        ).request_fields(),
    }


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
