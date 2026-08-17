"""Host-neutral edit proposals and persistent workspace checkpoints."""

from __future__ import annotations

import base64
import hashlib
import json
import os
import tempfile
import threading
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .protocol import (
    ERR_APPROVAL_REQUIRED,
    ERR_INVALID_PARAMS,
    ERR_TOOL_FAILED,
    RpcError,
)
from .workspace import WorkspaceTools


def _digest(value: bytes | None) -> str | None:
    return hashlib.sha256(value).hexdigest() if value is not None else None


@dataclass(slots=True)
class ProposedFile:
    path: str
    before: bytes | None
    after: bytes | None

    def public(self, *, include_content: bool = False) -> dict[str, Any]:
        result: dict[str, Any] = {
            "path": self.path,
            "beforeVersion": _digest(self.before),
            "afterVersion": _digest(self.after),
            "created": self.before is None and self.after is not None,
            "deleted": self.before is not None and self.after is None,
        }
        if include_content:
            result["before"] = self.before.decode("utf-8") if self.before is not None else None
            result["after"] = self.after.decode("utf-8") if self.after is not None else None
        return result


class ProposalStore:
    """Prepare mutations for review, then apply them with stale-file checks."""

    def __init__(self, tools: WorkspaceTools) -> None:
        self.tools = tools
        self._proposals: dict[str, dict[str, ProposedFile]] = {}
        self._lock = threading.RLock()
        self._checkpoint_path = tools.root / ".eurika" / "agent_checkpoints.json"

    @staticmethod
    def _approved(params: dict[str, Any], operation: str) -> None:
        if params.get("approval") is not True:
            raise RpcError(
                ERR_APPROVAL_REQUIRED,
                f"Explicit approval is required for {operation}",
                {"operation": operation, "requiresApproval": True},
            )

    def prepare(self, params: dict[str, Any]) -> dict[str, Any]:
        edits = params.get("edits")
        if edits is None:
            edits = [params]
        if not isinstance(edits, list) or not edits or not all(isinstance(item, dict) for item in edits):
            raise RpcError(ERR_INVALID_PARAMS, "edits must be a non-empty array of objects")
        files: dict[str, ProposedFile] = {}
        for item in edits:
            path_value = item.get("path")
            if not isinstance(path_value, str) or not path_value:
                raise RpcError(ERR_INVALID_PARAMS, "Every edit requires a workspace-relative path")
            target = self.tools.resolve(path_value)
            relative = target.relative_to(self.tools.root).as_posix()
            existing = files.get(relative)
            if existing is None:
                if target.exists() and not target.is_file():
                    raise RpcError(ERR_INVALID_PARAMS, f"Edit target is not a file: {relative}")
                try:
                    before = target.read_bytes() if target.is_file() else None
                    if before is not None:
                        before.decode("utf-8")
                except (OSError, UnicodeError) as exc:
                    raise RpcError(ERR_TOOL_FAILED, f"Could not read edit target: {exc}") from exc
                expected = item.get("expectedVersion")
                if expected is not None and expected != _digest(before):
                    raise RpcError(
                        ERR_TOOL_FAILED,
                        "File changed since it was read",
                        {
                            "path": relative,
                            "expectedVersion": expected,
                            "actualVersion": _digest(before),
                        },
                    )
                existing = ProposedFile(relative, before, before)
                files[relative] = existing
            existing.after = self._transform(existing.after, item, relative)
        proposal_id = str(uuid.uuid4())
        with self._lock:
            self._proposals[proposal_id] = files
        return {
            "proposalId": proposal_id,
            "transactionId": proposal_id,
            "files": [item.public() for item in files.values()],
        }

    @staticmethod
    def _transform(current_bytes: bytes | None, edit: dict[str, Any], relative: str) -> bytes | None:
        if edit.get("delete") is True:
            return None
        current = (current_bytes or b"").decode("utf-8")
        if isinstance(edit.get("content"), str):
            updated = edit["content"]
        elif isinstance(edit.get("newText"), str) and isinstance(edit.get("oldText"), str):
            old = edit["oldText"]
            occurrences = current.count(old)
            if occurrences != 1:
                raise RpcError(
                    ERR_TOOL_FAILED,
                    f"oldText must occur exactly once in {relative}",
                    {"path": relative, "occurrences": occurrences},
                )
            updated = current.replace(old, edit["newText"], 1)
        else:
            raise RpcError(ERR_INVALID_PARAMS, "Edit requires content, oldText/newText, or delete=true")
        return updated.encode("utf-8")

    def get(self, proposal_id: Any, path: Any = None) -> dict[str, Any]:
        with self._lock:
            files = self._require(proposal_id)
            if path is None:
                selected = list(files.values())
            elif isinstance(path, str) and path in files:
                selected = [files[path]]
            else:
                raise RpcError(ERR_INVALID_PARAMS, f"Unknown proposal path: {path}")
            return {
                "proposalId": proposal_id,
                "files": [item.public(include_content=True) for item in selected],
            }

    def apply(
        self,
        params: dict[str, Any],
        *,
        cancel: threading.Event,
    ) -> dict[str, Any]:
        self._approved(params, "proposal apply")
        proposal_id = params.get("proposalId") or params.get("transactionId")
        with self._lock:
            files = self._require(proposal_id)
            selected = self._selection(files, params.get("paths"))
            if not selected:
                raise RpcError(ERR_INVALID_PARAMS, "Select at least one proposal file")
            snapshots: list[tuple[Path, bytes | None]] = []
            entries: list[dict[str, Any]] = []
            for relative in selected:
                self.tools._check_cancel(cancel)
                proposed = files[relative]
                target = self.tools.resolve(relative)
                current = target.read_bytes() if target.is_file() else None
                if _digest(current) != _digest(proposed.before):
                    raise RpcError(
                        ERR_TOOL_FAILED,
                        "File changed after proposal preview",
                        {
                            "path": relative,
                            "expectedVersion": _digest(proposed.before),
                            "actualVersion": _digest(current),
                        },
                    )
                snapshots.append((target, current))
                entries.append(
                    {
                        "path": relative,
                        "beforeHash": _digest(current),
                        "beforeBase64": (
                            base64.b64encode(current).decode("ascii")
                            if current is not None
                            else None
                        ),
                        "appliedHash": _digest(proposed.after),
                    }
                )
            checkpoints = self._checkpoint_with_entries(str(proposal_id), entries)
            try:
                for relative in selected:
                    self.tools._check_cancel(cancel)
                    proposed = files[relative]
                    self._write(self.tools.resolve(relative), proposed.after)
                self._write_checkpoints(checkpoints)
            except Exception:
                for target, before in snapshots:
                    self._write(target, before)
                raise
            for relative in selected:
                files.pop(relative, None)
            remaining = list(files)
            if not files:
                self._proposals.pop(str(proposal_id), None)
            return {
                "proposalId": proposal_id,
                "checkpointId": proposal_id,
                "applied": selected,
                "remaining": remaining,
            }

    def reject(self, params: dict[str, Any]) -> dict[str, Any]:
        proposal_id = params.get("proposalId") or params.get("transactionId")
        with self._lock:
            files = self._require(proposal_id)
            selected = self._selection(files, params.get("paths"))
            for relative in selected:
                files.pop(relative, None)
            remaining = list(files)
            if not files:
                self._proposals.pop(str(proposal_id), None)
        return {"proposalId": proposal_id, "rejected": selected, "remaining": remaining}

    def restore(self, params: dict[str, Any], *, cancel: threading.Event) -> dict[str, Any]:
        self._approved(params, "checkpoint restore")
        with self._lock:
            checkpoints = self._load_checkpoints()
            checkpoint_id = params.get("checkpointId")
            checkpoint = (
                next((item for item in checkpoints if item.get("id") == checkpoint_id), None)
                if checkpoint_id
                else (checkpoints[-1] if checkpoints else None)
            )
            if not checkpoint:
                raise RpcError(ERR_INVALID_PARAMS, "No matching Eurika checkpoint is available")
            restored: list[str] = []
            conflicts: list[str] = []
            unresolved: list[dict[str, Any]] = []
            writes: list[tuple[Path, bytes | None, bytes | None]] = []
            for entry in checkpoint.get("entries", []):
                self.tools._check_cancel(cancel)
                relative = str(entry.get("path") or "")
                target = self.tools.resolve(relative)
                current = target.read_bytes() if target.is_file() else None
                if _digest(current) != entry.get("appliedHash"):
                    conflicts.append(relative)
                    unresolved.append(entry)
                    continue
                encoded = entry.get("beforeBase64")
                before = base64.b64decode(encoded) if isinstance(encoded, str) else None
                writes.append((target, current, before))
                restored.append(relative)
            remaining = [item for item in checkpoints if item is not checkpoint]
            if unresolved:
                remaining.append({**checkpoint, "entries": unresolved})
            try:
                for target, _current, before in writes:
                    self.tools._check_cancel(cancel)
                    self._write(target, before)
                self._write_checkpoints(remaining)
            except Exception:
                for target, current, _before in writes:
                    self._write(target, current)
                raise
            return {
                "checkpointId": checkpoint.get("id"),
                "restored": restored,
                "conflicts": conflicts,
            }

    def list_checkpoints(self) -> dict[str, Any]:
        with self._lock:
            return {
                "checkpoints": [
                    {
                        "id": item.get("id"),
                        "createdAt": item.get("createdAt"),
                        "paths": [entry.get("path") for entry in item.get("entries", [])],
                    }
                    for item in self._load_checkpoints()
                ]
            }

    def _require(self, proposal_id: Any) -> dict[str, ProposedFile]:
        if not isinstance(proposal_id, str) or not proposal_id:
            raise RpcError(ERR_INVALID_PARAMS, "proposalId must be a non-empty string")
        files = self._proposals.get(proposal_id)
        if files is None:
            raise RpcError(ERR_INVALID_PARAMS, f"Unknown proposal: {proposal_id}")
        return files

    @staticmethod
    def _selection(files: dict[str, ProposedFile], supplied: Any) -> list[str]:
        if supplied is None:
            return list(files)
        if not isinstance(supplied, list) or not all(isinstance(item, str) for item in supplied):
            raise RpcError(ERR_INVALID_PARAMS, "paths must be a string array")
        unknown = [item for item in supplied if item not in files]
        if unknown:
            raise RpcError(ERR_INVALID_PARAMS, "Unknown proposal path", {"paths": unknown})
        return list(dict.fromkeys(supplied))

    @staticmethod
    def _write(path: Path, content: bytes | None) -> None:
        if content is None:
            path.unlink(missing_ok=True)
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary: str | None = None
        try:
            with tempfile.NamedTemporaryFile("wb", dir=path.parent, delete=False) as handle:
                temporary = handle.name
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, path)
            temporary = None
        except OSError as exc:
            raise RpcError(ERR_TOOL_FAILED, f"Could not update file: {exc}") from exc
        finally:
            if temporary:
                Path(temporary).unlink(missing_ok=True)

    def _load_checkpoints(self) -> list[dict[str, Any]]:
        try:
            value = json.loads(self._checkpoint_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return []
        return value if isinstance(value, list) else []

    def _write_checkpoints(self, checkpoints: list[dict[str, Any]]) -> None:
        payload = json.dumps(
            checkpoints[-20:],
            ensure_ascii=False,
            indent=2,
        ).encode("utf-8")
        self._write(self._checkpoint_path, payload)

    def _checkpoint_with_entries(
        self,
        checkpoint_id: str,
        entries: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        checkpoints = self._load_checkpoints()
        existing = next((item for item in checkpoints if item.get("id") == checkpoint_id), None)
        if existing is None:
            checkpoints.append(
                {
                    "id": checkpoint_id,
                    "createdAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                    "entries": entries,
                }
            )
        else:
            known = {item.get("path") for item in existing.get("entries", [])}
            existing.setdefault("entries", []).extend(
                item for item in entries if item.get("path") not in known
            )
        return checkpoints
