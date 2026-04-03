"""Public artifact rendering for recommender evaluation runs.

This module converts evaluated metrics into the stable public outputs: markdown,
JSON, and one reusable SVG chart.
"""

from __future__ import annotations

# ruff: noqa: E402
import json
import os
import re
from pathlib import Path

from .canonical import (
    BUCKET_DESCRIPTIONS,
    BUCKET_ORDER,
    CANONICAL_RUN_CONFIG,
    METRIC_DEFINITIONS,
)
from .config import EvaluationConfig
from .paths import DEFAULT_CACHE_DIR, DEFAULT_OUTPUT_DIR

cache_root = DEFAULT_CACHE_DIR
cache_root.mkdir(parents=True, exist_ok=True)
matplotlib_cache = cache_root / "matplotlib"
matplotlib_cache.mkdir(parents=True, exist_ok=True)
os.environ.setdefault("XDG_CACHE_HOME", str(cache_root))
os.environ.setdefault("MPLCONFIGDIR", str(matplotlib_cache))

import matplotlib

matplotlib.use("Agg")
matplotlib.rcParams["svg.hashsalt"] = "limitation-phase1"

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

CHART_FILENAME = "bucket_utility_comparison.svg"
DEFAULT_JSON_FILENAME = "results.json"
DEFAULT_REPORT_FILENAME = "report.md"
CANONICAL_JSON_FILENAME = "official_demo_results.json"
CANONICAL_REPORT_FILENAME = "official_demo_report.md"


def _is_canonical_run(config: EvaluationConfig) -> bool:
    return config.artifact_mode == "canonical"


def artifact_filenames(config: EvaluationConfig) -> dict[str, str]:
    if _is_canonical_run(config):
        return {
            "chart": CHART_FILENAME,
            "json": CANONICAL_JSON_FILENAME,
            "report": CANONICAL_REPORT_FILENAME,
        }
    return {
        "chart": CHART_FILENAME,
        "json": DEFAULT_JSON_FILENAME,
        "report": DEFAULT_REPORT_FILENAME,
    }


def _model_label(metrics: dict, model_name: str) -> str:
    return metrics["model_specs"][model_name]["label"]


def aggregate_metrics_table(metrics: dict) -> pd.DataFrame:
    rows = []
    for model_name in ["Model A", "Model B"]:
        aggregate = metrics["models"][model_name]["aggregate"]
        rows.append(
            {
                "Model": model_name,
                "Recall@10": aggregate["recall_at_10"],
                "NDCG@10": aggregate["ndcg_at_10"],
            }
        )
    return pd.DataFrame(rows)


def bucket_comparison_table(metrics: dict) -> pd.DataFrame:
    rows = []
    for bucket_name in BUCKET_ORDER:
        a_metrics = metrics["models"]["Model A"]["buckets"][bucket_name]
        b_metrics = metrics["models"]["Model B"]["buckets"][bucket_name]
        rows.append(
            {
                "Bucket": bucket_name,
                "Model A": a_metrics["bucket_mean_utility"],
                "Model B": b_metrics["bucket_mean_utility"],
                "Delta (B-A)": b_metrics["bucket_mean_utility"]
                - a_metrics["bucket_mean_utility"],
            }
        )
    return pd.DataFrame(rows)


def behavior_metrics_table(metrics: dict) -> pd.DataFrame:
    rows = []
    for model_name in ["Model A", "Model B"]:
        aggregate = metrics["models"][model_name]["aggregate"]
        rows.append(
            {
                "Model": model_name,
                "Novelty": aggregate["novelty_score"],
                "Repetition": aggregate["repetition_score"],
                "Catalog concentration": aggregate["catalog_concentration"],
            }
        )
    return pd.DataFrame(rows)


def _frame_rows(frame: pd.DataFrame) -> list[dict]:
    rows = []
    for record in frame.to_dict(orient="records"):
        rendered = {}
        for key, value in record.items():
            rendered[key] = round(value, 6) if isinstance(value, float) else value
        rows.append(rendered)
    return rows


