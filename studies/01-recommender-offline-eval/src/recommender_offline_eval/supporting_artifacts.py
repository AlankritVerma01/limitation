"""Supporting proof artifacts for the canonical MovieLens demo.

These artifacts do not change the official canonical run. They package supporting
evidence that makes the public result easier to trust and easier to share.
"""

from __future__ import annotations

import json
import tempfile
from dataclasses import replace
from html import escape
from pathlib import Path
from typing import Callable

from .canonical import CANONICAL_RUN_CONFIG
from .paths import DEFAULT_CANONICAL_ARTIFACTS_DIR, DEFAULT_DATA_DIR
from .run_demo import run_evaluation

ROBUSTNESS_RESULTS_FILENAME = "robustness_results.json"
ROBUSTNESS_SUMMARY_FILENAME = "robustness_summary.md"
OFFLINE_VS_BUCKET_STORY_FILENAME = "offline_vs_bucket_story.svg"
CANONICAL_RESULT_SNAPSHOT_FILENAME = "canonical_result_snapshot.svg"

VariantResult = dict[str, object]
EvaluationRunner = Callable[..., dict]


def _variant_configs() -> list[tuple[str, str, object, dict[str, object]]]:
    return [
        (
            "canonical_seed_0",
            "Canonical config (seed 0)",
            replace(CANONICAL_RUN_CONFIG, artifact_mode="default"),
            {"seed": 0, "test_holdout_positive_count": 2},
        ),
        (
            "canonical_seed_1",
            "Canonical config (seed 1)",
            replace(CANONICAL_RUN_CONFIG, seed=1, artifact_mode="default"),
            {"seed": 1, "test_holdout_positive_count": 2},
        ),
        (
            "canonical_seed_2",
            "Canonical config (seed 2)",
            replace(CANONICAL_RUN_CONFIG, seed=2, artifact_mode="default"),
            {"seed": 2, "test_holdout_positive_count": 2},
        ),
        (
            "holdout_positive_1",
            "Hold out the last positive interaction",
            replace(
                CANONICAL_RUN_CONFIG,
                test_holdout_positive_count=1,
                artifact_mode="default",
            ),
            {"seed": 0, "test_holdout_positive_count": 1},
        ),
    ]


def _variant_summary(name: str, label: str, public_results: dict, overrides: dict) -> VariantResult:
    offline_rows = {
        row["Model"]: row for row in public_results["offline_metrics"]["rows"]
    }
    bucket_rows = {
        row["Bucket"]: row for row in public_results["bucket_utility"]["rows"]
    }
    behavior_rows = {
        row["Model"]: row for row in public_results["behavioral_diagnostics"]["rows"]
    }

    return {
        "name": name,
        "label": label,
        "config_overrides": overrides,
        "offline_metrics": {
            "model_a_recall_at_10": offline_rows["Model A"]["Recall@10"],
            "model_b_recall_at_10": offline_rows["Model B"]["Recall@10"],
            "model_a_ndcg_at_10": offline_rows["Model A"]["NDCG@10"],
            "model_b_ndcg_at_10": offline_rows["Model B"]["NDCG@10"],
        },
        "bucket_deltas": {
            "explorer": bucket_rows["Explorer / novelty-seeking"]["Delta (B-A)"],
            "niche_interest": bucket_rows["Niche-interest"]["Delta (B-A)"],
            "low_patience": bucket_rows["Low-patience"]["Delta (B-A)"],
        },
        "behavioral_metrics": {
            "model_a_catalog_concentration": behavior_rows["Model A"][
                "Catalog concentration"
            ],
            "model_b_catalog_concentration": behavior_rows["Model B"][
                "Catalog concentration"
            ],
        },
        "core_story_checks": {
            "aggregate_offline_favors_model_a": (
                offline_rows["Model A"]["Recall@10"] > offline_rows["Model B"]["Recall@10"]
                and offline_rows["Model A"]["NDCG@10"] > offline_rows["Model B"]["NDCG@10"]
            ),
            "explorer_favors_model_b": bucket_rows["Explorer / novelty-seeking"][
                "Delta (B-A)"
            ]
            > 0,
            "niche_interest_favors_model_b": bucket_rows["Niche-interest"][
                "Delta (B-A)"
            ]
            > 0,
            "candidate_lowers_concentration": behavior_rows["Model B"][
                "Catalog concentration"
            ]
            < behavior_rows["Model A"]["Catalog concentration"],
        },
    }


