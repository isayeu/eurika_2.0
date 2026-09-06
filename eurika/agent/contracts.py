"""Structured contracts advertised by the local coding backend."""

from __future__ import annotations

from typing import Any


def _path_schema(description: str = "Workspace-relative path") -> dict[str, Any]:
    return {"type": "string", "description": description}


RPC_METHOD_CONTRACTS: dict[str, dict[str, Any]] = {
    "session/history": {
        "mutatesWorkspace": False,
        "inputSchema": {
            "type": "object",
            "properties": {"limit": {"type": "integer", "minimum": 0, "maximum": 200}},
        },
    },
    "session/clear": {
        "mutatesWorkspace": False,
        "inputSchema": {"type": "object"},
    },
    "activity/recent": {
        "mutatesWorkspace": False,
        "inputSchema": {
            "type": "object",
            "properties": {
                "afterOffset": {"type": "integer", "minimum": 0},
                "limit": {"type": "integer", "minimum": 0, "maximum": 200},
            },
        },
    },
    "idle-self-dev/prefs": {
        "mutatesWorkspace": False,
        "inputSchema": {
            "type": "object",
            "properties": {
                "enabled": {"type": "boolean"},
                "idle_self_dev": {"type": "boolean"},
            },
        },
    },
    "idle-self-dev/status": {
        "mutatesWorkspace": False,
        "inputSchema": {"type": "object"},
    },
    "idle-self-dev/run": {
        "mutatesWorkspace": True,
        "inputSchema": {
            "type": "object",
            "properties": {
                "force": {"type": "boolean"},
                "marketLlmEnabled": {"type": "boolean"},
                "portfolioEnabled": {"type": "boolean"},
                "keepSandbox": {"type": "boolean"},
            },
        },
    },
    "proposal/prepare": {
        "mutatesWorkspace": False,
        "inputSchema": {"type": "object"},
    },
    "proposal/get": {
        "mutatesWorkspace": False,
        "inputSchema": {
            "type": "object",
            "required": ["proposalId"],
            "properties": {
                "proposalId": {"type": "string"},
                "path": _path_schema(),
            },
        },
    },
    "proposal/apply": {
        "mutatesWorkspace": True,
        "requiresApproval": True,
        "inputSchema": {
            "type": "object",
            "required": ["proposalId", "approval"],
            "properties": {
                "proposalId": {"type": "string"},
                "paths": {"type": "array", "items": _path_schema()},
                "approval": {"type": "boolean", "const": True},
            },
        },
    },
    "proposal/reject": {
        "mutatesWorkspace": False,
        "inputSchema": {
            "type": "object",
            "required": ["proposalId"],
            "properties": {
                "proposalId": {"type": "string"},
                "paths": {"type": "array", "items": _path_schema()},
            },
        },
    },
    "checkpoint/list": {
        "mutatesWorkspace": False,
        "inputSchema": {"type": "object"},
    },
    "checkpoint/restore": {
        "mutatesWorkspace": True,
        "requiresApproval": True,
        "inputSchema": {
            "type": "object",
            "required": ["approval"],
            "properties": {
                "checkpointId": {"type": "string"},
                "approval": {"type": "boolean", "const": True},
            },
        },
    },
    "context/preview": {
        "mutatesWorkspace": False,
        "inputSchema": {"type": "object"},
    },
    "context/decide": {
        "mutatesWorkspace": True,
        "inputSchema": {
            "type": "object",
            "required": ["decision"],
            "properties": {
                "decision": {"type": "string", "enum": ["apply", "reject"]},
                "token": {"type": "string"},
                "approval": {"type": "boolean", "const": True},
            },
        },
    },
    "approval/apply": {
        "mutatesWorkspace": True,
        "requiresApproval": True,
        "inputSchema": {
            "type": "object",
            "required": ["approval"],
            "properties": {
                "approval": {"type": "boolean", "const": True},
                "operations": {"type": "array", "items": {"type": "object"}},
                "verifyCmd": {"type": "string"},
                "timeoutMs": {"type": "integer", "minimum": 1},
            },
        },
    },
}


