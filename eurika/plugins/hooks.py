"""Trusted, observational lifecycle hooks at canonical pipeline boundaries."""

from __future__ import annotations

import copy
import time
from contextvars import ContextVar
from dataclasses import asdict, dataclass, field, is_dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any, Callable, Literal, Mapping, cast

from .registry import _load_entry_point, _load_toml

HookEvent = Literal["after_scan", "after_plan", "after_apply", "after_verify"]
HOOK_EVENTS: tuple[HookEvent, ...] = (
    "after_scan",
    "after_plan",
    "after_apply",
    "after_verify",
)
HOOK_SCHEMA_VERSION = 1
_ACTIVE_DISPATCHES: ContextVar[tuple[tuple[str, str], ...]] = ContextVar(
    "eurika_active_hook_dispatches", default=()
)


def _json_safe(value: Any, *, depth: int = 0) -> Any:
    """Bound arbitrary pipeline objects to a stable JSON-like public payload."""
    if depth > 12:
        return "<max-depth>"
    if is_dataclass(value) and not isinstance(value, type):
        value = asdict(value)
    if isinstance(value, Mapping):
        return {str(k): _json_safe(v, depth=depth + 1) for k, v in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [_json_safe(v, depth=depth + 1) for v in value]
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, (str, int, float, bool)) or value is None:
        if isinstance(value, str) and len(value) > 4000:
            return value[:4000] + "..."
        return value
    raw = getattr(value, "__dict__", None)
    if isinstance(raw, dict):
        return _json_safe(raw, depth=depth + 1)
    return str(value)[:1000]


def _freeze(value: Any) -> Any:
    try:
        value = copy.deepcopy(value)
    except Exception:
        pass
    if isinstance(value, Mapping):
        return MappingProxyType({str(k): _freeze(v) for k, v in value.items()})
    if isinstance(value, list):
        return tuple(_freeze(v) for v in value)
    if isinstance(value, tuple):
        return tuple(_freeze(v) for v in value)
    return value


@dataclass(frozen=True, slots=True)
class HookContext:
    """Versioned immutable envelope delivered to a lifecycle hook."""

    event: HookEvent
    project_root: Path
    status: str
    payload: Mapping[str, Any]
    metadata: Mapping[str, Any] = field(default_factory=lambda: MappingProxyType({}))
    schema_version: int = HOOK_SCHEMA_VERSION

    @property
    def stage(self) -> str:
        return self.event.removeprefix("after_")

    @classmethod
    def snapshot(
        cls,
        *,
        event: str,
        project_root: str | Path,
        payload: Mapping[str, Any] | None = None,
        status: str = "ok",
        metadata: Mapping[str, Any] | None = None,
    ) -> "HookContext":
        event_name = str(event).strip().lower()
        if event_name not in HOOK_EVENTS:
            raise ValueError(f"unsupported hook event: {event_name}")
        safe_payload = _json_safe(payload or {})
        safe_metadata = _json_safe(metadata or {})
        return cls(
            event=event_name,
            project_root=Path(project_root).resolve(),
            status=str(status),
            payload=_freeze(safe_payload),
            metadata=_freeze(safe_metadata),
        )


PostStageHook = Callable[[HookContext], Any]


@dataclass(frozen=True, slots=True)
class HookExecution:
    event: str
    plugin_id: str
    status: str
    duration_ms: int
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        row: dict[str, Any] = {
            "event": self.event,
            "plugin_id": self.plugin_id,
            "status": self.status,
            "duration_ms": self.duration_ms,
        }
        if self.error:
            row["error"] = self.error
        return row