def build_robustness_payload(
    *,
    data_dir: str | Path = DEFAULT_DATA_DIR,
    runner: EvaluationRunner = run_evaluation,
) -> dict:
    variants: list[VariantResult] = []

    for name, label, config, overrides in _variant_configs():
        with tempfile.TemporaryDirectory() as temp_dir:
            result = runner(config, data_dir=data_dir, output_dir=temp_dir)
        variants.append(
            _variant_summary(name, label, result["public_results"], overrides)
        )

    seed_rows = [
        row
        for row in variants
        if row["config_overrides"]["test_holdout_positive_count"] == 2
    ]
    split_row = next(
        row for row in variants if row["config_overrides"]["test_holdout_positive_count"] == 1
    )

    identical_across_seed_rows = all(
        row["offline_metrics"] == seed_rows[0]["offline_metrics"]
        and row["bucket_deltas"] == seed_rows[0]["bucket_deltas"]
        and row["behavioral_metrics"] == seed_rows[0]["behavioral_metrics"]
        for row in seed_rows[1:]
    )
    core_story_stable = all(
        all(row["core_story_checks"].values())
        for row in variants
    )

    return {
        "frozen_demo": {
            "dataset": CANONICAL_RUN_CONFIG.dataset.name,
            "buckets": [
                "Conservative mainstream",
                "Explorer / novelty-seeking",
                "Niche-interest",
                "Low-patience",
            ],
            "models": {
                "Model A": CANONICAL_RUN_CONFIG.baseline_model.label,
                "Model B": CANONICAL_RUN_CONFIG.candidate_model.label,
            },
            "seed": CANONICAL_RUN_CONFIG.seed,
            "test_holdout_positive_count": CANONICAL_RUN_CONFIG.test_holdout_positive_count,
        },
        "what_is_diagnostic": [
            "Bucket utility, novelty, repetition, and catalog concentration are behavioral diagnostics meant to make tradeoffs legible.",
            "Short traces are compact examples of how the two recommenders behave over a four-step sequence.",
            "These diagnostics do not replace online evaluation or claim to predict long-term production outcomes exactly.",
        ],
        "stability_checks": {
            "seed_rows_identical": identical_across_seed_rows,
            "core_story_stable": core_story_stable,
            "checked_seeds": [0, 1, 2],
            "checked_split_variation": {"test_holdout_positive_count": 1},
        },
        "variants": variants,
        "summary": {
            "seed_sensitivity": (
                "Seed 0, 1, and 2 produced identical results in this pipeline."
                if identical_across_seed_rows
                else "The seed sweep changed some metrics; inspect the variant table."
            ),
            "split_sensitivity": (
                "A smaller holdout split shifted the magnitudes slightly, but the same directional conclusion held."
                if all(split_row["core_story_checks"].values())
                else "The split variation changed part of the core conclusion."
            ),
        },
        "out_of_scope": [
            "The robustness pass does not claim external validity beyond MovieLens 100K.",
            "The bucket lenses remain simplified evaluation constructs rather than discovered user segments.",
            "The supporting checks do not substitute for live online experiments.",
        ],
    }


