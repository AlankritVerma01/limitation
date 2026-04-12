"""Simple SVG chart output for cohort summaries."""

from __future__ import annotations

from pathlib import Path

from ..schema import RunResult


class CohortChartWriter:
    """Writes a small SVG summary of mean session utility by cohort."""

    def write(self, run_result: RunResult, output_dir: Path) -> dict[str, str]:
        output_dir.mkdir(parents=True, exist_ok=True)
        chart_path = output_dir / "cohort_summary_chart.svg"
        summaries = run_result.cohort_summaries
        width = 980
        row_height = 44
        height = 110 + (row_height * len(summaries))
        max_bar = 360
        lines = [
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
            f'<rect width="{width}" height="{height}" fill="#fbf8f1"/>',
            '<text x="36" y="42" fill="#1f2937" font-size="28" font-family="Georgia, serif" font-weight="700">Cohort Utility Summary</text>',
            '<text x="36" y="72" fill="#5b6471" font-size="16" font-family="Helvetica, Arial, sans-serif">Mean session utility by scenario and archetype.</text>',
        ]
        for index, summary in enumerate(summaries):
            y = 108 + (index * row_height)
            bar_width = max(0.0, summary.mean_session_utility) * max_bar
            fill = "#b45309" if summary.risk_level == "high" else "#0f766e" if summary.risk_level == "low" else "#d97706"
            label = f"{summary.scenario_name} / {summary.archetype_label}"
            lines.extend(
                [
                    f'<text x="36" y="{y}" fill="#1f2937" font-size="14" font-family="Helvetica, Arial, sans-serif">{label}</text>',
                    f'<rect x="520" y="{y - 14}" width="{max_bar}" height="14" fill="#e7e1d4" rx="6"/>',
                    f'<rect x="520" y="{y - 14}" width="{bar_width:.1f}" height="14" fill="{fill}" rx="6"/>',
                    f'<text x="895" y="{y}" fill="#1f2937" font-size="13" font-family="Helvetica, Arial, sans-serif">{summary.mean_session_utility:.3f}</text>',
                ]
            )
        lines.append("</svg>")
        chart_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return {"chart_path": str(chart_path)}
