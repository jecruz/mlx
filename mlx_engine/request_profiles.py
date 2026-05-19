# Copyright © 2023-2024 Apple Inc.

"""Request-level workload intent to runtime-profile selection."""

from __future__ import annotations

from typing import Literal


RuntimeProfileName = Literal[
    "interactive",
    "agent-workspace",
    "agent-workspace-async",
    "agent-workspace-first-hit",
    "agent-workspace-low-memory",
    "agent-workspace-request",
    "memory-saver",
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


def select_runtime_profile_for_request(
    *,
    manual_profile: RuntimeProfileName | None = None,
    workload_intent: WorkloadIntent | None = None,
    diagnostics: bool = False,
    interactive: bool = False,
    agentic: bool = False,
    repeated_workspace: bool = False,
    immediate_second_turn: bool = False,
    low_memory: bool = False,
    memory_class_gb: int | None = None,
) -> tuple[RuntimeProfileName | None, str | None]:
    if manual_profile:
        return manual_profile, "request runtime_profile override"
    if diagnostics or workload_intent == "diagnostics":
        return "diagnostics", "diagnostics requested"
    if workload_intent == "memory-saver":
        return "memory-saver", "memory-saver intent"
    if (
        low_memory
        or workload_intent in {"coding-agent-low-memory", "low-memory"}
        or memory_class_gb in (16, 24, 32)
    ):
        return "agent-workspace-low-memory", "bounded memory mode"
    if immediate_second_turn or workload_intent in {"coding-agent-first-hit", "first-hit"}:
        return "agent-workspace-first-hit", "immediate repeated-context second turn"
    if agentic or repeated_workspace or workload_intent in {"coding-agent", "agent-workspace"}:
        return "agent-workspace-async", "steady-state coding-agent reuse"
    if interactive or workload_intent == "interactive":
        return "interactive", "foreground interactive use"
    return None, None
