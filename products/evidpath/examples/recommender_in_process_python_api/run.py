"""Run an audit against the example callable using the Python API."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from evidpath import audit

from .recsys import predict


def main() -> int:
    """Run the example audit."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--output-dir", type=str, default="./run-output")
    args = parser.parse_args()
    result = audit(
        callable=predict,
        seed=args.seed,
        output_dir=args.output_dir,
        backend_name="popularity-example",
    )
    print(f"Audit complete. Run ID: {result.metadata.get('run_id', '<unknown>')}")
    print(f"Artifacts written to: {Path(args.output_dir).resolve()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
