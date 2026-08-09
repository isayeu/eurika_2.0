"""Newline-delimited JSON-RPC server for an IDE child process."""

from __future__ import annotations

import argparse
import json
import sys
import threading
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Any, TextIO

from .local_runtime import LocalAgentRuntime
from .protocol import (
    ERR_CANCELLED,
    ERR_INTERNAL,
    ERR_INVALID_PARAMS,
    ERR_PARSE,
    ERR_TIMEOUT,
    JSONRPC_VERSION,
    RpcError,
    error_response,
    event_notification,
    success_response,
    validate_request,
)


@dataclass(slots=True)
class _ActiveRequest:
    cancel: threading.Event
    timed_out: threading.Event
    timer: threading.Timer | None = None
    future: Future[Any] | None = None


class JsonRpcStdioServer:
    """Concurrent JSON-RPC server whose output writes remain frame-atomic."""

    def __init__(
        self,
        runtime: LocalAgentRuntime,
        *,
        reader: TextIO,
        writer: TextIO,
        max_workers: int = 4,
        default_timeout_ms: int = 300_000,
    ) -> None:
        self.runtime = runtime
        self.reader = reader
        self.writer = writer
        self.default_timeout_ms = default_timeout_ms
        self._executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="eurika-rpc")
        self._active: dict[Any, _ActiveRequest] = {}
        self._active_lock = threading.RLock()
        self._write_lock = threading.Lock()

    def _write(self, message: dict[str, Any]) -> None:
        encoded = json.dumps(message, ensure_ascii=False, separators=(",", ":"))
        with self._write_lock:
            self.writer.write(encoded + "\n")
            self.writer.flush()

    def _cancel(self, request_id: Any) -> bool:
        with self._active_lock:
            active = self._active.get(request_id)
        if active is None:
            return False
        active.cancel.set()
        return True

    def _finish(self, request_id: Any, future: Future[Any]) -> None:
        with self._active_lock:
            active = self._active.pop(request_id, None)
        if active is None:
            return
        if active.timer is not None:
            active.timer.cancel()
        try:
            result = future.result()
        except RpcError as exc:
            if active.timed_out.is_set():
                exc = RpcError(ERR_TIMEOUT, "Request timed out")
            self._write(error_response(request_id, exc))
        except Exception as exc:  # pragma: no cover - final containment boundary
            self._write(error_response(request_id, RpcError(ERR_INTERNAL, "Internal error", {"detail": str(exc)})))
        else:
            if active.timed_out.is_set():
                self._write(error_response(request_id, RpcError(ERR_TIMEOUT, "Request timed out")))
            elif active.cancel.is_set():
                self._write(error_response(request_id, RpcError(ERR_CANCELLED, "Request cancelled")))
            else:
                self._write(success_response(request_id, result))

    def _submit(self, request_id: Any, method: str, params: dict[str, Any]) -> None:
        if request_id is None:
            return
        timeout_value = params.get("requestTimeoutMs", self.default_timeout_ms)
        if not isinstance(timeout_value, int) or timeout_value <= 0:
            self._write(error_response(request_id, RpcError(ERR_INVALID_PARAMS, "requestTimeoutMs must be a positive integer")))
            return
        timeout_ms = min(timeout_value, 3_600_000)
        active = _ActiveRequest(cancel=threading.Event(), timed_out=threading.Event())
        with self._active_lock:
            if request_id in self._active:
                self._write(error_response(request_id, RpcError(ERR_INVALID_PARAMS, "Duplicate active request id")))
                return
            self._active[request_id] = active

        def expire() -> None:
            active.timed_out.set()
            active.cancel.set()

        def emit(event: str, session_id: str | None, data: dict[str, Any]) -> None:
            self._write(
                event_notification(event=event, session_id=session_id, request_id=request_id, data=data)
            )

        active.timer = threading.Timer(timeout_ms / 1000, expire)
        active.timer.daemon = True
        active.timer.start()
        active.future = self._executor.submit(
            self.runtime.dispatch,
            method,
            params,
            cancel=active.cancel,
            emit=emit,
        )
        active.future.add_done_callback(lambda future: self._finish(request_id, future))

    def _handle_message(self, value: Any) -> None:
        try:
            request_id, method, params = validate_request(value)
        except RpcError as exc:
            request_id = value.get("id") if isinstance(value, dict) else None
            self._write(error_response(request_id, exc))
            return
        if method == "$/cancelRequest":
            target = params.get("id")
            cancelled = self._cancel(target)
            if request_id is not None:
                self._write(success_response(request_id, {"cancelled": cancelled, "id": target}))
            return
        self._submit(request_id, method, params)

    def serve_forever(self) -> None:
        try:
            for line in self.reader:
                if not line.strip():
                    continue
                try:
                    value = json.loads(line)
                except json.JSONDecodeError as exc:
                    self._write(error_response(None, RpcError(ERR_PARSE, "Parse error", {"detail": str(exc)})))
                    continue
                self._handle_message(value)
        finally:
            with self._active_lock:
                requests = list(self._active.values())
            for active in requests:
                active.cancel.set()
                if active.timer is not None:
                    active.timer.cancel()
            self._executor.shutdown(wait=True, cancel_futures=False)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Eurika local JSON-RPC agent backend")
    parser.add_argument("--workspace", type=Path, default=Path.cwd(), help="Workspace root")
    parser.add_argument("--max-workers", type=int, default=4)
    parser.add_argument("--request-timeout-ms", type=int, default=300_000)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    runtime = LocalAgentRuntime(args.workspace)
    server = JsonRpcStdioServer(
        runtime,
        reader=sys.stdin,
        writer=sys.stdout,
        max_workers=max(1, args.max_workers),
        default_timeout_ms=max(1, args.request_timeout_ms),
    )
    server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
