"""Run the Hugging Face recommender example service with Uvicorn."""

from __future__ import annotations

import argparse
import os

import uvicorn

try:
    from .app import create_app
except ImportError:  # pragma: no cover - direct script startup fallback
    from app import create_app  # type: ignore[no-redef]


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run the Interaction Harness HF recommender example service."
    )
    parser.add_argument(
        "--model-kind",
        default="hf-semantic",
        choices=("hf-semantic", "hf-semantic-popularity-blend"),
        help="HF-backed ranking mode to serve.",
    )
    parser.add_argument(
        "--artifact-dir",
        default="",
        help="Optional artifact directory override for the shared MovieLens bundle.",
    )
    parser.add_argument(
        "--data-dir",
        default=None,
        help="Optional explicit MovieLens data directory override.",
    )
    parser.add_argument(
        "--model-name",
        default="sentence-transformers/all-MiniLM-L6-v2",
        help="HF embedding model name.",
    )
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="Host interface to bind.",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8061,
        help="Port to bind.",
    )
    parser.add_argument(
        "--top-k",
        type=int,
        default=5,
        help="Number of ranked items to return per request.",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=64,
        help="Embedding batch size used while encoding the catalog.",
    )
    args = parser.parse_args()

    os.environ["IH_HF_MODEL_KIND"] = args.model_kind
    os.environ["IH_HF_ARTIFACT_DIR"] = args.artifact_dir
    if args.data_dir is not None:
        os.environ["IH_HF_DATA_DIR"] = args.data_dir
    os.environ["IH_HF_MODEL_NAME"] = args.model_name
    os.environ["IH_HF_TOP_K"] = str(args.top_k)
    os.environ["IH_HF_BATCH_SIZE"] = str(args.batch_size)

    uvicorn.run(create_app(), host=args.host, port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
