"""Host OS health probe for Chat (Arch/Linux) — read-only, fixed commands.

Distinct from ``eurika self-check`` (project/env). Terminal mirror uses the same
fixed shell snippet; never interpolate user text into the command.

Chat gets a short verdict + facts + advice; Terminal gets the probe log
(journal stacks collapsed). Never put the raw dump into the chat ``error`` field.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from dataclasses import dataclass
from typing import List, Sequence, Tuple

# Fixed script for Qt Terminal / run_command_with_result (no user input).
HOST_HEALTH_SHELL = r"""set +e
echo "=== HOST HEALTH (read-only) ==="
echo "=== uname ==="
uname -a
echo "=== uptime ==="
uptime
echo "=== loadavg ==="
cat /proc/loadavg 2>/dev/null || true
echo "=== memory ==="
free -h 2>/dev/null || true
echo "=== disk ==="
df -h -x tmpfs -x devtmpfs 2>/dev/null | head -n 30 || true
echo "=== inodes ==="
df -i -x tmpfs -x devtmpfs 2>/dev/null | head -n 20 || true
echo "=== failed units ==="
systemctl --failed --no-pager --plain 2>/dev/null | head -n 40 || echo "(systemctl unavailable)"
echo "=== journal errors (boot, last 40) ==="
journalctl -p err -b -n 40 --no-pager -o short-iso 2>/dev/null | tail -n 40 || echo "(journalctl unavailable)"
if command -v nvidia-smi >/dev/null 2>&1; then
  echo "=== nvidia-smi ==="
  nvidia-smi --query-gpu=name,driver_version,memory.total,memory.used,utilization.gpu --format=csv,noheader 2>/dev/null || nvidia-smi -L 2>/dev/null || true
fi
if command -v checkupdates >/dev/null 2>&1; then
  echo "=== pacman updates (checkupdates) ==="
  checkupdates 2>/dev/null | wc -l | awk '{print "pending_packages: "$1}'
