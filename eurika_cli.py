"""
Eurika CLI v0.5

Entry point: argument parsing and dispatch only.
All command logic lives in cli.handlers.
"""

import argparse
import sys
from pathlib import Path

# Ensure project root is on path for root-level imports (architecture_pipeline, runtime_scan, etc.)
_root = Path(__file__).resolve().parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

from cli.wiring import build_parser, dispatch_command
from eurika.utils.env import load_project_dotenv

def _load_environment(env_path: Path | str = ".env") -> None:
    """Load project .env (cwd); see load_project_dotenv for LLM key routing."""
    load_project_dotenv(Path(env_path).resolve().parent)


# Load .env if present (optional: pip install python-dotenv)
_load_environment()

def _build_parser() -> argparse.ArgumentParser:
    """Configure top-level parser via extracted wiring module."""
    return build_parser(version="3.0.19")


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()
    return dispatch_command(parser, args)


if __name__ == "__main__":
    sys.exit(main())
