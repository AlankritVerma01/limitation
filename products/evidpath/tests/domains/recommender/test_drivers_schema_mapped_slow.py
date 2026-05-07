"""Slow end-to-end tests for the schema-mapped recommender driver."""

from __future__ import annotations

import json
import sys
import threading
from http.server import HTTPServer
from pathlib import Path

from evidpath.artifacts.run_manifest import write_run_manifest
from evidpath.audit import execute_domain_audit, write_run_artifacts


def test_schema_mapped_audit_against_example_server(tmp_path: Path) -> None:
    examples_root = Path(__file__).resolve().parents[3]
    sys.path.insert(0, str(examples_root))
    try:
        from examples.recommender_external_shape.server import _Handler
    finally:
        sys.path.remove(str(examples_root))

    server = HTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        run_result = execute_domain_audit(
            domain_name="recommender",
            seed=11,
            output_dir=str(tmp_path / "schema-mapped-audit"),
            scenario_names=("returning-user-home-feed",),
            driver_kind="http_schema_mapped",
            driver_config={
                "base_url": f"http://127.0.0.1:{server.server_port}",
                "timeout_seconds": 2.0,
                "predict": {
                    "method": "POST",
                    "path": "/v1/predict",
                    "body": {
                        "user_id": "${agent_id}",
                        "history": "${history_item_ids}",
                        "n": 5,
                    },
                    "response": {
                        "items_path": "predictions",
                        "item_id_field": "movie_id",
                        "score_field": "confidence",
                        "title_field": "title",
                    },
                },
                "health": {"method": "GET", "path": "/healthz"},
            },
        )
        paths = write_run_artifacts(run_result)
        manifest_path = write_run_manifest(
            run_result,
            artifact_paths=paths,
            workflow_type="audit",
        )
        manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8"))

        assert manifest["service"]["target_driver_kind"] == "http_schema_mapped"
        assert run_result.trace_scores
    finally:
        server.shutdown()
