"""Tests for Ollama GPU env helpers (CUDA / Vulkan / CPU)."""

from __future__ import annotations

from qt_app.ui.handlers.ollama_handlers import apply_ollama_gpu_env


class _FakeEnv:
    def __init__(self) -> None:
        self._data: dict[str, str] = {}

    def insert(self, key: str, value: str) -> None:
        self._data[key] = value

    def remove(self, key: str) -> None:
        self._data.pop(key, None)

    def value(self, key: str, default: str = "") -> str:
        return self._data.get(key, default)

    def contains(self, key: str) -> bool:
        return key in self._data


def test_apply_ollama_gpu_env_vulkan() -> None:
    env = _FakeEnv()
    summary = apply_ollama_gpu_env(
        env,
        use_cuda=False,
        cuda_devices="0",
        use_vulkan=True,
        vk_devices="1",
        hsa_override="10.3.0",
        rocr_devices="0",
        hip_devices="0",
    )
    assert "OLLAMA_VULKAN=1" in summary
    assert "GGML_VK_VISIBLE_DEVICES=1" in summary
    assert env.value("OLLAMA_VULKAN") == "1"
    assert env.value("GGML_VK_VISIBLE_DEVICES") == "1"
    assert not env.contains("CUDA_VISIBLE_DEVICES")
    assert not env.contains("HSA_OVERRIDE_GFX_VERSION")
    assert not env.contains("ROCR_VISIBLE_DEVICES")
    assert not env.contains("HIP_VISIBLE_DEVICES")


def test_apply_ollama_gpu_env_cuda() -> None:
    env = _FakeEnv()
    summary = apply_ollama_gpu_env(
        env,
        use_cuda=True,
        cuda_devices="0",
        use_vulkan=True,  # CUDA wins
        vk_devices="1",
        hsa_override="10.3.0",
        rocr_devices="0",
        hip_devices="0",
    )
    assert "CUDA_VISIBLE_DEVICES=0" in summary
    assert env.value("CUDA_VISIBLE_DEVICES") == "0"
    assert env.value("OLLAMA_VULKAN") == "0"
    assert not env.contains("ROCR_VISIBLE_DEVICES")
    assert not env.contains("HSA_OVERRIDE_GFX_VERSION")
    assert not env.contains("GGML_VK_VISIBLE_DEVICES")


def test_apply_ollama_gpu_env_cpu() -> None:
    env = _FakeEnv()
    summary = apply_ollama_gpu_env(
        env,
        use_cuda=False,
        cuda_devices="0",
        use_vulkan=False,
        vk_devices="",
        hsa_override="10.3.0",
        rocr_devices="0",
        hip_devices="0",
    )
    assert "CPU" in summary
    assert env.value("OLLAMA_NUM_GPU") == "0"
    assert env.value("OLLAMA_VULKAN") == "0"
    assert env.value("CUDA_VISIBLE_DEVICES") == ""
