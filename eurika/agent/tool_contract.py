"""Tool Contract Layer (ROADMAP 2.7.2).

Typed adapters for scan, patch, verify, rollback, tests, git_read.
Unified ToolResult; errors normalized; dry-run reproducible.
"""
from __future__ import annotations
import subprocess
from pathlib import Path
from typing import Any, Protocol, Optional
from eurika.agent.tool_contract_extracted import ToolContract, _ok, _err, DefaultToolContract
from .models import ToolResult
