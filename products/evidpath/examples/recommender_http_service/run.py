"""Simple public runner for the example external recommender service."""

from __future__ import annotations

import argparse
import importlib
import os
import sys

import uvicorn


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Run the example external recommender service over HTTP. "
            "This is the easiest local proof path for the customer-style "
            "external target workflow."
        )
    )
    parser.add_argument(
        "--model-kind",
        default="popularity",
        choices=("popularity", "item-item-cf", "genre-history-blend"),
        help="Ranking behavior to serve.",
    )
    parser.add_argument(
        "--artifact-dir",
        default="",
        help="Optional directory for built example artifacts.",
    )
    parser.add_argument(
        "--data-dir",
        default="",
        help=(
            "Optional explicit MovieLens 100K data directory. "
            "If omitted, the service uses the repo copy when present and "
            "otherwise downloads the dataset automatically."
        ),
    )
    parser.add_argument(
        "--top-k",
        type=int,
        default=5,
        help="Number of ranked items to return.",
    )
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="Host interface to bind.",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8051,
        help="Port to bind.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    script_dir = os.path.dirname(__file__)
    if script_dir not in sys.path:
        sys.path.insert(0, script_dir)
    service_app = importlib.import_module("app")
    os.environ["IH_EXAMPLE_MODEL_KIND"] = args.model_kind
    os.environ["IH_EXAMPLE_TOP_K"] = str(args.top_k)
    if args.artifact_dir:
        os.environ["IH_EXAMPLE_ARTIFACT_DIR"] = args.artifact_dir
    else:
        os.environ.pop("IH_EXAMPLE_ARTIFACT_DIR", None)
    if args.data_dir:
        os.environ["IH_EXAMPLE_DATA_DIR"] = args.data_dir
    else:
        os.environ.pop("IH_EXAMPLE_DATA_DIR", None)

    uvicorn.run(
        service_app.create_app(),
        host=args.host,
        port=args.port,
        log_level="info",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
