#!/usr/bin/env python3
"""Validate Qwen3.5/Qwen3.6 interleaved MROPE lane semantics.

This probe does not load model weights. It checks the model config and the
installed mlx-vlm rotary implementation against the puma.cpp/panthro.cpp
GGML_ROPE_TYPE_IMROPE sector rule.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import mlx.core as mx
from mlx_vlm.models.qwen3_5.language import Qwen3_5RotaryEmbedding


DEFAULT_MODELS = [
    "/Volumes/StudioStackSSD4TB/Development/LLM/lmstudio/models/unsloth/Qwen3.6-27B-UD-MLX-4bit",
    "/Volumes/StudioStackSSD4TB/Development/LLM/lmstudio/models/unsloth/Qwen3.6-35B-A3B-UD-MLX-4bit",
]


def load_config(model_path: Path) -> dict[str, Any]:
    config_path = model_path / "config.json"
    return json.loads(config_path.read_text())


def puma_imrope_lane_owners(sections: list[int], lane_count: int) -> list[str]:
    sections4 = [*sections, 0][:4]
    sect_dims = sum(sections4)
    if sect_dims <= 0:
        raise ValueError(f"invalid IMROPE sections: {sections}")

    owners = []
    for lane in range(lane_count):
        sector = lane % sect_dims
        if sector % 3 == 1 and sector < 3 * sections4[1]:
            owners.append("h")
        elif sector % 3 == 2 and sector < 3 * sections4[2]:
            owners.append("w")
        elif sector % 3 == 0 and sector < 3 * sections4[0]:
            owners.append("t")
        else:
            owners.append("e")
    return owners


def mlx_interleaved_lane_owners(sections: list[int], lane_count: int) -> list[str]:
    rotary = Qwen3_5RotaryEmbedding(dim=lane_count * 2, mrope_section=sections)

    lanes = mx.arange(lane_count, dtype=mx.float32)
    freqs = mx.stack(
        [
            1000 + lanes,
            2000 + lanes,
            3000 + lanes,
        ],
        axis=0,
    ).reshape(3, 1, 1, lane_count)

    out = out_1d = rotary.apply_interleaved_mrope(freqs, sections).reshape(lane_count)
    mx.eval(out_1d)
    values = out.tolist()

    owners = []
    for value in values:
        if 1000 <= value < 2000:
            owners.append("t")
        elif 2000 <= value < 3000:
            owners.append("h")
        elif 3000 <= value < 4000:
            owners.append("w")
        else:
            owners.append("?")
    return owners


def inspect_model(model_path: Path) -> dict[str, Any]:
    cfg = load_config(model_path)
    text = cfg.get("text_config") or cfg
    rope = text.get("rope_parameters") or {}
    sections = rope.get("mrope_section")
    partial_rotary_factor = rope.get("partial_rotary_factor")
    head_dim = text.get("head_dim")

    if sections is None or partial_rotary_factor is None or head_dim is None:
        raise ValueError(f"{model_path} is missing Qwen IMROPE config fields")

    rotary_dim = int(head_dim * partial_rotary_factor)
    lane_count = rotary_dim // 2
    mlx_owners = mlx_interleaved_lane_owners(sections, lane_count)
    puma_owners = puma_imrope_lane_owners(sections, lane_count)

    mismatches = [
        {"lane": i, "mlx": mlx_owner, "puma": puma_owner}
        for i, (mlx_owner, puma_owner) in enumerate(zip(mlx_owners, puma_owners))
        if mlx_owner != puma_owner
    ]

    return {
        "model_path": str(model_path),
        "top_level_model_type": cfg.get("model_type"),
        "text_model_type": text.get("model_type"),
        "architectures": cfg.get("architectures"),
        "head_dim": head_dim,
        "partial_rotary_factor": partial_rotary_factor,
        "rotary_dim": rotary_dim,
        "frequency_lane_count": lane_count,
        "rope_parameters": rope,
        "mlx_lane_owners": "".join(mlx_owners),
        "puma_panthro_lane_owners": "".join(puma_owners),
        "mismatch_count": len(mismatches),
        "mismatches": mismatches,
        "passes": len(mismatches) == 0 and rope.get("mrope_interleaved") is True,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("models", nargs="*", default=DEFAULT_MODELS)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    report = {
        "probe": "qwen_imrope_static_probe",
        "comparison": "mlx-vlm Qwen3_5RotaryEmbedding.apply_interleaved_mrope vs puma.cpp/panthro.cpp GGML_ROPE_TYPE_IMROPE sector rule",
        "models": [inspect_model(Path(model)) for model in args.models],
    }
    report["passes"] = all(model["passes"] for model in report["models"])

    rendered = json.dumps(report, indent=2)
    if args.output:
        args.output.write_text(rendered + "\n")
    print(rendered)


if __name__ == "__main__":
    main()
