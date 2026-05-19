#!/usr/bin/env python3
"""Create a UI/Prowl field map for operator readiness surfaces."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


FIELD_MAP = [
    {
        "surface": "header",
        "label": "Readiness",
        "bundle_field": "verdict",
        "render_field": "display.title",
        "endpoint_field": "verdict",
        "required": True,
    },
    {
        "surface": "header",
        "label": "Active Model",
        "bundle_field": "model_decision.active_model",
        "render_field": "active_model_name",
        "endpoint_field": "runtime.model",
        "required": True,
    },
    {
        "surface": "badges",
        "label": "Runtime",
        "bundle_field": "status_card.runtime",
        "render_field": "status_card.runtime",
        "endpoint_field": "status_card.runtime",
        "required": True,
    },
    {
        "surface": "badges",
        "label": "Quality",
        "bundle_field": "status_card.quality",
        "render_field": "status_card.quality",
        "endpoint_field": None,
        "required": True,
    },
    {
        "surface": "badges",
        "label": "Memory Source",
        "bundle_field": "status_card.memory_source",
        "render_field": "status_card.memory_source",
        "endpoint_field": "memory.source",
        "required": True,
    },
    {
        "surface": "badges",
        "label": "Candidate Swap",
        "bundle_field": "status_card.candidate_swap",
        "render_field": "status_card.candidate_swap",
        "endpoint_field": None,
        "required": True,
    },
    {
        "surface": "details",
        "label": "Runtime Profile",
        "bundle_field": "runtime.runtime_profile",
        "render_field": "runtime_profile",
        "endpoint_field": "runtime.runtime_profile",
        "required": True,
    },
    {
        "surface": "details",
        "label": "Engine Preset",
        "bundle_field": "runtime.engine_preset",
        "render_field": "engine_preset",
        "endpoint_field": "runtime.engine_preset",
        "required": True,
    },
    {
        "surface": "details",
        "label": "Max Active Memory GB",
        "bundle_field": "memory.max_active_memory_gb",
        "render_field": "max_active_memory_gb",
        "endpoint_field": "memory.active_memory_bytes",
        "required": True,
    },
    {
        "surface": "warnings",
        "label": "Warnings",
        "bundle_field": "warnings",
        "render_field": "warnings",
        "endpoint_field": "warnings",
        "required": True,
    },
    {
        "surface": "failures",
        "label": "Failures",
        "bundle_field": "failures",
        "render_field": "failures",
        "endpoint_field": "failures",
        "required": True,
    },
]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-json", type=Path, required=True)
    parser.add_argument("--tag", default="m191-operator-ui-field-map")
    args = parser.parse_args()

    output = {
        "type": "operator_ui_field_map",
        "tag": args.tag,
        "verdict": "PASS",
        "readiness": "operator-ui-field-map-ready",
        "field_count": len(FIELD_MAP),
        "fields": FIELD_MAP,
        "guidance": {
            "primary_source": "operator readiness bundle or renderer JSON",
            "live_source": "/engine/operator-readiness",
            "quality_source": "artifact bundle only",
            "candidate_swap_warn_is_non_blocking": True,
        },
        "failures": [],
    }
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n")
    print(
        "operator_ui_field_map",
        output["verdict"],
        output["readiness"],
        "fields",
        len(FIELD_MAP),
        args.output_json,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