class HookRegistry:
    """Ordered registry; duplicate ``event + plugin_id`` entries are ignored."""

    def __init__(self) -> None:
        self._hooks: dict[str, list[tuple[str, PostStageHook]]] = {}
        self._registered: set[tuple[str, str]] = set()

    def register(
        self,
        event: str,
        hook: PostStageHook,
        *,
        plugin_id: str | None = None,
    ) -> bool:
        event_name = str(event).strip().lower()
        if event_name not in HOOK_EVENTS:
            raise ValueError(f"unsupported hook event: {event_name}")
        if not callable(hook):
            raise TypeError("hook must be callable")
        ident = plugin_id or f"{getattr(hook, '__module__', '?')}:{getattr(hook, '__name__', '?')}"
        key = (event_name, ident)
        if key in self._registered:
            return False
        self._registered.add(key)
        self._hooks.setdefault(event_name, []).append((ident, hook))
        return True

    def execute(self, context: HookContext) -> list[HookExecution]:
        executions: list[HookExecution] = []
        for plugin_id, hook in tuple(self._hooks.get(context.event, ())):
            started = time.perf_counter()
            try:
                hook(context)
                status = "ok"
                error = None
            except BaseException as exc:
                # Plugins are fail-open observers; even SystemExit must not stop verify/rollback.
                status = "exception"
                error = f"{type(exc).__name__}: {exc}"[:1000]
            executions.append(
                HookExecution(
                    event=context.event,
                    plugin_id=plugin_id,
                    status=status,
                    duration_ms=int((time.perf_counter() - started) * 1000),
                    error=error,
                )
            )
        return executions

    def count(self, event: str | None = None) -> int:
        if event is None:
            return sum(len(items) for items in self._hooks.values())
        return len(self._hooks.get(str(event).strip().lower(), ()))


def _configured_hooks(project_root: Path) -> list[tuple[str, str]]:
    configured: list[tuple[str, str]] = []
    plugins_path = project_root / ".eurika" / "plugins.toml"
    if plugins_path.is_file():
        try:
            data = _load_toml(plugins_path.read_text(encoding="utf-8"))
        except Exception:
            data = {}
        hooks = data.get("hooks")
        if isinstance(hooks, list):
            for item in hooks:
                if not isinstance(item, dict):
                    continue
                event = str(item.get("event") or "").strip()
                entry_point = str(item.get("entry_point") or "").strip()
                if event and entry_point and item.get("enabled", True) is not False:
                    configured.append((event, entry_point))

    pyproject = project_root / "pyproject.toml"
    if pyproject.is_file():
        try:
            data = _load_toml(pyproject.read_text(encoding="utf-8"))
        except Exception:
            data = {}
        hooks = ((data.get("tool") or {}).get("eurika") or {}).get("hooks")
        if isinstance(hooks, dict):
            for event, raw in hooks.items():
                for entry_point in raw if isinstance(raw, list) else [raw]:
                    ep = str(entry_point or "").strip()
                    if ep:
                        configured.append((str(event), ep))
    return configured


def load_hook_registry(project_root: str | Path) -> HookRegistry:
    """Load explicitly configured trusted hooks in declaration order."""
    root = Path(project_root).resolve()
    registry = HookRegistry()
    for event, entry_point in _configured_hooks(root):
        fn = _load_entry_point(entry_point)
        if fn is None:
            continue
        try:
            registry.register(event, cast(PostStageHook, fn), plugin_id=entry_point)
        except (TypeError, ValueError):
            continue
    return registry


def dispatch_project_hooks(
    project_root: str | Path,
    event: str,
    *,
    payload: Mapping[str, Any] | None = None,
    status: str = "ok",
    metadata: Mapping[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Execute configured hooks, audit attempts, and never raise into the pipeline."""
    root = Path(project_root).resolve()
    key = (str(root), str(event))
    active = _ACTIVE_DISPATCHES.get()
    if key in active:
        return [
            {
                "event": str(event),
                "plugin_id": "<dispatcher>",
                "status": "skipped_reentrant",
                "duration_ms": 0,
            }
        ]
    token = _ACTIVE_DISPATCHES.set(active + (key,))
    try:
        registry = load_hook_registry(root)
        if registry.count(event) == 0:
            return []
        context = HookContext.snapshot(
            event=event,
            project_root=root,
            payload=payload,
            status=status,
            metadata=metadata,
        )
        rows = [execution.to_dict() for execution in registry.execute(context)]
        try:
            from eurika.storage import ProjectMemory

            memory = ProjectMemory(root)
            for row in rows:
                memory.events.append_event(
                    type="plugin_hook",
                    input={
                        "event": row["event"],
                        "plugin_id": row["plugin_id"],
                        "schema_version": HOOK_SCHEMA_VERSION,
                    },
                    output=row,
                    result=row["status"] == "ok",
                )
        except Exception:
            pass
        return rows
    except BaseException as exc:
        return [
            {
                "event": str(event),
                "plugin_id": "<dispatcher>",
                "status": "exception",
                "duration_ms": 0,
                "error": f"{type(exc).__name__}: {exc}"[:1000],
            }
        ]
    finally:
        _ACTIVE_DISPATCHES.reset(token)
