#!/usr/bin/env bash
set -euo pipefail

MODEL="${1:?usage: run_prompt_sweep.sh MODEL_PATH [OUTPUT_JSONL]}"
OUT="${2:-prompt-sweep.jsonl}"
PYTHON="${PYTHON:-python3}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BENCH="${SCRIPT_DIR}/vlm_prompt_decode_bench.py"

if [[ ! -f "${MODEL}/config.json" ]]; then
  echo "error: model config not found: ${MODEL}/config.json" >&2
  echo "hint: quote the model path, especially if copying a wrapped command." >&2
  exit 64
fi

: > "${OUT}"

for TOKENS in 8 16 32 64; do
  TMP="$(mktemp)"
  "${PYTHON}" "${BENCH}" \
    --model "${MODEL}" \
    --prompt placeholder \
    --prompt-tokens "${TOKENS}" \
    --max-tokens 1 \
    --temperature 0 \
    --require-gpu \
    --json > "${TMP}"
  cat "${TMP}" >&2
  JSON_LINE="$(tail -n 1 "${TMP}")"
  rm -f "${TMP}"
  if [[ "${JSON_LINE}" != \{* ]]; then
    echo "error: benchmark did not end with a JSON result for ${TOKENS} prompt tokens" >&2
    exit 65
  fi
  printf '%s\n' "${JSON_LINE}" >> "${OUT}"
done

echo "wrote ${OUT}"
