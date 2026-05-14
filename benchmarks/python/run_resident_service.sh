#!/usr/bin/env bash
set -euo pipefail

MODEL="${1:?usage: run_resident_service.sh MODEL_PATH [PREFILL_PROFILE_JSON] [PORT]}"
PROFILE="${2:-}"
PORT="${3:-8765}"
PYTHON="${PYTHON:-python3}"
ENGINE_PRESET="${ENGINE_PRESET:-sync-safe}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROFILE_ARGS=()

case "${ENGINE_PRESET}" in
  sync-safe)
    PRESET_MAX_CONCURRENT_REQUESTS=1
    PRESET_MAX_QUEUED_REQUESTS=16
    PRESET_QUEUE_TIMEOUT_MS=30000
    PRESET_PREFIX_CACHE_MAX_ENTRIES=16
    PRESET_PREFIX_CACHE_MEMORY_LIMIT_MB=0
    PRESET_PREFIX_CACHE_MIN_ENTRIES=0
    PRESET_PREFIX_CACHE_POPULATION_MODE=sync
    PRESET_PREFIX_CACHE_ASYNC_IDLE_TIMEOUT_MS=30000
    ;;
  async-experimental)
    PRESET_MAX_CONCURRENT_REQUESTS=1
    PRESET_MAX_QUEUED_REQUESTS=16
    PRESET_QUEUE_TIMEOUT_MS=30000
    PRESET_PREFIX_CACHE_MAX_ENTRIES=16
    PRESET_PREFIX_CACHE_MEMORY_LIMIT_MB=0
    PRESET_PREFIX_CACHE_MIN_ENTRIES=0
    PRESET_PREFIX_CACHE_POPULATION_MODE=async
    PRESET_PREFIX_CACHE_ASYNC_IDLE_TIMEOUT_MS=30000
    ;;
  memory-saver)
    PRESET_MAX_CONCURRENT_REQUESTS=1
    PRESET_MAX_QUEUED_REQUESTS=8
    PRESET_QUEUE_TIMEOUT_MS=30000
    PRESET_PREFIX_CACHE_MAX_ENTRIES=4
    PRESET_PREFIX_CACHE_MEMORY_LIMIT_MB=64
    PRESET_PREFIX_CACHE_MIN_ENTRIES=1
    PRESET_PREFIX_CACHE_POPULATION_MODE=sync
    PRESET_PREFIX_CACHE_ASYNC_IDLE_TIMEOUT_MS=30000
    ;;
  custom)
    PRESET_MAX_CONCURRENT_REQUESTS=1
    PRESET_MAX_QUEUED_REQUESTS=16
    PRESET_QUEUE_TIMEOUT_MS=30000
    PRESET_PREFIX_CACHE_MAX_ENTRIES=16
    PRESET_PREFIX_CACHE_MEMORY_LIMIT_MB=0
    PRESET_PREFIX_CACHE_MIN_ENTRIES=0
    PRESET_PREFIX_CACHE_POPULATION_MODE=sync
    PRESET_PREFIX_CACHE_ASYNC_IDLE_TIMEOUT_MS=30000
    ;;
  *)
    echo "error: unsupported ENGINE_PRESET: ${ENGINE_PRESET}" >&2
    echo "valid presets: sync-safe, async-experimental, memory-saver, custom" >&2
    exit 64
    ;;
esac