def _markdown_table(frame: pd.DataFrame) -> str:
    headers = list(frame.columns)
    rows = [headers, ["---"] * len(headers)]
    for record in frame.to_dict(orient="records"):
        rendered = []
        for header in headers:
            value = record[header]
            rendered.append(f"{value:.3f}" if isinstance(value, float) else str(value))
        rows.append(rendered)
    return "\n".join("| " + " | ".join(row) + " |" for row in rows)


def _json_default(value):
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, np.ndarray):
        return value.tolist()
    raise TypeError(f"Object of type {type(value)!r} is not JSON serializable")


def _bucket_glossary_lines() -> list[str]:
    return [
        f"- **{bucket_name}**: {BUCKET_DESCRIPTIONS[bucket_name]}"
        for bucket_name in BUCKET_ORDER
    ]


def _metric_definition_lines(metric_names: list[str]) -> list[str]:
    return [f"- **{name}**: {METRIC_DEFINITIONS[name]}" for name in metric_names]


def _run_summary_paragraph(metrics: dict, config: EvaluationConfig) -> str:
    baseline_label = _model_label(metrics, "Model A")
    candidate_label = _model_label(metrics, "Model B")
    if _is_canonical_run(config):
        return (
            f"This canonical Phase 1 run evaluates {config.dataset.name} with Model A "
            f"({baseline_label}) and Model B ({candidate_label}) across the fixed four "
            "user buckets to show where aggregate offline metrics hide segment-level "
            "and behavioral tradeoffs."
        )
    return (
        f"This run evaluates {config.dataset.name} with Model A ({baseline_label}) and "
        f"Model B ({candidate_label}) across the fixed four user buckets using the same "
        "behavioral QA report structure as the canonical demo."
    )


def _trace_markdown(example: dict, metrics: dict) -> str:
    lines = [
        f"### {example['bucket']} (user {example['user_id']}, delta {example['utility_delta']:.3f})",
        "",
    ]
    for model_name in ["Model A", "Model B"]:
        lines.append(f"**{model_name} — {_model_label(metrics, model_name)}**")
        lines.append("")
        lines.append(
            "| Step | Title | Utility | Affinity | Popularity | Novelty | Repetition penalty |"
        )
        lines.append("| --- | --- | --- | --- | --- | --- | --- |")
        for step in example[model_name]["trace"]:
            lines.append(
                "| "
                + " | ".join(
                    [
                        str(step["step"]),
                        step["title"].replace("|", "/"),
                        f"{step['utility']:.3f}",
                        f"{step['affinity']:.3f}",
                        f"{step['popularity']:.3f}",
                        f"{step['novelty']:.3f}",
                        f"{step['repetition_penalty']:.3f}",
                    ]
                )
                + " |"
            )
        lines.append("")
    return "\n".join(lines)


def _plot_bucket_comparison(metrics: dict, output_path: Path) -> None:
    buckets = BUCKET_ORDER
    model_a_scores = [
        metrics["models"]["Model A"]["buckets"][bucket]["bucket_mean_utility"]
        for bucket in buckets
    ]
    model_b_scores = [
        metrics["models"]["Model B"]["buckets"][bucket]["bucket_mean_utility"]
        for bucket in buckets
    ]

    x = np.arange(len(buckets))
    width = 0.34

    fig, ax = plt.subplots(figsize=(10, 5))
    ax.bar(x - width / 2, model_a_scores, width=width, label="Model A")
    ax.bar(x + width / 2, model_b_scores, width=width, label="Model B")
    ax.set_xticks(x)
    ax.set_xticklabels(["Conservative", "Explorer", "Niche", "Low-patience"])
    ax.set_ylabel("Bucket utility")
    ax.set_title("Bucket-level utility comparison")
    ax.legend()
    fig.tight_layout()
    fig.savefig(
        output_path,
        format="svg",
        bbox_inches="tight",
        metadata={"Date": None},
    )
    plt.close(fig)

    # Strip volatile metadata so the committed canonical SVG stays diff-stable.
    svg = output_path.read_text()
    svg = re.sub(r"<metadata>.*?</metadata>", "", svg, flags=re.DOTALL)
    output_path.write_text(svg)