TOOL_CONTRACTS: dict[str, dict[str, Any]] = {
    "search": {
        "description": (
            "Search ignore-aware workspace contents or symbol declarations. "
            "Matches are ranked so implementation files appear before docs and tests."
        ),
        "mutatesWorkspace": False,
        "requiresApproval": False,
        "inputSchema": {
            "type": "object",
            "required": ["query"],
            "properties": {
                "query": {"type": "string"},
                "path": _path_schema("Optional workspace-relative search scope"),
                "glob": {"type": "string"},
                "regex": {"type": "boolean"},
                "caseSensitive": {"type": "boolean"},
                "mode": {"type": "string", "enum": ["text", "symbol"]},
                "maxResults": {"type": "integer", "minimum": 1, "maximum": 1000},
            },
        },
    },
    "read": {
        "description": "Read a UTF-8 workspace file.",
        "mutatesWorkspace": False,
        "requiresApproval": False,
        "inputSchema": {
            "type": "object",
            "required": ["path"],
            "properties": {
                "path": _path_schema(),
                "startLine": {"type": "integer", "minimum": 1},
                "endLine": {"type": "integer", "minimum": 1},
            },
        },
    },
    "market_status": {
        "description": (
            "Read the current Eurika paper-Market, portfolio, open-position, "
            "PnL, and learning status from the stable product Market root."
        ),
        "mutatesWorkspace": False,
        "requiresApproval": False,
        "inputSchema": {"type": "object", "properties": {}},
    },
    "edit": {
        "description": "Write or replace text in one or more workspace files.",
        "mutatesWorkspace": True,
        "requiresApproval": True,
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": _path_schema(),
                "content": {"type": "string"},
                "oldText": {"type": "string"},
                "newText": {"type": "string"},
                "expectedVersion": {"type": "string", "description": "Optional SHA-256 of current bytes"},
                "create": {"type": "boolean"},
                "edits": {
                    "type": "array",
                    "minItems": 1,
                    "items": {
                        "type": "object",
                        "required": ["path"],
                        "properties": {
                            "path": _path_schema(),
                            "content": {"type": "string"},
                            "oldText": {"type": "string"},
                            "newText": {"type": "string"},
                            "expectedVersion": {"type": "string"},
                            "create": {"type": "boolean"},
                        },
                    },
                },
                "approval": {"type": "boolean", "const": True},
            },
        },
    },
    "terminal": {
        "description": "Run an argv command without a shell in the workspace.",
        "mutatesWorkspace": True,
        "requiresApproval": True,
        "inputSchema": {
            "type": "object",
            "required": ["argv", "approval"],
            "properties": {
                "argv": {"type": "array", "items": {"type": "string"}, "minItems": 1},
                "cwd": _path_schema(),
                "timeoutMs": {"type": "integer", "minimum": 1},
                "approval": {"type": "boolean", "const": True},
            },
        },
    },
    "diagnostics": {
        "description": "Compile Python files and return syntax diagnostics.",
        "mutatesWorkspace": False,
        "requiresApproval": False,
        "inputSchema": {
            "type": "object",
            "properties": {"paths": {"type": "array", "items": _path_schema()}},
        },
    },
    "tests": {
        "description": "Run pytest for approved workspace-relative targets.",
        "mutatesWorkspace": True,
        "requiresApproval": True,
        "inputSchema": {
            "type": "object",
            "required": ["approval"],
            "properties": {
                "paths": {"type": "array", "items": _path_schema()},
                "extraArgs": {"type": "array", "items": {"type": "string"}},
                "timeoutMs": {"type": "integer", "minimum": 1},
                "approval": {"type": "boolean", "const": True},
            },
        },
    },
    "git_diff": {
        "description": "Read the workspace git diff.",
        "mutatesWorkspace": False,
        "requiresApproval": False,
        "inputSchema": {
            "type": "object",
            "properties": {
                "staged": {"type": "boolean"},
                "paths": {"type": "array", "items": _path_schema()},
            },
        },
    },
    "git_status": {
        "description": "Read git status and a safe commit-path preview (no secrets).",
        "mutatesWorkspace": False,
        "requiresApproval": False,
        "inputSchema": {"type": "object", "properties": {}},
    },
    "git_commit": {
        "description": (
            "Commit listed workspace-relative paths with an explicit message. "
            "Never add -A, --no-verify, or secret files. Requires approval."
        ),
        "mutatesWorkspace": True,
        "requiresApproval": True,
        "inputSchema": {
            "type": "object",
            "required": ["message", "approval"],
            "properties": {
                "message": {"type": "string", "minLength": 1},
                "paths": {"type": "array", "items": _path_schema()},
                "approval": {"type": "boolean", "const": True},
            },
        },
    },
    "git_push": {
        "description": (
            "Push the current branch to origin (or git push -u origin HEAD). "
            "Never --force. Requires approval."
        ),
        "mutatesWorkspace": True,
        "requiresApproval": True,
        "inputSchema": {
            "type": "object",
            "required": ["approval"],
            "properties": {"approval": {"type": "boolean", "const": True}},
        },
    },
}
