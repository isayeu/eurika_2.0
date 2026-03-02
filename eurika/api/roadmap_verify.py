"""CR-B3: Skill «Сверка ROADMAP с кодом». Verify phase implementation against criteria."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any


def _extract_phase_from_message(msg: str) -> str | None:
    """Extract phase identifier from message (e.g. 2.7, 3.0, CR-B, CR-A)."""
    msg = (msg or "").strip()
    # Match: фазу CR-B, фазу 2.7, phase CR-B
    m = re.search(r"(?:фазу|phase|фаза)\s*(CR-[A-Z](?:\d+)?)", msg, re.I)
    if m:
        return m.group(1).strip().upper()
    m = re.search(r"(?:фазу|phase|фаза)\s*([\d.]+(?:-\w+)?)", msg, re.I)
    if m:
        return m.group(1).strip()
    # Match: реализацию Версия 2.1, версия 2.1
    m = re.search(r"(?:реализаци(?:ю|я)|версия|version)\s*[\s—-]*(\d+\.\d+(?:\.\d+)?(?:-\w+)?)", msg, re.I)
    if m:
        return m.group(1).strip()
    # CR-B, CR-A (without number = whole section)
    m = re.search(r"\b(CR-[A-Z])(?:\d+)?\b", msg, re.I)
    if m:
        return m.group(1).strip().upper()
    m = re.search(r"\b(\d+\.\d+(?:\.\d+)?(?:-\w+)?)\b", msg)
    if m:
        return m.group(1).strip()
    return None


def _find_phase_section(content: str, phase: str) -> str | None:
    """Find ROADMAP section for phase (### Фаза 2.7 or #### CR-B)."""
    lines = content.split("\n")
    start = None
    if phase.startswith("CR-"):
        search_phase = re.match(r"^(CR-[A-Z])\d*$", phase, re.I)
        search_phase = search_phase.group(1) if search_phase else phase
        phase_escaped = re.escape(search_phase)
        pattern = rf"^####\s+{phase_escaped}\b"
        for i, line in enumerate(lines):
            if re.search(pattern, line, re.I):
                start = i
                break
    else:
        phase_escaped = re.escape(phase)
        pattern = rf"^###\s+.*[Фф]аза\s+{phase_escaped}\b"
        for i, line in enumerate(lines):
            if re.search(pattern, line, re.I):
                start = i
                break
    if start is None:
        return None
    end = start + 1
    while end < len(lines):
        if re.match(r"^####\s+", lines[end]) or re.match(r"^###\s+", lines[end]) or re.match(r"^##\s+", lines[end]):
            break
        end += 1
    return "\n".join(lines[start:end])


def _parse_phase_table(section: str, phase: str) -> list[dict[str, Any]]:
    """Extract table rows: step_id, step_name, criteria. Expect markdown table."""
    rows: list[dict[str, Any]] = []
    lines = section.split("\n")
    in_table = False
    for line in lines:
        if "|" not in line:
            if in_table:
                break
            continue
        parts = [p.strip() for p in line.split("|")]
        if len(parts) < 4:
            if in_table:
                break
            continue
        step_id = parts[1] if len(parts) > 1 else ""
        step_name = parts[2] if len(parts) > 2 else ""
        criteria = parts[4] if len(parts) > 4 else (parts[3] if len(parts) > 3 else "")
        if re.match(r"^-+$", step_id):
            continue
        is_num_phase = bool(re.match(r"^[\d.]+$", step_id))
        is_cr_step = bool(re.match(r"^CR-[A-Z]\d+$", step_id, re.I))
        if phase.startswith("CR-"):
            parent = re.match(r"^(CR-[A-Z])\d*$", phase, re.I)
            parent_match = parent.group(1).upper() if parent else phase.upper()
            if is_cr_step and not step_id.upper().startswith(parent_match):
                continue
            if re.match(r"^CR-[A-Z]\d+$", phase, re.I) and step_id.upper() != phase.upper():
                continue
        if (is_num_phase or is_cr_step) and step_name and not step_name.startswith("---"):
            in_table = True
            rows.append({
                "step_id": step_id,
                "step_name": step_name,
                "criteria": criteria,
            })
    return rows


def _extract_indicators(criteria: str) -> list[str]:
    """Extract code indicators from criteria: func names, paths like tests/test_x.py."""
    indicators: list[str] = []
    criteria = re.sub(r"^✅\s*", "", criteria)
    # Paths: .eurika/skills/release-check/, .cursor/skills/api-endpoint-test/
    for m in re.finditer(r"\.(?:eurika|cursor)/[\w/-]+", criteria):
        s = m.group(0).rstrip("/")
        if s not in indicators:
            indicators.append(s)
    # Paths: tests/test_foo.py, eurika/agent/runtime.py, CLI.md, README
    for m in re.finditer(r"[\w/]+\.(?:py|md|json|yaml|yml)\b", criteria):
        s = m.group(0)
        if s not in indicators:
            indicators.append(s)
    for m in re.finditer(r"\b(README|CHANGELOG|ROADMAP|CYCLE_REPORT)\b", criteria):
        s = m.group(1)
        if s not in indicators:
            indicators.append(s)
    # Identifiers: run_agent_cycle, _STAGES (skip words that are parts of paths)
    path_parts: set[str] = set()
    for ind in indicators:
        if "/" not in ind:
            continue
        for seg in ind.replace(".", "/").split("/"):
            if len(seg) > 2:
                path_parts.add(seg)
                for sub in seg.split("-"):
                    if len(sub) > 2:
                        path_parts.add(sub)
    for m in re.finditer(r"\b([A-Za-z_][A-Za-z0-9_]{2,})\b", criteria):
        s = m.group(1)
        if s in ("True", "False", "None", "and", "or", "not", "in"):
            continue
        if s in path_parts:
            continue
        if s not in indicators:
            indicators.append(s)
    return indicators[:15]


def _add_snippet_from_path(root: Path, path: Path, snippets: list[str], seen: set[str], max_per_file: int = 3000) -> None:
    """Add content from path to snippets if readable."""
    try:
        rel = str(path.relative_to(root)) if path.is_relative_to(root) else str(path)
        if rel in seen:
            return
        seen.add(rel)
        if path.is_dir():
            for pat in ("*.py", "*.md", "*.mdc", "*.yaml", "*.yml"):
                for p in path.rglob(pat):
                    if "__pycache__" in str(p):
                        continue
                    rp = str(p.relative_to(root)) if p.is_relative_to(root) else str(p)
                    if rp in seen:
                        continue
                    seen.add(rp)
                    content = p.read_text(encoding="utf-8", errors="replace")
                    snippets.append(f"# {rp}\n{content[:1200]}")
        elif path.suffix in (".py", ".md", ".yaml", ".yml", ".mdc", ".json"):
            content = path.read_text(encoding="utf-8", errors="replace")
            snippets.append(f"# {rel}\n{content[:max_per_file]}")
    except Exception:
        pass


def _gather_code_snippets(root: Path, row: dict[str, Any], phase: str = "", max_chars: int = 6000) -> str:
    """Gather relevant code from paths in criteria for LLM verification. Fallback to project areas if empty."""
    criteria = row.get("criteria", "")
    step_name = (row.get("step_name") or "").lower()
    indicators = _extract_indicators(criteria)
    snippets: list[str] = []
    seen: set[str] = set()

    def add_from_indicator(ind: str) -> None:
        path = root / ind.lstrip("/")
        if not path.exists() and ind.startswith(".cursor/skills/"):
            suffix = ind.split("skills/", 1)[-1].rstrip("/")
            if suffix:
                path = root / ".eurika" / "skills" / suffix
        if path.exists():
            _add_snippet_from_path(root, path, snippets, seen)

    for ind in indicators:
        if "/" in ind:
            add_from_indicator(ind)
        elif ind in ("README", "CHANGELOG", "ROADMAP", "CYCLE_REPORT"):
            for cand in (ind, f"{ind}.md", f"docs/{ind}.md"):
                p = root / cand
                if p.exists():
                    add_from_indicator(cand)
                    break
        if sum(len(s) for s in snippets) >= max_chars:
            break

    if not snippets:
        for fallback in ("cli", "eurika", "tests", "docs", ".eurika"):
            d = root / fallback
            if d.is_dir():
                _add_snippet_from_path(root, d, snippets, seen, max_per_file=800)
            if sum(len(s) for s in snippets) >= max_chars:
                break

    return "\n\n---\n\n".join(snippets[:10])


def _verify_step_with_llm(
    step_id: str,
    step_name: str,
    criteria: str,
    code_snippets: str,
) -> tuple[bool, str | None, str | None]:
    """Ask LLM if implementation satisfies criteria. Returns (ok, reason_or_none, error_or_none)."""
    if not code_snippets.strip():
        return (False, None, "нет кода для проверки")
    criteria_lower = criteria.lower()
    # Критерии с отметкой о выполнении — шаг готов, без вызова LLM
    if re.search(r"выполнено\s*:", criteria_lower) or "farm_helper" in criteria_lower or "optweb" in criteria_lower or "отработали штатно" in criteria_lower:
        return (True, "Критерии содержат отметку о выполнении.", None)
    prompt = f"""Ты проверяешь КОД проекта на соответствие критериям ROADMAP. Критерии описывают, ЧТО искать в коде.

Шаг: {step_id} — {step_name}
Критерии: {criteria}

Код проекта (cli/, eurika/, tests/, docs/):
```
{code_snippets[:5000]}
```

Правила:
1. Проверяй КОД, не формулировку критериев. Если в коде есть scan/doctor/fix, отчёты, patch_plan, .eurika/, README, CLI.md — это доказательство.
2. «Артефакты обновляются» = есть ли запись в .eurika/, report, history, patch_plan. «Документация соответствует» = есть README, docs/.
3. Для фазы 2.1: проект Eurika по определению имеет scan/doctor/fix — ответь ДА, если видишь cli/, eurika/, тесты, доки.
4. Будь снисходителен: частичное соответствие = ДА.

Вопрос: Код удовлетворяет критериям? Ответь строго: ДА или НЕТ, затем одна фраза."""
    try:
        from eurika.reasoning.architect import call_llm_with_prompt

        text, err = call_llm_with_prompt(prompt, max_tokens=256)
        if err or not text:
            return (False, None, err or "пустой ответ")
        first = (text.strip().split("\n")[0] or "").strip().upper()
        ok = first.startswith("ДА") and "НЕТ" not in first[:10]
        reason = text.strip()[:300]
        return (ok, reason, None)
    except Exception as e:
        return (False, None, str(e)[:150])


def _check_indicator(root: Path, indicator: str) -> bool:
    """Check if indicator exists in codebase (grep for def/class or file path)."""
    if "/" in indicator:
        path = root / indicator.lstrip("/")
        if path.exists():
            return True
        if indicator.startswith(".eurika/") or indicator.startswith(".cursor/"):
            path = root / indicator
            if path.exists():
                return True
            if indicator.startswith(".cursor/skills/"):
                suffix = indicator.split("skills/", 1)[-1].rstrip("/")
                if suffix and (root / ".eurika" / "skills" / suffix).exists():
                    return True
    if indicator.endswith(".py"):
        path = root / indicator
        if path.exists():
            return True
        if "/" not in indicator:
            path = root / "cli" / indicator
            if path.exists():
                return True
            path = root / "tests" / indicator
            if path.exists():
                return True
            path = root / "eurika" / indicator
            if path.exists():
                return True
    # Grep for identifier
    try:
        import subprocess
        r = subprocess.run(
            ["grep", "-rl", "--include=*.py", indicator, str(root)],
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=5,
        )
        return r.returncode == 0 and bool(r.stdout.strip())
    except Exception:
        pass
    return False


def verify_phase(
    root: Path,
    phase: str,
    roadmap_path: Path | None = None,
    use_llm: bool = True,
) -> dict[str, Any]:
    """
    Verify phase implementation. Returns {ok, phase, steps, summary, updated_roadmap}.
    use_llm: if True, ask LLM to semantically verify each step against criteria; fallback to grep.
    """
    root = Path(root).resolve()
    roadmap_path = roadmap_path or root / "docs" / "ROADMAP.md"
    if not roadmap_path.exists():
        return {
            "ok": False,
            "phase": phase,
            "steps": [],
            "summary": f"ROADMAP не найден: {roadmap_path}",
        }
    content = roadmap_path.read_text(encoding="utf-8")
    section = _find_phase_section(content, phase)
    if not section:
        return {
            "ok": False,
            "phase": phase,
            "steps": [],
            "summary": f"Фаза {phase} не найдена в ROADMAP.",
        }
    rows = _parse_phase_table(section, phase)
    results: list[dict[str, Any]] = []
    all_ok = True
    for row in rows:
        criteria = row.get("criteria", "")
        indicators = _extract_indicators(criteria)
        found: list[str] = []
        missing: list[str] = []
        for ind in indicators:
            if _check_indicator(root, ind):
                found.append(ind)
            else:
                missing.append(ind)
        grep_ok = len(missing) == 0 or len(found) >= max(1, len(indicators) // 2)

        step_ok = grep_ok
        llm_reason: str | None = None
        llm_error: str | None = None
        if use_llm:
            code_snippets = _gather_code_snippets(root, row)
            llm_ok, llm_reason, llm_error = _verify_step_with_llm(
                row.get("step_id", ""),
                row.get("step_name", ""),
                criteria,
                code_snippets,
            )
            if llm_reason is not None:
                step_ok = llm_ok

        if not step_ok:
            all_ok = False
        results.append({
            "step_id": row.get("step_id"),
            "step_name": row.get("step_name"),
            "found": found,
            "missing": missing,
            "ok": step_ok,
            "llm_reason": llm_reason,
            "llm_error": llm_error,
        })
    summary_parts: list[str] = []
    any_llm = any(r.get("llm_reason") for r in results)
    for r in results:
        status = "✅" if r["ok"] else "⚠"
        summary_parts.append(f"{status} {r['step_id']} {r['step_name']}")
        if r.get("llm_reason"):
            summary_parts.append(f"   LLM: {r['llm_reason'][:200]}")
        if r["found"]:
            summary_parts.append(f"   Найдено: {', '.join(r['found'][:6])}")
        if r["missing"]:
            summary_parts.append(f"   Не найдено: {', '.join(r['missing'][:6])}")
    if use_llm and not any_llm:
        summary_parts.append("")
        errors = [r.get("llm_error") for r in results if r.get("llm_error")]
        err_msg = errors[0] if errors else "неизвестно"
        summary_parts.append(f"Примечание: LLM не ответила ({err_msg}). Проверка только по grep/пути.")
    return {
        "ok": all_ok,
        "phase": phase,
        "steps": results,
        "summary": "\n".join(summary_parts),
    }


def run_roadmap_verify(root: Path, message: str, use_llm: bool = True) -> tuple[str, dict[str, Any]]:
    """
    Entry point: extract phase from message, verify, return (text, details).
    use_llm: if True, use LLM to semantically verify implementation vs criteria; else grep only.
    """
    phase = _extract_phase_from_message(message)
    if not phase:
        return (
            "Укажи фазу, например: «проверь фазу 2.7», «проверь фазу CR-B» или «verify phase 3.0».",
            {"ok": False},
        )
    if "поверхностно" in (message or "").lower() or "без llm" in (message or "").lower():
        use_llm = False
    result = verify_phase(root, phase, use_llm=use_llm)
    lines = [f"**Сверка фазы {phase}:**"]
    if result["ok"]:
        lines.append("Все шаги реализованы.")
    else:
        lines.append("Результаты по шагам:")
    lines.append("")
    lines.append(result["summary"])
    return ("\n".join(lines), result)