def _run_summary(metrics: dict, config: EvaluationConfig) -> dict:
    dataset_source = metrics["dataset_source"]
    return {
        "paragraph": _run_summary_paragraph(metrics, config),
        "dataset": config.dataset.name,
        "dataset_type": dataset_source["dataset_type"],
        "dataset_id": dataset_source["dataset_id"],
        "dataset_path": dataset_source["dataset_path"],
        "dataset_stats": metrics["dataset_summary"],
        "models": {
            "Model A": metrics["model_specs"]["Model A"],
            "Model B": metrics["model_specs"]["Model B"],
        },
        "buckets": [
            {"name": bucket_name, "description": BUCKET_DESCRIPTIONS[bucket_name]}
            for bucket_name in BUCKET_ORDER
        ],
        "purpose": (
            "Compare a baseline and candidate recommender in one reproducible run and "
            "surface hidden tradeoffs before launch."
        ),
    }


def _reproducibility_summary(metrics: dict, config: EvaluationConfig) -> dict:
    dataset_source = metrics["dataset_source"]
    return {
        "dataset": config.dataset.name,
        "dataset_type": dataset_source["dataset_type"],
        "dataset_id": dataset_source["dataset_id"],
        "dataset_path": dataset_source["dataset_path"],
        "fixed_buckets": BUCKET_ORDER,
        "baseline_model": metrics["model_specs"]["Model A"],
        "candidate_model": metrics["model_specs"]["Model B"],
        "effective_config": {
            "top_k": config.top_k,
            "session_steps": config.session_steps,
            "slate_size": config.slate_size,
            "choice_pool": config.choice_pool,
            "positive_rating_threshold": config.positive_rating_threshold,
            "min_user_ratings": config.min_user_ratings,
            "min_user_positive_ratings": config.min_user_positive_ratings,
            "test_holdout_positive_count": config.test_holdout_positive_count,
        },
        "seed": config.seed,
    }


def build_public_results(
    metrics: dict,
    config: EvaluationConfig = CANONICAL_RUN_CONFIG,
) -> dict:
    aggregate_df = aggregate_metrics_table(metrics)
    bucket_df = bucket_comparison_table(metrics)
    behavior_df = behavior_metrics_table(metrics)
    run_summary = _run_summary(metrics, config)

    return {
        "run_summary": run_summary,
        "offline_metrics": {
            "rows": _frame_rows(aggregate_df),
            "metric_definitions": {
                "Recall@10": METRIC_DEFINITIONS["Recall@10"],
                "NDCG@10": METRIC_DEFINITIONS["NDCG@10"],
            },
        },
        "bucket_utility": {
            "bucket_definitions": run_summary["buckets"],
            "rows": _frame_rows(bucket_df),
            "metric_definition": METRIC_DEFINITIONS["Bucket utility"],
        },
        "behavioral_diagnostics": {
            "rows": _frame_rows(behavior_df),
            "metric_definitions": {
                "Novelty": METRIC_DEFINITIONS["Novelty"],
                "Repetition": METRIC_DEFINITIONS["Repetition"],
                "Catalog concentration": METRIC_DEFINITIONS[
                    "Catalog concentration"
                ],
            },
            "chart": CHART_FILENAME,
        },
        "key_takeaways": list(metrics["summaries"]),
        "trace_examples": metrics["trace_examples"],
        "reproducibility": _reproducibility_summary(metrics, config),
    }


def _report_title(config: EvaluationConfig) -> str:
    return (
        "# Official MovieLens Demo"
        if _is_canonical_run(config)
        else "# Recommender Evaluation Report"
    )


