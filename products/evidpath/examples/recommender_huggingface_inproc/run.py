"""Run an in-process audit against a Hugging Face Pipeline."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from evidpath import audit
from evidpath.adapters.huggingface import wrap_pipeline

from .recsys import build_pipeline


def main() -> int:
    """Run the example audit."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--output-dir", type=str, default="./run-output")
    args = parser.parse_args()
    pipeline = build_pipeline()
    result = audit(
        callable=wrap_pipeline(pipeline),
        seed=args.seed,
        output_dir=args.output_dir,
        backend_name="hf-pipeline-example",
    )
    print(f"Audit complete. Run ID: {result.metadata.get('run_id', '<unknown>')}")
    print(f"Artifacts written to: {Path(args.output_dir).resolve()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