MAX_CONCURRENT_REQUESTS="${MAX_CONCURRENT_REQUESTS:-$PRESET_MAX_CONCURRENT_REQUESTS}"
MAX_QUEUED_REQUESTS="${MAX_QUEUED_REQUESTS:-$PRESET_MAX_QUEUED_REQUESTS}"
QUEUE_TIMEOUT_MS="${QUEUE_TIMEOUT_MS:-$PRESET_QUEUE_TIMEOUT_MS}"
PREFIX_CACHE_MAX_ENTRIES="${PREFIX_CACHE_MAX_ENTRIES:-$PRESET_PREFIX_CACHE_MAX_ENTRIES}"
PREFIX_CACHE_MEMORY_LIMIT_MB="${PREFIX_CACHE_MEMORY_LIMIT_MB:-$PRESET_PREFIX_CACHE_MEMORY_LIMIT_MB}"
PREFIX_CACHE_MIN_ENTRIES="${PREFIX_CACHE_MIN_ENTRIES:-$PRESET_PREFIX_CACHE_MIN_ENTRIES}"
PREFIX_CACHE_POPULATION_MODE="${PREFIX_CACHE_POPULATION_MODE:-$PRESET_PREFIX_CACHE_POPULATION_MODE}"
PREFIX_CACHE_ASYNC_IDLE_TIMEOUT_MS="${PREFIX_CACHE_ASYNC_IDLE_TIMEOUT_MS:-$PRESET_PREFIX_CACHE_ASYNC_IDLE_TIMEOUT_MS}"
WARMUP_MODE="${WARMUP_MODE:-async}"

if [[ -n "${PROFILE}" && "${PROFILE}" =~ ^[0-9]+$ ]]; then
  PORT="${PROFILE}"
  PROFILE=""
fi

if [[ ! -f "${MODEL}/config.json" ]]; then
  echo "error: model config not found: ${MODEL}/config.json" >&2
  exit 64
fi

if [[ ! -r "${MODEL}/config.json" ]]; then
  echo "error: model config is not readable by this process: ${MODEL}/config.json" >&2
  echo "Grant the launching Terminal/tmux/Python process permission to read the model volume." >&2
  exit 77
fi

if [[ -n "${PROFILE}" ]]; then
  if [[ ! -f "${PROFILE}" ]]; then
    echo "error: profile not found: ${PROFILE}" >&2
    exit 64
  fi
  PROFILE_ARGS=(--profile "${PROFILE}")
fi

if [[ ${#PROFILE_ARGS[@]} -gt 0 ]]; then
  "${PYTHON}" "${SCRIPT_DIR}/resident_mlx_service.py" \
    --model "${MODEL}" \
    "${PROFILE_ARGS[@]}" \
    --port "${PORT}" \
    --engine-preset "${ENGINE_PRESET}" \
    --warmup-prompt-tokens 64,512 \
    --warmup-mode "${WARMUP_MODE}" \
    --max-concurrent-requests "${MAX_CONCURRENT_REQUESTS}" \
    --max-queued-requests "${MAX_QUEUED_REQUESTS}" \
    --queue-timeout-ms "${QUEUE_TIMEOUT_MS}" \
    --prefix-cache-max-entries "${PREFIX_CACHE_MAX_ENTRIES}" \
    --prefix-cache-memory-limit-mb "${PREFIX_CACHE_MEMORY_LIMIT_MB}" \
    --prefix-cache-min-entries "${PREFIX_CACHE_MIN_ENTRIES}" \
    --prefix-cache-population-mode "${PREFIX_CACHE_POPULATION_MODE}" \
    --prefix-cache-async-idle-timeout-ms "${PREFIX_CACHE_ASYNC_IDLE_TIMEOUT_MS}" \
    --require-gpu
else
  "${PYTHON}" "${SCRIPT_DIR}/resident_mlx_service.py" \
    --model "${MODEL}" \
    --port "${PORT}" \
    --engine-preset "${ENGINE_PRESET}" \
    --warmup-prompt-tokens 64,512 \
    --warmup-mode "${WARMUP_MODE}" \
    --max-concurrent-requests "${MAX_CONCURRENT_REQUESTS}" \
    --max-queued-requests "${MAX_QUEUED_REQUESTS}" \
    --queue-timeout-ms "${QUEUE_TIMEOUT_MS}" \
    --prefix-cache-max-entries "${PREFIX_CACHE_MAX_ENTRIES}" \
    --prefix-cache-memory-limit-mb "${PREFIX_CACHE_MEMORY_LIMIT_MB}" \
    --prefix-cache-min-entries "${PREFIX_CACHE_MIN_ENTRIES}" \
    --prefix-cache-population-mode "${PREFIX_CACHE_POPULATION_MODE}" \
    --prefix-cache-async-idle-timeout-ms "${PREFIX_CACHE_ASYNC_IDLE_TIMEOUT_MS}" \
    --require-gpu
fi
