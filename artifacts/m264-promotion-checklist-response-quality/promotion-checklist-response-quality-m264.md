# M264 Promotion Checklist Response-Quality Gate

Timestamp: `2026-05-27`

Branch: `prompt-processing-bench`

## Purpose

M264 makes `bin/mlx-engine response-quality-release` the required promotion
checklist command before merging or promoting runtime/performance changes that
can affect inference quality.

## Required Command

```bash
bin/mlx-engine response-quality-release \
  --base-url http://127.0.0.1:8773 \
  --output-dir artifacts/response-quality-release \
  --tag response-quality-release \
  --fail-on-fail
```

## Required Pass Criteria

- runner verdict: `PASS`
- readiness: `response-quality-release-ready`
- candidate source: `live-capture`
- candidate-vs-baseline comparison: `PASS`
- release gate: `PASS`
- release gate count: `16`
- failures: `0`

## Scope

The gate is required for changes touching routing, cache behavior, prompt
processing, streaming, sampling defaults, context handling, tokenizer handling,
RoPE/IMRoPE, KV-cache reuse, model/profile swaps, or performance work being
promoted.

`--candidate-json` is acceptable for CI/offline checks that reuse an existing
capture. It is not final operator proof unless the release note explicitly
documents why live capture was skipped.

## Validation

```bash
rg -n "response-quality-release|Required Response-Quality Promotion Gate|M264" \
  docs/mac-local-inference-platform/resident-operator-runbook.md \
  docs/mac-local-inference-platform/inference-quality-gates.md \
  docs/mac-local-inference-platform/progress.md \
  artifacts/m264-promotion-checklist-response-quality/promotion-checklist-response-quality-m264.md

git diff --check
```
