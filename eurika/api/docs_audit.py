"""Chat skill: audit docs vs reality (VISION / ROADMAP / live signals).

Uses cloud/local LLM via ``call_llm_with_prompt`` when available; otherwise a
deterministic fallback from VISION backlog checkmarks.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def _read_capped(path: Path, *, max_chars: int) -> str:
    if not path.is_file():
        return ""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    text = text.strip()
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 20].rstrip() + "\n…[truncated]"


def _self_map_blurb(root: Path) -> str:
    path = root / "self_map.json"
    if not path.is_file():
        return "self_map.json: отсутствует (сделай scan)."
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return "self_map.json: не читается."
    if not isinstance(data, dict):
        return "self_map.json: неожиданный формат."
    mods = data.get("modules")
    n_mods: int | str
    if isinstance(mods, list):
        n_mods = len(mods)
    elif isinstance(mods, (int, float)):
        n_mods = int(mods)
    else:
        try:
            parsed = int(data.get("n_modules") or 0)
            n_mods = parsed if parsed else "?"
        except (TypeError, ValueError):
            n_mods = "?"
    deps = data.get("dependencies")
    n_deps = len(deps) if isinstance(deps, list) else data.get("n_dependencies", "?")
    smells = data.get("smells") or data.get("findings") or []
    n_smells: int | str
    if isinstance(smells, list) and smells:
        n_smells = len(smells)
    else:
        # self_map often has no smells list — use last architecture history point.
        n_smells = "?"
        hist = root / ".eurika" / "history.json"
        if hist.is_file():
            try:
                hdata = json.loads(hist.read_text(encoding="utf-8"))
                points = None
                if isinstance(hdata, dict):
                    points = hdata.get("history") or hdata.get("points")
                elif isinstance(hdata, list):
                    points = hdata
                if isinstance(points, list) and points:
                    last = points[-1]
                    if isinstance(last, dict) and last.get("total_smells") is not None:
                        n_smells = int(last["total_smells"])
            except (OSError, json.JSONDecodeError, TypeError, ValueError):
                pass
    summary = data.get("summary") if isinstance(data.get("summary"), dict) else {}
    cycles = summary.get("cycles", "?") if summary else "?"
    return f"self_map: modules={n_mods}, deps={n_deps}, cycles={cycles}, smells≈{n_smells}"


def _vision_fallback(vision_text: str, root: Path | None = None) -> str:
    """No-LLM: extract backlog lines with ✅ / partial / open from VISION."""
    lines_out = [
        "**Аудит по docs/VISION.md (без LLM — шаблон):**",
        "",
        "### Сделано / частично (по отметкам в VISION)",
    ]
    done: list[str] = []
    open_items: list[str] = []
    for raw in vision_text.splitlines():
        line = raw.strip()
        if not line.startswith(("1.", "2.", "3.", "4.", "5.", "6.", "7.", "8.", "9.", "10.", "11.", "12.", "13.")):
            if line.startswith(("- ", "* ")) and ("✅" in line or "частично" in line.lower() or "Не трогать" in line):
                pass
            else:
                continue
        if "✅" in line or "частично" in line.lower():
            done.append(line)
        elif line.startswith(("6.", "10.", "11.", "12.")) or "Не трогать" in line or "Позже" in line:
            open_items.append(line)
        elif "**" in line and "✅" not in line:
            # numbered backlog without checkmark
            if any(line.startswith(f"{n}.") for n in range(1, 14)):
                if "частично" in line.lower() or "✅" in line:
                    done.append(line)
                else:
                    open_items.append(line)
    for item in done[:12]:
        lines_out.append(f"- {item}")
    if open_items:
        lines_out.append("")
        lines_out.append("### Открыто / не сейчас")
        for item in open_items[:10]:
            lines_out.append(f"- {item}")
    lines_out.append("")
    lines_out.append("### Следующие 1–2 шага (non-Market)")
    dev = (Path(root) / "docs" / "DEVELOPMENT.md") if root is not None else None
    if dev is not None and dev.is_file():
        lines_out.append("- См. `docs/DEVELOPMENT.md` § Текущий фокус (не застывший VISION A1).")
    else:
        lines_out.append("- VISION backlog A→B→C; не выдумывать следующий шаг.")
    lines_out.append("- Market только наблюдать journal; без нового entry / explore / HTF / live.")
    lines_out.append("")
    lines_out.append(
        "Для живого разбора с Groq/Ollama повтори запрос при доступном LLM "
        "(Models → API preset / ключ в `.env`)."
    )
    return "\n".join(lines_out)


def build_docs_audit_prompt(root: Path) -> str:
    vision = _read_capped(root / "docs" / "VISION.md", max_chars=9000)
    development = _read_capped(root / "docs" / "DEVELOPMENT.md", max_chars=4000)
    memory = _read_capped(root / "docs" / "MEMORY.md", max_chars=4000)
    chat = _read_capped(root / "docs" / "CHAT.md", max_chars=2500)
    blurb = _self_map_blurb(root)
    return (
        "Ты Eurika — локальный архитектурный ассистент. Сверь docs с реальностью и "
        "дай краткий статус бэклога.\n"
        "Текущий фокус разработки: **docs/DEVELOPMENT.md**. "
        "Компас продукта: **docs/VISION.md** (✅ / частично / Не трогать / Не сейчас). "
        "MEMORY/CHAT — только уточнения; не предлагай инфраструктуру из старых планов "
        "(MetricVector, EnergyModel, ExperienceStore, «упростить ядро»), если DEVELOPMENT/VISION "
        "этого не ставят следующим шагом — это уже в коде.\n"
        "Правила:\n"
        "- **Сделано** = пункты VISION с ✅ или явно реализованный слой (shell/agent/learning).\n"
        "- **Частично** = только то, где VISION пишет «частично».\n"
        "- **Не сделано / не сейчас** = HTF (не трогать), walk-forward, "
        "live-ордера, explore on, новый entry, большой рефактор вкладок.\n"
        "- Market: не предлагай новый entry/HTF/explore/live; market сейчас = наблюдение journal.\n"
        "- **Следующие 1–2 шага**: из `docs/DEVELOPMENT.md` § Текущий фокус "
        "(сейчас CR-H H4), не RV11 и не застывший A1 — максимум два пункта.\n"
        "- Ответ на русском; без воды; ≤20 коротких пунктов суммарно; не выдумывай фичи.\n\n"
        f"## Live\n{blurb}\n\n"
        f"## docs/DEVELOPMENT.md\n{development or '(нет файла)'}\n\n"
        f"## docs/VISION.md\n{vision or '(нет файла)'}\n\n"
        f"## docs/MEMORY.md (фрагмент)\n{memory or '(нет)'}\n\n"
        f"## docs/CHAT.md (фрагмент)\n{chat or '(нет)'}\n"
    )


def run_docs_audit(root: Path, *, use_llm: bool = True) -> tuple[str, dict[str, Any]]:
    """Return (chat text, meta)."""
    root = Path(root)
    vision_path = root / "docs" / "VISION.md"
    vision_text = _read_capped(vision_path, max_chars=12000) if vision_path.is_file() else ""
    meta: dict[str, Any] = {"ok": True, "source": "fallback", "self_map": _self_map_blurb(root)}
    if use_llm:
        try:
            from eurika.reasoning.architect import call_llm_with_prompt

            prompt = build_docs_audit_prompt(root)
            text, err = call_llm_with_prompt(prompt, max_tokens=1200)
            if text and text.strip():
                meta["source"] = "llm"
                # Keep header tiny — never dump self_map modules into the chat.
                header = f"_Аудит документации (LLM) · {meta['self_map']}_\n\n"
                body = text.strip()
                if len(body) > 8000:
                    body = body[:8000].rstrip() + "\n…[truncated]"
                return header + body, meta
            meta["llm_error"] = err or "empty"
        except Exception as exc:  # noqa: BLE001 — best-effort chat skill
            meta["llm_error"] = str(exc)
    fallback = _vision_fallback(vision_text, root) if vision_text else (
        "Нет docs/VISION.md — не могу сверить бэклог. Сначала открой корень Eurika."
    )
    meta["ok"] = bool(vision_text)
    meta["source"] = "fallback"
    return fallback, meta
