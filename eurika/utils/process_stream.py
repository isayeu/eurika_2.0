"""Stream a shell command line-by-line (Chat → Terminal)."""
from __future__ import annotations

import subprocess
from collections.abc import Callable
from typing import Optional

from eurika.utils.env import child_process_environ

OnChunk = Callable[[str], None]
ShouldStop = Callable[[], bool]


def run_streamed_command(
    cmd: str,
    *,
    cwd: str,
    on_chunk: Optional[OnChunk] = None,
    should_stop: Optional[ShouldStop] = None,
) -> tuple[str, int]:
    """Run ``bash -c cmd``; call ``on_chunk`` for each line (including newline)."""
    shell = (cmd or "").strip()
    if not shell:
        return "", -1
    env = child_process_environ()
    try:
        proc = subprocess.Popen(
            ["bash", "-c", shell],
            cwd=cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            env=env,
        )
    except OSError as exc:
        return str(exc), -1
    chunks: list[str] = []
    stream = proc.stdout
    try:
        if stream is not None:
            for line in stream:
                chunks.append(line)
                if on_chunk is not None:
                    on_chunk(line)
                if should_stop is not None and should_stop():
                    proc.terminate()
                    try:
                        proc.wait(timeout=3)
                    except subprocess.TimeoutExpired:
                        proc.kill()
                        proc.wait()
                    return ("".join(chunks).strip(), -1)
        code = proc.wait()
    except Exception as exc:
        try:
            proc.kill()
            proc.wait()
        except Exception:
            pass
        return (str(exc), -1)
    return ("".join(chunks).strip(), int(code if code is not None else -1))
