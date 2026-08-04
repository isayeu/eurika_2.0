"""Optional PyTorch runtime probe (CR-G3 scaffold).

Torch is an optional dependency (`pip install -e ".[torch]"`). Core Eurika
never imports torch at module load; learning loop does not depend on it.
ML works alongside LLM (Ollama/OpenAI), not as a replacement for generate.
Default device is CPU — suitable for 8 GB RAM / old NVIDIA drivers.
"""

from __future__ import annotations

import os
from typing import Any, Optional

_torch_mod: Any = None
_torch_import_error: Optional[str] = None
_torch_probed: bool = False


def _load_torch() -> Any:
    """Lazy-import torch once. Returns module or None."""
    global _torch_mod, _torch_import_error, _torch_probed
    if _torch_probed:
        return _torch_mod
    _torch_probed = True
    try:
        import torch as _t

        _torch_mod = _t
        _torch_import_error = None
    except Exception as exc:  # ImportError and rare init failures
        _torch_mod = None
        _torch_import_error = f"{type(exc).__name__}: {exc}"
    return _torch_mod


def torch_available() -> bool:
    """True if torch can be imported."""
    return _load_torch() is not None


def preferred_device() -> str:
    """Resolve compute device.

    Default: cpu. Set EURIKA_TORCH_DEVICE=cuda only when CUDA is available;
    otherwise falls back to cpu (and similarly for mps).
    """
    torch = _load_torch()
    if torch is None:
        return "cpu"
    requested = (os.environ.get("EURIKA_TORCH_DEVICE") or "cpu").strip().lower()
    if requested in ("", "cpu"):
        return "cpu"
    if requested == "cuda":
        try:
            if bool(torch.cuda.is_available()):
                return "cuda"
        except Exception:
            pass
        return "cpu"
    if requested == "mps":
        try:
            mps = getattr(torch.backends, "mps", None)
            if mps is not None and bool(mps.is_available()):
                return "mps"
        except Exception:
            pass
        return "cpu"
    return "cpu"


def run_smoke(*, device: Optional[str] = None) -> bool:
    """Tiny matmul smoke test. No model download. Returns True on success."""
    torch = _load_torch()
    if torch is None:
        return False
    dev = device or preferred_device()
    try:
        a = torch.tensor([[1.0, 2.0], [3.0, 4.0]], device=dev)
        b = torch.tensor([[5.0, 6.0], [7.0, 8.0]], device=dev)
        c = torch.matmul(a, b)
        expected = torch.tensor([[19.0, 22.0], [43.0, 50.0]], device=dev)
        return bool(torch.allclose(c, expected))
    except Exception:
        return False


def torch_status(*, run_smoke_check: bool = True) -> dict[str, Any]:
    """Probe status for self-check / diagnostics.

    Keys: available, version, device, cuda, smoke_ok, error.
    smoke_ok is None when skipped (torch absent or run_smoke_check=False).
    """
    import warnings

    torch = _load_torch()
    if torch is None:
        return {
            "available": False,
            "version": None,
            "device": "cpu",
            "cuda": False,
            "smoke_ok": None,
            "error": _torch_import_error or "torch not installed",
        }
    cuda = False
    try:
        # Old NVIDIA drivers (e.g. 470) warn loudly on CUDA probe; scaffold defaults to CPU.
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", UserWarning)
            cuda = bool(torch.cuda.is_available())
    except Exception:
        cuda = False
    version = getattr(torch, "__version__", None)
    device = preferred_device()
    smoke_ok: Optional[bool] = None
    error: Optional[str] = None
    if run_smoke_check:
        try:
            smoke_ok = run_smoke(device=device)
            if not smoke_ok:
                error = "smoke matmul failed"
        except Exception as exc:
            smoke_ok = False
            error = f"{type(exc).__name__}: {exc}"
    return {
        "available": True,
        "version": version,
        "device": device,
        "cuda": cuda,
        "smoke_ok": smoke_ok,
        "error": error,
    }


def format_torch_block(status: Optional[dict[str, Any]] = None) -> str:
    """Human-readable PYTORCH block for self-check."""
    st = status if status is not None else torch_status()
    lines = ["", "PYTORCH (optional ML runtime)", ""]
    if not st.get("available"):
        lines.append("  available: no")
        err = st.get("error")
        if err:
            lines.append(f"  detail: {err}")
        lines.append("  install: pip install -e \".[torch]\"  # prefer CPU wheel on low VRAM")
        return "\n".join(lines)
    smoke = st.get("smoke_ok")
    if smoke is True:
        smoke_s = "ok"
    elif smoke is False:
        smoke_s = "fail"
    else:
        smoke_s = "skip"
    lines.append("  available: yes")
    lines.append(f"  version: {st.get('version') or '?'}")
    lines.append(f"  device: {st.get('device') or 'cpu'}")
    lines.append(f"  cuda: {'yes' if st.get('cuda') else 'no'}")
    lines.append(f"  smoke: {smoke_s}")
    if st.get("error"):
        lines.append(f"  error: {st['error']}")
    return "\n".join(lines)


# Test helper: reset lazy-import cache between tests.
def _reset_torch_cache_for_tests() -> None:
    global _torch_mod, _torch_import_error, _torch_probed
    _torch_mod = None
    _torch_import_error = None
    _torch_probed = False
