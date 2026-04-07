"""CLI entrypoint for the interaction harness package."""

import sys

from .cli import main


def cli_entrypoint() -> None:
    """Console-script entrypoint for installed usage."""
    sys.exit(int(main().get("exit_code", 0)))


if __name__ == "__main__":
    cli_entrypoint()
