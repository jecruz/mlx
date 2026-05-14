#!/usr/bin/env python3
"""Compatibility wrapper for the packaged resident MLX service."""

from __future__ import annotations

from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from mlx_engine.resident_service import main


if __name__ == "__main__":
    main()
