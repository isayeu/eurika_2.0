"""Example lifecycle hooks used by plugin-loader tests."""

from __future__ import annotations

from typing import Any

EVENTS: list[dict[str, Any]] = []


def reset() -> None:
    EVENTS.clear()


def capture(context: Any) -> None:
    EVENTS.append(
        {
            "event": context.event,
            "stage": context.stage,
            "status": context.status,
            "payload": context.payload,
            "metadata": context.metadata,
        }
    )


def fail(_context: Any) -> None:
    raise RuntimeError("hook boom")