fi
echo "=== done ==="
"""

_DISK_SKIP_MOUNTS = frozenset(
    {
        "/sys/firmware/efi/efivars",
        "/sys",
        "/proc",
        "/dev",
        "/run",
        "/dev/shm",
    }
)
_DISK_SKIP_FS = frozenset(
    {"efivarfs", "tmpfs", "devtmpfs", "squashfs", "overlay", "fuse", "fusectl", "tracefs"}
)


@dataclass(frozen=True)
class HostHealthResult:
    ok: bool
    level: str  # ok | attention | bad
    output: str
    facts: Tuple[str, ...]


def _run_argv(argv: Sequence[str], *, timeout: float = 15.0) -> Tuple[int, str]:
    try:
        r = subprocess.run(
            list(argv),
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        out = ((r.stdout or "") + (r.stderr or "")).strip()
        return int(r.returncode), out
    except FileNotFoundError:
        return 127, f"(not found: {argv[0]})"
    except subprocess.TimeoutExpired:
        return -1, f"(timeout: {' '.join(argv)})"
    except Exception as exc:
        return -1, f"({type(exc).__name__}: {exc})"


def _section(title: str, body: str) -> str:
    body = (body or "").strip() or "(empty)"
    return f"=== {title} ===\n{body}"


def _disk_line_relevant(cols: Sequence[str]) -> bool:
    """Skip pseudo FS (efivarfs etc.) so 96% there is not 'host bad'."""
    if not cols:
        return False
    fs = cols[0].lower()
    if fs in _DISK_SKIP_FS or fs.startswith("fuse."):
        return False
    mount = cols[-1]
    if mount in _DISK_SKIP_MOUNTS:
        return False
    if mount.startswith(("/sys/", "/proc/", "/dev/", "/run/")) and mount != "/run/media":
        # Allow /run/media/... removable; skip other /run/*
        if not mount.startswith("/run/media"):
            return False
    return True


def summarize_journal(raw: str, *, max_lines: int = 25) -> Tuple[str, List[str]]:
    """Collapse coredump stacks; return compact log + fact hints."""
    facts: List[str] = []
    if not (raw or "").strip():
        return "(empty)", facts
    out_lines: List[str] = []
    coredumps = 0
    ntfs_errs = 0
    skip_stack = False
    for line in raw.splitlines():
        low = line.lower()
        if "dumped core" in low or "systemd-coredump" in low:
            coredumps += 1
            skip_stack = True
            if "eurika-qt" in low:
                out_lines.append("… systemd-coredump: eurika-qt dumped core (Qt/PySide exit)")
            elif "Process" in line or "process" in low:
                out_lines.append(line[:160])
            else:
                out_lines.append(line[:160])
            continue
        if skip_stack:
            if (
                line.startswith("Stack trace")
                or line.startswith("#")
                or line.startswith("Module ")
                or "ELF object" in line
                or not line.strip()
            ):
                continue
            skip_stack = False
        if "ntfs3" in low or "critical target error" in low:
            ntfs_errs += 1
            if ntfs_errs <= 3:
                out_lines.append(line[:200])
            continue
        out_lines.append(line[:240])
        if len(out_lines) >= max_lines:
            out_lines.append("…")
            break
    if coredumps:
        facts.append(f"coredumps this boot: {coredumps} (часто eurika-qt на выходе)")
    if ntfs_errs:
        facts.append(f"storage I/O / NTFS errors: {ntfs_errs} (часто сменный/битый том)")
    return "\n".join(out_lines) if out_lines else "(empty)", facts


def _fact_is_disk_fullness(fact: str) -> bool:
    """True for 'disk / 96% full', not for storage I/O / NTFS lines."""
    f = fact.lower()
    return f.startswith("disk ") and "%" in f and ("full" in f or "used" in f)


def advice_from_facts(level: str, facts: Sequence[str]) -> List[str]:
    """Deterministic tips; LLM may add a short narrative on top."""
    tips: List[str] = []
    joined = " | ".join(facts).lower()
    if level == "ok":
        tips.append("Для разработки (Qt, paper, Ollama на CPU) хост выглядит рабочим.")
    # Priority: real storage damage first.
    if "ntfs" in joined or "storage i/o" in joined:
        tips.append(
            "Главный риск: ошибки NTFS/I/O (часто sdc) — не монтируй повреждённый том; "
            "бэкапы важного с /mnt/storage."
        )
    if "swap used" in joined:
        tips.append(
            "Swap частично занят — при тормозах закрой тяжёлые вкладки/IDE; для спокойной "
            "работы Ollama/Qt желательно держать RAM свободнее."
        )
    if any(_fact_is_disk_fullness(f) for f in facts):
        tips.append("Раздел почти заполнен — освободи место на / или /mnt/storage до >90%.")
    if "coredump" in joined or "eurika-qt" in joined:
        tips.append(
            "Coredump eurika-qt при выходе (Qt/PySide) — шум приложения, не признак «сломанной ОС»."
        )
    if "pacman pending" in joined:
        tips.append(
            "Много отложенных обновлений pacman — планируй обновление в удобное окно "
            "(не в середине цикла)."
        )
    if "gpu:" in joined and "940mx" in joined:
        tips.append(
            "GPU 940MX ок для лёгкого inference; тяжёлый CUDA PyTorch лучше не ждать — CPU/cloud LLM."
        )
    if "load1 high" in joined:
        tips.append("Load высокий — не гоняй параллельно scan+doctor+live paper без нужды.")
    if level == "bad":
        tips.append("Есть критичные сигналы (диск почти полный и т.п.) — разбери их до тяжёлой нагрузки.")
    if level == "attention" and "ntfs" not in joined and "storage i/o" not in joined:
        tips.append("Для Qt/paper хост в целом пригоден; пункты выше — плановые, не авария.")
    if not tips:
        tips.append("Критичных блокеров по probe не видно; полный лог — в Terminal.")
    return tips


def run_host_health_probe(*, timeout_per_step: float = 15.0) -> HostHealthResult:
    """Run fixed read-only probes; never uses user-supplied strings."""
    parts: List[str] = ["=== HOST HEALTH (read-only) ==="]
    facts: List[str] = []
    attention = False
    bad = False

    _code, out = _run_argv(["uname", "-a"], timeout=timeout_per_step)
    parts.append(_section("uname", out))
    if out:
        bits = out.split()
        facts.append(f"kernel: {bits[2] if len(bits) > 2 else out[:80]}")

    _code, out = _run_argv(["uptime"], timeout=timeout_per_step)
    parts.append(_section("uptime", out))
    if out:
        facts.append(f"uptime: {out.strip()}")

    _code, out = _run_argv(["bash", "-c", "cat /proc/loadavg"], timeout=timeout_per_step)
    parts.append(_section("loadavg", out))
    try:
        load1 = float((out or "0").split()[0])
        if load1 >= 8.0:
            attention = True
            facts.append(f"load1 high: {load1}")
    except (TypeError, ValueError, IndexError):
        pass

    _code, out = _run_argv(["free", "-h"], timeout=timeout_per_step)
    parts.append(_section("memory", out))
    for line in (out or "").splitlines():
        low = line.lower()
        if low.startswith("swap:") or low.startswith("своп:"):
            cols = line.split()
            if len(cols) >= 3 and cols[2] not in {"0B", "0", "0Ki", "0Mi", "0,0"}:
                attention = True
                facts.append(f"swap used: {cols[2]}")

    _code, out = _run_argv(
        ["bash", "-c", "df -h -x tmpfs -x devtmpfs 2>/dev/null | head -n 30"],
        timeout=timeout_per_step,
    )
    parts.append(_section("disk", out))
    for line in (out or "").splitlines()[1:]:
        cols = line.split()
        if len(cols) >= 5 and cols[4].endswith("%") and _disk_line_relevant(cols):
            try:
                pct = int(cols[4].rstrip("%"))
                mount = cols[-1]
                if pct >= 95:
                    bad = True
                    facts.append(f"disk {mount} {pct}% full")
                elif pct >= 85:
                    attention = True
                    facts.append(f"disk {mount} {pct}% used")
            except ValueError:
                pass

    _code, out = _run_argv(
        ["bash", "-c", "df -i -x tmpfs -x devtmpfs 2>/dev/null | head -n 20"],
        timeout=timeout_per_step,
    )
    parts.append(_section("inodes", out))

    if shutil.which("systemctl"):
        _code, out = _run_argv(
            ["systemctl", "--failed", "--no-pager", "--plain"],
            timeout=timeout_per_step,
        )
        parts.append(_section("failed units", out))
        lines = [ln for ln in (out or "").splitlines() if ln.strip() and "UNIT" not in ln]
        real = [ln for ln in lines if "loaded units listed" not in ln.lower()]
        if real:
            attention = True
            facts.append(f"failed units: {len(real)}")
    else:
        parts.append(_section("failed units", "(systemctl unavailable)"))

    if shutil.which("journalctl"):
        _code, out = _run_argv(
            ["journalctl", "-p", "err", "-b", "-n", "40", "--no-pager", "-o", "short-iso"],
            timeout=max(timeout_per_step, 20.0),
        )
        compact, jfacts = summarize_journal(out or "")
        parts.append(_section("journal errors (boot, summarized)", compact))
        for jf in jfacts:
            facts.append(jf)
            attention = True
        err_lines = [ln for ln in (out or "").splitlines() if ln.strip()]
        if len(err_lines) >= 15 and not jfacts:
            attention = True
            facts.append(f"journal err lines: {len(err_lines)}")
    else:
        parts.append(_section("journal errors", "(journalctl unavailable)"))

    if shutil.which("nvidia-smi"):
        _code, out = _run_argv(
            [
                "nvidia-smi",
                "--query-gpu=name,driver_version,memory.total,memory.used,utilization.gpu",
                "--format=csv,noheader",
            ],
            timeout=timeout_per_step,
        )
        if _code != 0 or not out:
            _code, out = _run_argv(["nvidia-smi", "-L"], timeout=timeout_per_step)
        parts.append(_section("nvidia-smi", out))
        if out and _code == 0:
            facts.append(f"gpu: {out.splitlines()[0][:100]}")
    else:
        facts.append("gpu: nvidia-smi not found (CPU or other GPU stack)")

    if shutil.which("checkupdates"):
        _code, out = _run_argv(
            ["bash", "-c", "checkupdates 2>/dev/null | wc -l"],
            timeout=max(timeout_per_step, 60.0),
        )
        parts.append(_section("pacman updates (count)", f"pending_packages: {(out or '0').strip()}"))
        try:
            n = int((out or "0").strip() or "0")
            if n >= 100:
                attention = True
            if n > 0:
                facts.append(f"pacman pending: {n}")
        except ValueError:
            pass

    parts.append("=== done ===")
    level = "bad" if bad else ("attention" if attention else "ok")
    ok = level != "bad"
    if not facts:
        facts.append(f"level={level}")
    return HostHealthResult(ok=ok, level=level, output="\n".join(parts), facts=tuple(facts))


def format_host_health_for_chat(result: HostHealthResult) -> str:
    """Chat summary: verdict + facts + advice. No raw journal dump."""
    label = {"ok": "OK", "attention": "внимание", "bad": "проблемы"}.get(result.level, result.level)
    lines = [
        f"**Здоровье ОС (хост):** {label}",
        "",
        "Это проверка **системы** (Arch/Linux), не проекта Eurika.",
        "Для проекта: «проведи self-check» / «что за проект?» / scan.",
        "",
    ]
    if result.facts:
        lines.append("Факты:")
        for f in result.facts[:14]:
            lines.append(f"- {f}")
        lines.append("")
    tips = advice_from_facts(result.level, result.facts)
    lines.append("Советы:")
    for t in tips:
        lines.append(f"- {t}")
    lines.append("")
    lines.append("Полный (сжатый) лог probe — во вкладке **Terminal**.")
    return "\n".join(lines)


def enrich_host_health_with_llm(facts_text: str, *, use_llm: bool = True) -> str:
    """Optional Groq/Ollama 2–4 sentence interpretation; falls back to facts_text."""
    if not use_llm:
        return facts_text
    prompt = (
        "Ты помощник Eurika — эксперт по Linux/Arch для разработчика. "
        "Ниже факты и советы health-check хоста. "
        "Напиши по-русски 2–4 спокойных предложения (с пробелами после точек): "
        "1) пригоден ли хост для Qt/Ollama/paper; "
        "2) главный риск (если есть storage I/O/NTFS — начни с него); "
        "3) что шум (coredump eurika-qt при quit — не ОС). "
        "Приоритет: storage I/O/NTFS > диск % full > swap > pacman > coredump. "
        "Если нет 'load1 high' — не говори про высокую нагрузку CPU. "
        "Если уровень 'внимание' — не пиши 'немедленно/авария'. "
        "Не путай с репозиторием Eurika. Не выдумывай цифры. Не повторяй списки.\n\n"
        f"{facts_text[:2800]}"
    )
    try:
        from eurika.reasoning.architect import call_llm_with_prompt

        text, err = call_llm_with_prompt(prompt, max_tokens=280)
        narrative = (text or "").strip()
        if err or not narrative:
            return facts_text
        # Soft-fix "word.Word" glue from some LLM outputs.
        narrative = re.sub(r"\.([A-ZА-ЯЁ])", r". \1", narrative)
        return f"{facts_text}\n\n**Заключение (LLM):**\n{narrative}"
    except Exception:
        return facts_text


def host_health_shell_command() -> str:
    """Single fixed shell string for Terminal mirror."""
    return HOST_HEALTH_SHELL.strip()
