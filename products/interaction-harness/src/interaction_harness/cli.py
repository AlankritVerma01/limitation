"""Public CLI entrypoint for the interaction harness."""

from __future__ import annotations

import sys

from .cli_app.handlers import COMMAND_HANDLERS
from .cli_app.parser import build_parser
from .cli_app.progress import TerminalProgressRenderer


def main(argv: list[str] | None = None) -> dict[str, str | int]:
    """Run the CLI entrypoint and return the generated artifact paths."""
    raw_argv = list(argv) if argv is not None else sys.argv[1:]
    parser = build_parser()
    args = parser.parse_args(raw_argv)
    args.provided_options = {token for token in raw_argv if token.startswith("--")}
    handler_name = getattr(args, "handler_name", None)
    if handler_name is None:
        parser.print_help()
        raise SystemExit(0)

    handler = COMMAND_HANDLERS[handler_name]
    progress = TerminalProgressRenderer()
    try:
        return handler(args, progress)
    finally:
        progress.close()
