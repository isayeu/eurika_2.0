"""Optional ML helpers (PyTorch scaffold + paper market loop). Not required for core learning loop."""

from __future__ import annotations

from eurika.ml.torch_runtime import (
    format_torch_block,
    preferred_device,
    run_smoke,
    torch_available,
    torch_status,
)

__all__ = [
    "format_torch_block",
    "preferred_device",
    "run_smoke",
    "torch_available",
    "torch_status",
]
