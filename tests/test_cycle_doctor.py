"""Tests for eurika doctor command and doctor cycle."""
import json
import subprocess
import sys
from pathlib import Path
from typing import Any
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _minimal_self_map(path: Path, modules: list, dependencies: dict) -> None:
    data = {
        "modules": [{"path": p, "lines": 10, "functions": [], "classes": []} for p in modules],
        "dependencies": dependencies,
    }
    path.write_text(json.dumps(data), encoding="utf-8")


def test_doctor_includes_knowledge_when_cache_present(tmp_path: Path) -> None:
    """
    doctor --no-llm with eurika_knowledge.json in project root: architect output includes
    Reference block from Knowledge Layer (Knowledge Layer integration).
    """
    proj = tmp_path / "proj"
    proj.mkdir()
    _minimal_self_map(proj / "self_map.json", ["a.py"], {})
    (proj / "eurika_knowledge.json").write_text(
        json.dumps({
            "topics": {
                "python": [{"title": "PEP 701", "content": "f-strings can contain nested quotes."}],
            }
        }, ensure_ascii=False),
        encoding="utf-8",
    )
    result = subprocess.run(
        [sys.executable, "-m", "eurika_cli", "doctor", "--no-llm", str(proj)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, f"stderr: {result.stderr}\nstdout: {result.stdout[:800]}"
    assert "Reference" in result.stdout, "Knowledge Layer: architect should include Reference when cache has topic"
    assert "PEP 701" in result.stdout or "f-strings" in result.stdout, "Reference content from cache should appear"


def test_knowledge_topics_derived_from_summary(monkeypatch: Any) -> None:
    """_knowledge_topics_from_env_or_summary: without env, topics derived from summary (cycles, risks)."""
    monkeypatch.delenv("EURIKA_KNOWLEDGE_TOPIC", raising=False)
    from cli.core_handlers import knowledge_topics_from_env_or_summary

    topics = knowledge_topics_from_env_or_summary({"system": {}, "risks": []})
    assert topics == ["python", "python_3_14"]
    topics = knowledge_topics_from_env_or_summary({"system": {"cycles": 1}, "risks": []})
    assert "python" in topics and "python_3_14" in topics and "cyclic_imports" in topics
    topics = knowledge_topics_from_env_or_summary({"system": {}, "risks": ["god_module @ a.py"]})
    assert "python" in topics and "python_3_14" in topics and "architecture_refactor" in topics
    topics = knowledge_topics_from_env_or_summary({"system": {}, "risks": ["long_function @ foo.py"]})
    assert "pep_8" in topics


def test_doctor_runtime_reports_degraded_mode_when_llm_disabled(tmp_path: Path) -> None:
    """Doctor reports deterministic degraded mode metadata when running with --no-llm."""
    from eurika.orchestration.doctor import run_doctor_cycle

    _minimal_self_map(tmp_path / "self_map.json", ["a.py"], {})
    out = run_doctor_cycle(tmp_path, window=3, no_llm=True, online=False)
    runtime = out.get("runtime") or {}
    assert runtime.get("degraded_mode") is True
    assert "llm_disabled" in (runtime.get("degraded_reasons") or [])
    assert runtime.get("llm_used") is False
    assert runtime.get("use_llm") is False


def test_doctor_handles_network_unavailable_without_crash(tmp_path: Path) -> None:
    """Doctor should degrade gracefully when online knowledge fetch is unavailable."""
    import urllib.error

    from eurika.orchestration.doctor import run_doctor_cycle

    _minimal_self_map(tmp_path / "self_map.json", ["a.py"], {})
    with patch(
        "eurika.knowledge.base.urllib.request.urlopen",
        side_effect=urllib.error.URLError("network down"),
    ):
        out = run_doctor_cycle(tmp_path, window=3, no_llm=True, online=True)
    assert "error" not in out
    assert "summary" in out and "architect_text" in out
    runtime = out.get("runtime") or {}
    assert runtime.get("degraded_mode") is True
    assert "llm_disabled" in (runtime.get("degraded_reasons") or [])


def test_doctor_quiet_suppresses_progress_messages(tmp_path: Path) -> None:
    """R2 Logging: doctor --quiet suppresses progress messages to stderr."""
    _minimal_self_map(tmp_path / "self_map.json", ["a.py"], {})
    result = subprocess.run(
        [sys.executable, "-m", "eurika_cli", "doctor", "--no-llm", "--quiet", str(tmp_path)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0
    stderr = result.stderr or ""
    assert "loading summary" not in stderr
    assert "step 1/4" not in stderr
    assert "step 3/4" not in stderr
    assert "eurika_doctor_report.json written" not in stderr
    assert "ARCHITECTURE SUMMARY" in result.stdout or "architect" in result.stdout.lower()


def test_doctor_llm_unavailable_falls_back_to_template(tmp_path: Path) -> None:
    """R2 Fallback: when LLM is requested but all paths fail, doctor returns template with degraded_mode."""
    from eurika.orchestration.doctor import run_doctor_cycle

    _minimal_self_map(tmp_path / "self_map.json", ["a.py"], {})
    with patch(
        "eurika.reasoning.architect._llm_interpret",
        return_value=(None, "ollama CLI failed; ollama HTTP failed"),
    ):
        out = run_doctor_cycle(tmp_path, window=3, no_llm=False, online=False)
    assert "error" not in out
    assert "architect_text" in out and len(out["architect_text"]) > 0
    runtime = out.get("runtime") or {}
    assert runtime.get("degraded_mode") is True
    reasons = runtime.get("degraded_reasons") or []
    assert any("llm_unavailable" in r for r in reasons)


def test_doctor_suggested_policy_block(tmp_path: Path) -> None:
    """Doctor shows Suggested policy block when fix report has low apply_rate (ROADMAP 2.9.4)."""
    (tmp_path / "eurika_fix_report.json").write_text(
        json.dumps({"telemetry": {"apply_rate": 0.2, "rollback_rate": 0.0}}),
        encoding="utf-8",
    )
    (tmp_path / "self_map.json").write_text(
        json.dumps({
            "modules": [{"path": "a.py", "lines": 10}],
            "dependencies": {},
            "system": {"modules": 1, "dependencies": 0, "cycles": 0},
        }),
        encoding="utf-8",
    )
    result = subprocess.run(
        [sys.executable, "-m", "eurika_cli", "doctor", "--no-llm", str(tmp_path)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert "Suggested policy" in result.stdout, f"stdout: {result.stdout!r}\nstderr: {result.stderr!r}"
    assert "EURIKA_AGENT_MAX_OPS" in result.stdout or "export" in result.stdout


def test_doctor_includes_context_sources(tmp_path: Path) -> None:
    """Doctor output should include semantic context sources (ROADMAP 3.6.3)."""
    from eurika.orchestration.doctor import run_doctor_cycle

    (tmp_path / "self_map.json").write_text(
        json.dumps(
            {
                "modules": [{"path": "a.py", "lines": 10}, {"path": "b.py", "lines": 12}],
                "dependencies": {"a.py": ["b.py"]},
                "system": {"modules": 2, "dependencies": 1, "cycles": 0},
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_a.py").write_text("def test_a(): assert True\n", encoding="utf-8")
    out = run_doctor_cycle(tmp_path, window=3, no_llm=True, online=False)
    ctx = out.get("context_sources")
    assert isinstance(ctx, dict)
    assert "by_target" in ctx
    assert isinstance(ctx.get("by_target"), dict)
