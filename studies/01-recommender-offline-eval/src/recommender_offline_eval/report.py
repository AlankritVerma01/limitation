from __future__ import annotations

# ruff: noqa: E402
import json
import os
from pathlib import Path

from .paths import DEFAULT_CACHE_DIR, DEFAULT_OUTPUT_DIR

cache_root = DEFAULT_CACHE_DIR
cache_root.mkdir(parents=True, exist_ok=True)
matplotlib_cache = cache_root / "matplotlib"
matplotlib_cache.mkdir(parents=True, exist_ok=True)
os.environ.setdefault("XDG_CACHE_HOME", str(cache_root))
os.environ.setdefault("MPLCONFIGDIR", str(matplotlib_cache))

import matplotlib
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

matplotlib.use("Agg")


def aggregate_metrics_table(metrics: dict) -> pd.DataFrame:
    rows = []
    for model_name, model_metrics in metrics["models"].items():
        aggregate = model_metrics["aggregate"]
        rows.append(
            {
                "Model": model_name,
                "Recall@10": aggregate["recall_at_10"],
                "NDCG@10": aggregate["ndcg_at_10"],
                "Novelty": aggregate["novelty_score"],
                "Repetition": aggregate["repetition_score"],
                "Catalog concentration": aggregate["catalog_concentration"],
            }
        )
    return pd.DataFrame(rows)


def bucket_comparison_table(metrics: dict) -> pd.DataFrame:
    rows = []
    for bucket_name in metrics["models"]["Model A"]["buckets"]:
        a_metrics = metrics["models"]["Model A"]["buckets"][bucket_name]
        b_metrics = metrics["models"]["Model B"]["buckets"][bucket_name]
        rows.append(
            {
                "Bucket": bucket_name,
                "Model A utility": a_metrics["bucket_mean_utility"],
                "Model B utility": b_metrics["bucket_mean_utility"],
                "Delta (B-A)": b_metrics["bucket_mean_utility"]
                - a_metrics["bucket_mean_utility"],
                "Model A repetition": a_metrics["repetition_score"],
                "Model B repetition": b_metrics["repetition_score"],
                "Model A novelty": a_metrics["novelty_score"],
                "Model B novelty": b_metrics["novelty_score"],
            }
        )
    return pd.DataFrame(rows)


def behavior_metrics_table(metrics: dict) -> pd.DataFrame:
    rows = []
    for model_name, model_metrics in metrics["models"].items():
        aggregate = model_metrics["aggregate"]
        rows.append(
            {
                "Model": model_name,
                "Novelty score": aggregate["novelty_score"],
                "Repetition score": aggregate["repetition_score"],
                "Catalog concentration": aggregate["catalog_concentration"],
            }
        )
    return pd.DataFrame(rows)


def _markdown_table(frame: pd.DataFrame) -> str:
    headers = list(frame.columns)
    rows = [headers, ["---"] * len(headers)]
    for record in frame.to_dict(orient="records"):
        rendered = []
        for header in headers:
            value = record[header]
            if isinstance(value, float):
                rendered.append(f"{value:.3f}")
            else:
                rendered.append(str(value))
        rows.append(rendered)
    return "\n".join("| " + " | ".join(row) + " |" for row in rows)


def _json_default(value):
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, np.ndarray):
        return value.tolist()
    raise TypeError(f"Object of type {type(value)!r} is not JSON serializable")


def _trace_markdown(example: dict) -> str:
    lines = [
        f"### {example['bucket']} (user {example['user_id']}, delta {example['utility_delta']:.3f})",
        "",
    ]
    for model_name in ["Model A", "Model B"]:
        lines.append(f"**{model_name}**")
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
    buckets = list(metrics["models"]["Model A"]["buckets"].keys())
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

    plt.figure(figsize=(10, 5))
    plt.bar(x - width / 2, model_a_scores, width=width, label="Model A")
    plt.bar(x + width / 2, model_b_scores, width=width, label="Model B")
    plt.xticks(
        x,
        ["Conservative", "Explorer", "Niche", "Low-patience"],
        rotation=0,
    )
    plt.ylabel("Bucket mean utility")
    plt.title(
        "Bucketed utility exposes differences that aggregate offline metrics miss"
    )
    plt.legend()
    plt.tight_layout()
    plt.savefig(output_path, format="svg", bbox_inches="tight")
    plt.close()


def generate_report(metrics: dict, output_dir: str | Path = DEFAULT_OUTPUT_DIR) -> dict:
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    aggregate_df = aggregate_metrics_table(metrics)
    bucket_df = bucket_comparison_table(metrics)
    behavior_df = behavior_metrics_table(metrics)

    chart_path = output_path / "bucket_comparison.svg"
    metrics_path = output_path / "metrics.json"
    report_path = output_path / "report.md"

    _plot_bucket_comparison(metrics, chart_path)
    metrics_path.write_text(json.dumps(metrics, indent=2, default=_json_default))

    sections = [
        "# Offline Evaluation vs Bucketed/Trajectory Diagnostics",
        "",
        "## Dataset",
        "",
        f"- Users: {metrics['dataset']['users']}",
        f"- Items: {metrics['dataset']['items']}",
        f"- Ratings after filtering: {metrics['dataset']['ratings']}",
        "",
        "## Aggregate Offline Metrics",
        "",
        _markdown_table(aggregate_df),
        "",
        "## Bucket Comparison",
        "",
        _markdown_table(bucket_df),
        "",
        "## Behavior Diagnostics",
        "",
        _markdown_table(behavior_df),
        "",
        "## Plain-English Summaries",
        "",
    ]

    sections.extend([f"- {summary}" for summary in metrics["summaries"]])
    sections.extend(
        [
            "",
            "## Figure",
            "",
            f"See `{chart_path.name}` for the bucket utility comparison chart.",
            "",
            "## Example Traces",
            "",
        ]
    )
    sections.extend(_trace_markdown(example) for example in metrics["trace_examples"])

    report_path.write_text("\n".join(sections))

    return {
        "aggregate_table": aggregate_df,
        "bucket_table": bucket_df,
        "behavior_table": behavior_df,
        "report_path": report_path,
        "metrics_path": metrics_path,
        "chart_path": chart_path,
    }
