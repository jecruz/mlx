"""Response metrics shaping helpers for hot OpenAI-compatible responses."""

from __future__ import annotations

from typing import Any, Literal


MetricsDetail = Literal["full", "compact", "off"]

COMPACT_ENGINE_METRIC_KEYS = [
    "request_id",
    "created",
    "model",
    "backend",
    "effective_policy",
    "prefill_step_size",
    "prompt_tokens",
    "actual_prefill_tokens",
    "generation_tokens",
    "run_ms",
    "service_request_ms",
    "engine_lock_wait_ms",
    "scheduler_queue_wait_ms",
    "cache_reuse_enabled",
    "cache_hit",
    "cache_created",
    "cache_scheduled",
    "cache_pending",
    "cache_prepare_ms",
    "cached_prefix_tokens",
    "cache_pending_wait_ms",
    "cache_pending_wait_result",
    "prefix_lookup_fast_path",
    "prefix_lookup_path",
    "tokenized_prompt_cache_hit",
    "tokenized_prompt_cache_ms",
    "stop_reason",
]


def effective_metrics_detail(
    *,
    requested: MetricsDetail,
    diagnostics_workload: bool,
) -> MetricsDetail:
    return "full" if diagnostics_workload else requested


def shape_engine_metrics(
    row: dict[str, Any],
    *,
    requested: MetricsDetail,
    diagnostics_workload: bool,
) -> dict[str, Any] | None:
    detail = effective_metrics_detail(
        requested=requested,
        diagnostics_workload=diagnostics_workload,
    )
    if detail == "off":
        return None
    if detail == "full":
        output = dict(row)
        output["metrics_detail"] = "full"
        output["metrics_compacted"] = False
        return output

    compact = {key: row.get(key) for key in COMPACT_ENGINE_METRIC_KEYS if key in row}
    compact["metrics_detail"] = "compact"
    compact["metrics_compacted"] = True
    compact["metrics_full_available_via"] = "/metrics"
    return compact


def attach_engine_metrics(
    payload: dict[str, Any],
    row: dict[str, Any],
    *,
    requested: MetricsDetail,
    diagnostics_workload: bool,
) -> dict[str, Any]:
    metrics = shape_engine_metrics(
        row,
        requested=requested,
        diagnostics_workload=diagnostics_workload,
    )
    if metrics is not None:
        payload["engine_metrics"] = metrics
    return payload
