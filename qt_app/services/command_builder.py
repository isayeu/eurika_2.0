"""Build validated CLI argument vectors for Qt command execution."""

from __future__ import annotations

from pathlib import Path


SUPPORTED_COMMANDS = {"scan", "doctor", "fix", "cycle", "explain", "report-snapshot", "learning-kpi"}


def build_cli_args(
    *,
    command: str,
    project_root: str,
    module: str = "",
    window: int = 5,
    dry_run: bool = False,
    no_llm: bool = False,
    no_clean_imports: bool = False,
    team_mode: bool = False,
) -> list[str]:
    """Return argument vector for `python -m eurika_cli` execution."""
    if command not in SUPPORTED_COMMANDS:
        raise ValueError(f"Unsupported command: {command}")
    if not project_root.strip():
        raise ValueError("project_root is required")

    root = str(Path(project_root).resolve())
    args = [command]

    if command == "explain":
        if not module.strip():
            raise ValueError("module is required for explain command")
        args.append(module.strip())
        args.append(root)
        if window > 0:
            args.extend(["--window", str(window)])
        return args

    args.append(root)
    if command in {"report-snapshot", "learning-kpi"}:
        return args
    if command in {"doctor", "fix", "cycle"} and window > 0:
        args.extend(["--window", str(window)])
    if command in {"doctor", "cycle"} and no_llm:
        args.append("--no-llm")
    if command in {"fix", "cycle"} and dry_run:
        args.append("--dry-run")
    if command in {"fix", "cycle"} and no_clean_imports:
        args.append("--no-clean-imports")
    if command in {"fix", "cycle"} and team_mode:
        args.append("--team-mode")
    return args