def _render_markdown_report(
    *,
    metrics: dict,
    public_results: dict,
    aggregate_df: pd.DataFrame,
    bucket_df: pd.DataFrame,
    behavior_df: pd.DataFrame,
    chart_name: str,
    config: EvaluationConfig,
) -> str:
    dataset_path = public_results["reproducibility"]["dataset_path"] or "built-in dataset"
    sections = [
        _report_title(config),
        "",
        "## Run summary",
        "",
        public_results["run_summary"]["paragraph"],
        "",
        "## Standard offline metrics",
        "",
        _markdown_table(aggregate_df),
        "",
    ]
    sections.extend(_metric_definition_lines(["Recall@10", "NDCG@10"]))
    sections.extend(
        [
            "",
            "## Bucket-level utility",
            "",
            "Bucket glossary:",
            "",
        ]
    )
    sections.extend(_bucket_glossary_lines())
    sections.extend(
        [
            "",
            _markdown_table(bucket_df),
            "",
            f"- **Bucket utility**: {METRIC_DEFINITIONS['Bucket utility']}",
            "",
            "## Behavioral diagnostics",
            "",
            _markdown_table(behavior_df),
            "",
            f"See `{chart_name}` for the bucket utility comparison chart.",
            "",
        ]
    )
    sections.extend(
        _metric_definition_lines(["Novelty", "Repetition", "Catalog concentration"])
    )
    sections.extend(["", "## Key takeaways", ""])
    sections.extend([f"- {summary}" for summary in public_results["key_takeaways"]])
    sections.extend(["", "## Short traces", ""])
    sections.extend(
        _trace_markdown(example, metrics) for example in public_results["trace_examples"]
    )
    sections.extend(
        [
            "## Reproducibility note",
            "",
            f"- Dataset: {public_results['reproducibility']['dataset']} ({public_results['reproducibility']['dataset_type']})",
            f"- Dataset id: {public_results['reproducibility']['dataset_id']}",
            f"- Dataset path: {dataset_path}",
            f"- Fixed buckets: {', '.join(BUCKET_ORDER)}",
            "- Effective config: "
            f"top_k={config.top_k}, session_steps={config.session_steps}, "
            f"slate_size={config.slate_size}, choice_pool={config.choice_pool}, "
            f"positive_rating_threshold={config.positive_rating_threshold}, "
            f"min_user_ratings={config.min_user_ratings}, "
            f"min_user_positive_ratings={config.min_user_positive_ratings}, "
            f"test_holdout_positive_count={config.test_holdout_positive_count}",
            f"- Baseline model: {_model_label(metrics, 'Model A')} ({metrics['model_specs']['Model A']['type']})",
            f"- Candidate model: {_model_label(metrics, 'Model B')} ({metrics['model_specs']['Model B']['type']})",
            f"- Fixed seed: {config.seed}",
            "",
        ]
    )
    return "\n".join(sections)


def generate_report(
    metrics: dict,
    output_dir: str | Path = DEFAULT_OUTPUT_DIR,
    config: EvaluationConfig = CANONICAL_RUN_CONFIG,
) -> dict:
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    filenames = artifact_filenames(config)
    aggregate_df = aggregate_metrics_table(metrics)
    bucket_df = bucket_comparison_table(metrics)
    behavior_df = behavior_metrics_table(metrics)
    public_results = build_public_results(metrics=metrics, config=config)

    chart_path = output_path / filenames["chart"]
    metrics_path = output_path / filenames["json"]
    report_path = output_path / filenames["report"]

    _plot_bucket_comparison(metrics, chart_path)
    metrics_path.write_text(
        json.dumps(public_results, indent=2, default=_json_default) + "\n"
    )
    report_path.write_text(
        _render_markdown_report(
            metrics=metrics,
            public_results=public_results,
            aggregate_df=aggregate_df,
            bucket_df=bucket_df,
            behavior_df=behavior_df,
            chart_name=chart_path.name,
            config=config,
        )
    )

    return {
        "aggregate_table": aggregate_df,
        "bucket_table": bucket_df,
        "behavior_table": behavior_df,
        "public_results": public_results,
        "report_path": report_path,
        "metrics_path": metrics_path,
        "chart_path": chart_path,
    }