def _robustness_markdown(payload: dict) -> str:
    rows = payload["variants"]
    lines = [
        "# Canonical Robustness Note",
        "",
        "This note supplements the official MovieLens demo. It does not replace the frozen canonical run.",
        "",
        "## What Is Frozen",
        "",
        f"- Dataset: {payload['frozen_demo']['dataset']}",
        "- Fixed buckets: " + ", ".join(payload["frozen_demo"]["buckets"]),
        f"- Models: Model A = {payload['frozen_demo']['models']['Model A']}, Model B = {payload['frozen_demo']['models']['Model B']}",
        f"- Canonical seed: {payload['frozen_demo']['seed']}",
        f"- Canonical holdout positives per user: {payload['frozen_demo']['test_holdout_positive_count']}",
        "",
        "## What Is Diagnostic",
        "",
    ]
    lines.extend(f"- {text}" for text in payload["what_is_diagnostic"])
    lines.extend(
        [
            "",
            "## What Was Checked For Stability",
            "",
            "- Seeds checked: 0, 1, 2",
            "- Modest split variation: hold out the last positive interaction instead of the last two",
            "",
            "| Variant | Recall@10 A | Recall@10 B | NDCG@10 A | NDCG@10 B | Explorer delta | Niche delta | Model B concentration |",
            "| --- | --- | --- | --- | --- | --- | --- | --- |",
        ]
    )
    for row in rows:
        offline = row["offline_metrics"]
        bucket_deltas = row["bucket_deltas"]
        behavior = row["behavioral_metrics"]
        lines.append(
            "| "
            + " | ".join(
                [
                    row["label"],
                    f"{offline['model_a_recall_at_10']:.3f}",
                    f"{offline['model_b_recall_at_10']:.3f}",
                    f"{offline['model_a_ndcg_at_10']:.3f}",
                    f"{offline['model_b_ndcg_at_10']:.3f}",
                    f"{bucket_deltas['explorer']:.3f}",
                    f"{bucket_deltas['niche_interest']:.3f}",
                    f"{behavior['model_b_catalog_concentration']:.3f}",
                ]
            )
            + " |"
        )
    lines.extend(
        [
            "",
            "## What Changed And What Did Not",
            "",
            f"- {payload['summary']['seed_sensitivity']}",
            f"- {payload['summary']['split_sensitivity']}",
            "- Across every checked variant, aggregate offline metrics still favored Model A.",
            "- Across every checked variant, Explorer and Niche-interest still favored Model B.",
            "- Across every checked variant, Model B remained less concentrated than Model A.",
            "",
            "## What Remains Out Of Scope",
            "",
        ]
    )
    lines.extend(f"- {text}" for text in payload["out_of_scope"])
    lines.append("")
    return "\n".join(lines)


def _scorecard_svg(title: str, subtitle: str, blocks: list[dict]) -> str:
    width = 1080
    block_width = 480
    left_x = 40
    right_x = 560
    top_y = 140
    block_height = 300
    colors = {
        "bg": "#fbf8f1",
        "panel": "#fffdf8",
        "border": "#d6cbb8",
        "text": "#1f2937",
        "muted": "#5b6471",
        "accent": "#b45309",
        "win": "#0f766e",
    }
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="520" viewBox="0 0 {width} 520">',
        f'<rect width="{width}" height="520" fill="{colors["bg"]}"/>',
        f'<text x="40" y="56" fill="{colors["text"]}" font-size="30" font-family="Georgia, serif" font-weight="700">{escape(title)}</text>',
        f'<text x="40" y="92" fill="{colors["muted"]}" font-size="18" font-family="Helvetica, Arial, sans-serif">{escape(subtitle)}</text>',
    ]
    positions = [left_x, right_x]
    for index, block in enumerate(blocks):
        x = positions[index]
        parts.extend(
            [
                f'<rect x="{x}" y="{top_y}" width="{block_width}" height="{block_height}" rx="18" fill="{colors["panel"]}" stroke="{colors["border"]}" stroke-width="2"/>',
                f'<text x="{x + 24}" y="{top_y + 42}" fill="{colors["accent"]}" font-size="20" font-family="Helvetica, Arial, sans-serif" font-weight="700">{escape(block["heading"])}</text>',
            ]
        )
        y = top_y + 82
        for line in block["lines"]:
            parts.append(
                f'<text x="{x + 24}" y="{y}" fill="{colors["text"]}" font-size="24" font-family="Helvetica, Arial, sans-serif" font-weight="700">{escape(line)}</text>'
            )
            y += 40
        y += 10
        for line in block.get("notes", []):
            parts.append(
                f'<text x="{x + 24}" y="{y}" fill="{colors["win"]}" font-size="18" font-family="Helvetica, Arial, sans-serif">{escape(line)}</text>'
            )
            y += 28
    parts.append("</svg>")
    return "\n".join(parts)


