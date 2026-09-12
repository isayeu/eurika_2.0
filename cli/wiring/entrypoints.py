"""CLI entrypoints for Eurika.

This module sets up the top‑level command group and wires the
sub‑commands defined elsewhere in the ``cli`` package.  It is
intentionally lightweight and respects the dependency firewall
(L6 → L0‑L5 only through public facades).
"""

from __future__ import annotations

import sys

import click

# Public façade of the Eurika CLI implementation.
# Importing from ``eurika_cli`` (layer L6) is allowed.
from eurika_cli.main import cli as eurika_cli  # type: ignore[import-not-found]

# Optional: import other top‑level commands from the wiring package.
# These modules must also respect the layer contracts.
# from .commands import some_other_cmd  # example placeholder


@click.group()
def main() -> None:
    """Root command group for the Eurika CLI."""
    pass


# Register the main Eurika command tree.
main.add_command(eurika_cli)


def entrypoint() -> None:
    """Console‑script entry point.

    This function is referenced in ``setup.cfg`` / ``pyproject.toml`` as
    the ``console_scripts`` target, enabling ``eurika`` to be invoked
    from the command line.
    """
    sys.exit(main())


if __name__ == "__main__":
    entrypoint()