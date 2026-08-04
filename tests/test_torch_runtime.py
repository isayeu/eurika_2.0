"""Tests for optional PyTorch runtime scaffold."""

from __future__ import annotations

import sys
from types import SimpleNamespace
from typing import Any

import pytest

from eurika.ml import torch_runtime as tr


@pytest.fixture(autouse=True)
def _reset_torch_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    tr._reset_torch_cache_for_tests()
    monkeypatch.delenv("EURIKA_TORCH_DEVICE", raising=False)
    yield
    tr._reset_torch_cache_for_tests()


def test_torch_status_when_import_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    # Drop cached torch so lazy import actually hits __import__.
    for key in list(sys.modules):
        if key == "torch" or key.startswith("torch."):
            monkeypatch.delitem(sys.modules, key, raising=False)

    real_import = __import__

    def fake_import(name: str, *args: Any, **kwargs: Any) -> Any:
        if name == "torch" or name.startswith("torch."):
            raise ImportError("simulated missing torch")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr("builtins.__import__", fake_import)
    assert tr.torch_available() is False
    st = tr.torch_status(run_smoke_check=True)
    assert st["available"] is False
    assert st["smoke_ok"] is None
    assert st["error"]
    block = tr.format_torch_block(st)
    assert "available: no" in block
    assert "PYTORCH" in block


def test_preferred_device_defaults_to_cpu(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = SimpleNamespace(
        __version__="2.1.0",
        cuda=SimpleNamespace(is_available=lambda: True),
    )
    monkeypatch.setattr(tr, "_load_torch", lambda: fake)
    assert tr.preferred_device() == "cpu"
    monkeypatch.setenv("EURIKA_TORCH_DEVICE", "cuda")
    assert tr.preferred_device() == "cuda"
    fake.cuda = SimpleNamespace(is_available=lambda: False)
    assert tr.preferred_device() == "cpu"


def test_run_smoke_and_status_with_fake_torch(monkeypatch: pytest.MonkeyPatch) -> None:
    class _T:
        def __init__(self, data: Any, device: str = "cpu") -> None:
            self.data = data
            self.device = device

        def __eq__(self, other: object) -> bool:
            return isinstance(other, _T) and other.data == self.data

    def matmul(a: _T, b: _T) -> _T:
        return _T([[19.0, 22.0], [43.0, 50.0]], device=a.device)

    fake = SimpleNamespace(
        __version__="2.1.0-test",
        cuda=SimpleNamespace(is_available=lambda: False),
        tensor=lambda data, device="cpu": _T(data, device=device),
        matmul=matmul,
        allclose=lambda a, b: a.data == b.data,
    )
    monkeypatch.setattr(tr, "_load_torch", lambda: fake)
    assert tr.run_smoke(device="cpu") is True
    st = tr.torch_status(run_smoke_check=True)
    assert st["available"] is True
    assert st["version"] == "2.1.0-test"
    assert st["device"] == "cpu"
    assert st["cuda"] is False
    assert st["smoke_ok"] is True
    block = tr.format_torch_block(st)
    assert "available: yes" in block
    assert "smoke: ok" in block


def test_format_pytorch_block_never_raises() -> None:
    from cli.core_handlers_common import _format_pytorch_block

    text = _format_pytorch_block()
    assert "PYTORCH" in text
    assert "available:" in text


def test_real_torch_smoke_when_installed() -> None:
    pytest.importorskip("torch")
    tr._reset_torch_cache_for_tests()
    assert tr.run_smoke(device="cpu") is True
    st = tr.torch_status()
    assert st["available"] is True
    assert st["smoke_ok"] is True
    assert st["device"] == "cpu"
