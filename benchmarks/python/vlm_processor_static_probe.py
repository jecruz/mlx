#!/usr/bin/env python3
"""Static VLM processor/package probe for MLX Qwen3.6 checkpoints."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


DEFAULT_MODELS = [
    "/Volumes/StudioStackSSD4TB/Development/LLM/lmstudio/models/unsloth/Qwen3.6-27B-UD-MLX-4bit",
    "/Volumes/StudioStackSSD4TB/Development/LLM/lmstudio/models/unsloth/Qwen3.6-35B-A3B-UD-MLX-4bit",
]

REQUIRED_FILES = [
    "config.json",
    "processor_config.json",
    "tokenizer.json",
    "tokenizer_config.json",
    "chat_template.jinja",
    "model.safetensors.index.json",
]

REQUIRED_TOP_LEVEL_KEYS = [
    "vision_config",
    "image_token_id",
    "video_token_id",
    "vision_start_token_id",
    "vision_end_token_id",
]

REQUIRED_VISION_KEYS = [
    "patch_size",
    "spatial_merge_size",
    "temporal_patch_size",
    "num_position_embeddings",
]


def inspect_model(model_path: Path) -> dict[str, Any]:
    missing_files = [name for name in REQUIRED_FILES if not (model_path / name).is_file()]
    config = json.loads((model_path / "config.json").read_text())
    processor = json.loads((model_path / "processor_config.json").read_text())
    index = json.loads((model_path / "model.safetensors.index.json").read_text())
    chat_template = (model_path / "chat_template.jinja").read_text()

    missing_top_level = [key for key in REQUIRED_TOP_LEVEL_KEYS if key not in config]
    vision = config.get("vision_config") or {}
    missing_vision = [key for key in REQUIRED_VISION_KEYS if key not in vision]
    weight_files = sorted(set(index.get("weight_map", {}).values()))
    missing_weight_files = [name for name in weight_files if not (model_path / name).is_file()]
    template_markers = {
        "image_token_literal": "<|image_pad|>" in chat_template,
        "video_token_literal": "<|video_pad|>" in chat_template,
        "vision_start_literal": "<|vision_start|>" in chat_template,
        "vision_end_literal": "<|vision_end|>" in chat_template,
    }

    checks = {
        "required_files_present": not missing_files,
        "required_top_level_keys_present": not missing_top_level,
        "required_vision_keys_present": not missing_vision,
        "weight_shards_present": not missing_weight_files,
        "chat_template_has_vision_markers": all(template_markers.values()),
    }

    return {
        "model_path": str(model_path),
        "model_type": config.get("model_type"),
        "architectures": config.get("architectures"),
        "image_token_id": config.get("image_token_id"),
        "video_token_id": config.get("video_token_id"),
        "vision_start_token_id": config.get("vision_start_token_id"),
        "vision_end_token_id": config.get("vision_end_token_id"),
        "processor_class": processor.get("processor_class"),
        "image_processor_type": processor.get("image_processor_type"),
        "vision_model_type": vision.get("model_type"),
        "vision_patch_size": vision.get("patch_size"),
        "vision_spatial_merge_size": vision.get("spatial_merge_size"),
        "vision_temporal_patch_size": vision.get("temporal_patch_size"),
        "weight_shard_count": len(weight_files),
        "missing_files": missing_files,
        "missing_top_level_keys": missing_top_level,
        "missing_vision_keys": missing_vision,
        "missing_weight_files": missing_weight_files,
        "template_markers": template_markers,
        "checks": checks,
        "passes": all(checks.values()),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("models", nargs="*", default=DEFAULT_MODELS)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    report = {
        "probe": "vlm_processor_static_probe",
        "models": [inspect_model(Path(model)) for model in args.models],
    }
    report["passes"] = all(model["passes"] for model in report["models"])
    rendered = json.dumps(report, indent=2)
    if args.output:
        args.output.write_text(rendered + "\n")
    print(rendered)


if __name__ == "__main__":
    main()
