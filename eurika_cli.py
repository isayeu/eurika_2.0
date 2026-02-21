"""
Eurika CLI v0.5

Entry point: argument parsing and dispatch only.
All command logic lives in cli.handlers.
"""

import argparse
import os
import sys
from pathlib import Path

# Ensure project root is on path for root-level imports (architecture_pipeline, runtime_scan, etc.)
_root = Path(__file__).resolve().parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

from cli.wiring import build_parser, dispatch_command

def _load_environment(env_path: Path | str = ".env") -> None:
    """
    Load project environment and force project LLM routing keys from .env.

    We keep normal dotenv behavior for generic vars, then explicitly apply
    LLM-related keys from project .env so external shell exports do not
    accidentally bypass project configuration.
    """
    try:
        from dotenv import dotenv_values, load_dotenv
    except ImportError:
        return

    load_dotenv(dotenv_path=env_path, override=False)
    values = dotenv_values(env_path)
    keys = (
        "OPENAI_API_KEY",
        "OPENAI_MODEL",
        "OPENAI_BASE_URL",
        "OLLAMA_OPENAI_API_KEY",
        "OLLAMA_OPENAI_MODEL",
        "OLLAMA_OPENAI_BASE_URL",
    )
    for key in keys:
        value = values.get(key)
        if value:
            os.environ[key] = value


# Load .env if present (optional: pip install python-dotenv)
_load_environment()

def _build_parser() -> argparse.ArgumentParser:
    """Configure top-level parser via extracted wiring module."""
    return build_parser(version="3.0.1")


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()
    return dispatch_command(parser, args)


if __name__ == "__main__":
    sys.exit(main())
