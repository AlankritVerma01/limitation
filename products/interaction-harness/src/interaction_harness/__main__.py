"""CLI entrypoint for the interaction harness package."""

import sys

from .cli import main

if __name__ == "__main__":
    sys.exit(int(main().get("exit_code", 0)))
