"""Build a tiny Hugging Face-like pipeline for the in-process audit example."""

from __future__ import annotations


def build_pipeline():
    """Return a dummy callable that mimics an HF Pipeline output shape."""
    catalog = [
        {"item_id": "m1", "score": 0.91, "title": "Heat"},
        {"item_id": "m2", "score": 0.83, "title": "Drive"},
        {"item_id": "m3", "score": 0.74, "title": "Collateral"},
        {"item_id": "m4", "score": 0.66, "title": "Manhunter"},
        {"item_id": "m5", "score": 0.58, "title": "Thief"},
    ]

    def pipeline(_prompt: str):
        return list(catalog)

    return pipeline
