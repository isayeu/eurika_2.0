"""Tests for host OS health probe (distinct from project self-check)."""

from __future__ import annotations

from eurika.api.host_health import (
    HostHealthResult,
    _disk_line_relevant,
    advice_from_facts,
    format_host_health_for_chat,
    run_host_health_probe,
    summarize_journal,
)


def test_run_host_health_probe_smoke() -> None:
    result = run_host_health_probe(timeout_per_step=8.0)
    assert result.level in {"ok", "attention", "bad"}
    assert "HOST HEALTH" in result.output
    assert "uname" in result.output.lower() or "=== uname ===" in result.output
    text = format_host_health_for_chat(result)
    assert "Здоровье ОС" in text
    assert "не проекта" in text.lower() or "Eurika" in text
    assert "Советы:" in text
    # Chat must not dump raw journal stacks / full probe.
    assert "Stack trace of thread" not in text
    assert "=== HOST HEALTH" not in text


def test_summarize_journal_collapses_coredumps() -> None:
    raw = """
июл 31 kernel: ntfs3(sdc1): failed to read volume
июл 31 systemd-coredump: Process 1 (eurika-qt) of user 1000 dumped core.
Stack trace of thread 1:
#0 0xabc n/a (libc.so.6)
#1 0xdef raise
Module libfoo.so without build-id.
ELF object binary architecture: AMD x86-64
авг 01 bluetoothd: No SDP records
""".strip()
    compact, facts = summarize_journal(raw)
    assert "Stack trace of thread" not in compact
    assert "eurika-qt" in compact.lower() or any("coredump" in f for f in facts)
    assert any("NTFS" in f or "ntfs" in f.lower() or "I/O" in f for f in facts)


def test_disk_skips_efivarfs() -> None:
    cols = "efivarfs 128K 118K 5,6K 96% /sys/firmware/efi/efivars".split()
    assert _disk_line_relevant(cols) is False
    root = "/dev/mapper/root 119G 47G 71G 40% /".split()
    assert _disk_line_relevant(root) is True


def test_efivarfs_not_in_chat_facts_as_full_disk() -> None:
    """Pseudo FS at 96% must not mark host bad via format path (unit via advice)."""
    result = HostHealthResult(
        ok=True,
        level="attention",
        output="=== HOST HEALTH ===\nefivarfs 96%\n=== done ===",
        facts=("swap used: 1,9Gi", "pacman pending: 154", "gpu: NVIDIA GeForce 940MX"),
    )
    text = format_host_health_for_chat(result)
    assert "Здоровье ОС" in text
    assert "Советы:" in text
    assert "Swap" in text or "swap" in text.lower()
    assert "=== HOST HEALTH ===" not in text
    tips = advice_from_facts(result.level, result.facts)
    assert any("Swap" in t or "swap" in t.lower() for t in tips)


def test_ntfs_fact_does_not_trigger_disk_fullness_tip() -> None:
    facts = (
        "swap used: 1,9Gi",
        "storage I/O / NTFS errors: 25 (часто сменный/битый том)",
        "coredumps this boot: 1 (часто eurika-qt на выходе)",
        "pacman pending: 154",
        "gpu: NVIDIA GeForce 940MX",
    )
    tips = advice_from_facts("attention", facts)
    joined = "\n".join(tips).lower()
    assert "ntfs" in joined or "i/o" in joined
    assert "почти заполнен" not in joined
    assert "до >90%" not in joined
    assert tips[0].lower().startswith("главный риск") or "ntfs" in tips[0].lower()