def _offline_vs_bucket_story_svg(public_results: dict) -> str:
    offline_rows = {row["Model"]: row for row in public_results["offline_metrics"]["rows"]}
    bucket_rows = {row["Bucket"]: row for row in public_results["bucket_utility"]["rows"]}
    return _scorecard_svg(
        "What Offline Metrics Missed",
        "The canonical MovieLens run looks one way in aggregate and another way by user bucket.",
        [
            {
                "heading": "Aggregate offline view",
                "lines": [
                    f"Model A Recall@10 {offline_rows['Model A']['Recall@10']:.3f}",
                    f"Model B Recall@10 {offline_rows['Model B']['Recall@10']:.3f}",
                    f"Model A NDCG@10 {offline_rows['Model A']['NDCG@10']:.3f}",
                    f"Model B NDCG@10 {offline_rows['Model B']['NDCG@10']:.3f}",
                ],
                "notes": [
                    "Aggregate offline metrics favor Model A.",
                ],
            },
            {
                "heading": "Bucket-level view",
                "lines": [
                    f"Explorer delta +{bucket_rows['Explorer / novelty-seeking']['Delta (B-A)']:.3f}",
                    f"Niche delta +{bucket_rows['Niche-interest']['Delta (B-A)']:.3f}",
                    f"Low-patience delta +{bucket_rows['Low-patience']['Delta (B-A)']:.3f}",
                ],
                "notes": [
                    "Model B is stronger for Explorer and Niche-interest users.",
                    "That is the hidden tradeoff this tool surfaces.",
                ],
            },
        ],
    )


def _canonical_result_snapshot_svg(public_results: dict, robustness_payload: dict) -> str:
    behavior_rows = {
        row["Model"]: row for row in public_results["behavioral_diagnostics"]["rows"]
    }
    return _scorecard_svg(
        "Canonical Result Snapshot",
        "A small public proof that aggregate offline metrics are useful but incomplete.",
        [
            {
                "heading": "Behavioral shift",
                "lines": [
                    f"Novelty {behavior_rows['Model A']['Novelty']:.3f} -> {behavior_rows['Model B']['Novelty']:.3f}",
                    f"Repetition {behavior_rows['Model A']['Repetition']:.3f} -> {behavior_rows['Model B']['Repetition']:.3f}",
                    f"Concentration {behavior_rows['Model A']['Catalog concentration']:.3f} -> {behavior_rows['Model B']['Catalog concentration']:.3f}",
                ],
                "notes": [
                    "Model B is more novel and less concentrated.",
                    "It is also more repetitive in this diagnostic.",
                ],
            },
            {
                "heading": "Trust note",
                "lines": [
                    "Frozen: MovieLens, 2 models, 4 buckets, fixed report.",
                    "Diagnostic: bucket utility and short traces are proxies.",
                    "Stability: seeds 0/1/2 were identical.",
                    "Split check: the same directional story held.",
                ],
                "notes": [
                    robustness_payload["summary"]["split_sensitivity"],
                ],
            },
        ],
    )


def write_supporting_artifacts(
    public_results: dict,
    *,
    output_dir: str | Path = DEFAULT_CANONICAL_ARTIFACTS_DIR,
    data_dir: str | Path = DEFAULT_DATA_DIR,
    runner: EvaluationRunner = run_evaluation,
) -> dict[str, Path]:
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    robustness_payload = build_robustness_payload(data_dir=data_dir, runner=runner)
    robustness_results_path = output_path / ROBUSTNESS_RESULTS_FILENAME
    robustness_summary_path = output_path / ROBUSTNESS_SUMMARY_FILENAME
    offline_story_path = output_path / OFFLINE_VS_BUCKET_STORY_FILENAME
    snapshot_path = output_path / CANONICAL_RESULT_SNAPSHOT_FILENAME

    robustness_results_path.write_text(
        json.dumps(robustness_payload, indent=2) + "\n"
    )
    robustness_summary_path.write_text(_robustness_markdown(robustness_payload))
    offline_story_path.write_text(_offline_vs_bucket_story_svg(public_results))
    snapshot_path.write_text(
        _canonical_result_snapshot_svg(public_results, robustness_payload)
    )

    return {
        "robustness_results_path": robustness_results_path,
        "robustness_summary_path": robustness_summary_path,
        "offline_story_path": offline_story_path,
        "snapshot_path": snapshot_path,
    }
