"""Qt adapter mixin: local coding-agent gateway (/chat + JSON-RPC)."""

from __future__ import annotations

from pathlib import Path
from typing import Any


def _rpc_error_text(rpc: dict[str, Any]) -> str:
    err = rpc.get("error")
    if isinstance(err, dict):
        return str(err.get("message") or err)
    return str(err)


class AgentGatewayMixin:
    """Requires `_root()` and `_agent_session_id` on the host adapter."""

    _agent_session_id: str | None

    def _root(self) -> Path:
        raise NotImplementedError

    def agent_chat(self, message: str, *, session_id: str | None = None) -> dict[str, Any]:
        """Local coding-agent loop (same /chat surface as Desktop)."""
        from eurika.agent.http_client import AgentHttpClient

        client = AgentHttpClient.discover(self._root())
        payload: dict[str, Any] = {
            "message": message,
            "context": {"reviewInApprovals": True, "client": "qt"},
        }
        sid = session_id or self._agent_session_id
        if sid:
            payload["sessionId"] = sid
        result = client.post("/chat", payload)
        if isinstance(result, dict) and result.get("sessionId"):
            self._agent_session_id = str(result["sessionId"])
        if isinstance(result, dict):
            return result
        return {"ok": False, "text": "", "error": "empty agent result"}

    def agent_decide_tool(self, call: dict[str, Any], *, approved: bool) -> dict[str, Any]:
        """Approve or reject a pendingToolCall, then continue the agent session."""
        from eurika.agent.http_client import AgentHttpClient
        from qt_app.ui.agent_pending import with_approval

        client = AgentHttpClient.discover(self._root())
        tool = str(call.get("tool") or "")
        call_id = str(call.get("callId") or "")
        outcome: dict[str, Any] = {"status": "rejected"}
        params: dict[str, Any] = {}
        if self._agent_session_id:
            params["sessionId"] = self._agent_session_id
        if approved:
            rpc = client.rpc(
                "tool/call",
                {
                    "callId": call_id,
                    "tool": tool,
                    "arguments": with_approval(call.get("arguments")),
                    **params,
                },
            )
            if isinstance(rpc, dict) and rpc.get("error"):
                return {
                    "ok": False,
                    "text": "",
                    "error": _rpc_error_text(rpc),
                    "pendingToolCalls": [],
                }
            raw_result = rpc.get("result") if isinstance(rpc, dict) else {}
            outcome = raw_result if isinstance(raw_result, dict) else {"result": raw_result}
        cont = client.rpc(
            "session/chat",
            {
                "toolResults": [{"callId": call_id, "tool": tool, "result": outcome}],
                **params,
            },
        )
        return self._agent_continue_payload(cont)

    def agent_get_proposal(self, proposal_id: str, path: str | None = None) -> dict[str, Any]:
        from eurika.agent.http_client import AgentHttpClient

        client = AgentHttpClient.discover(self._root())
        params: dict[str, Any] = {"proposalId": proposal_id}
        if path:
            params["path"] = path
        rpc = client.rpc("proposal/get", params)
        if isinstance(rpc, dict) and rpc.get("error"):
            return {"error": _rpc_error_text(rpc), "files": []}
        raw_result = rpc.get("result") if isinstance(rpc, dict) else None
        return raw_result if isinstance(raw_result, dict) else {"files": []}

    def agent_decide_proposal(self, call: dict[str, Any], *, approved: bool) -> dict[str, Any]:
        """Apply or reject an edit proposal, then continue the agent session."""
        from eurika.agent.http_client import AgentHttpClient
        from qt_app.ui.agent_pending import proposal_paths

        client = AgentHttpClient.discover(self._root())
        raw_proposal = call.get("proposal")
        proposal: dict[str, Any] = raw_proposal if isinstance(raw_proposal, dict) else {}
        proposal_id = str(proposal.get("proposalId") or "")
        paths = proposal_paths(call)
        params: dict[str, Any] = {"proposalId": proposal_id}
        if paths:
            params["paths"] = paths
        if self._agent_session_id:
            params["sessionId"] = self._agent_session_id
        if approved:
            params["approval"] = True
            rpc = client.rpc("proposal/apply", params)
        else:
            rpc = client.rpc("proposal/reject", params)
        if isinstance(rpc, dict) and rpc.get("error"):
            return {
                "ok": False,
                "text": "",
                "error": _rpc_error_text(rpc),
                "pendingToolCalls": [],
            }
        raw_outcome = rpc.get("result") if isinstance(rpc, dict) else {}
        outcome = raw_outcome if isinstance(raw_outcome, dict) else {"result": raw_outcome}
        cont_params: dict[str, Any] = {
            "toolResults": [
                {
                    "callId": str(call.get("callId") or ""),
                    "tool": str(call.get("tool") or "edit"),
                    "result": {
                        "decision": "applied" if approved else "rejected",
                        "outcome": outcome,
                    },
                }
            ]
        }
        if self._agent_session_id:
            cont_params["sessionId"] = self._agent_session_id
        return self._agent_continue_payload(client.rpc("session/chat", cont_params))

    def _agent_continue_payload(self, cont: Any) -> dict[str, Any]:
        if isinstance(cont, dict) and cont.get("error"):
            return {
                "ok": False,
                "text": "",
                "error": _rpc_error_text(cont),
                "pendingToolCalls": [],
                "sessionId": self._agent_session_id,
            }
        inner = cont.get("result") if isinstance(cont, dict) else {}
        if not isinstance(inner, dict):
            inner = {}
        if inner.get("sessionId"):
            self._agent_session_id = str(inner["sessionId"])
        return {
            "ok": True,
            "text": str(inner.get("text") or ""),
            "pendingToolCalls": inner.get("pendingToolCalls") or [],
            "sessionId": inner.get("sessionId") or self._agent_session_id,
            "metrics": inner.get("metrics") or {},
        }
