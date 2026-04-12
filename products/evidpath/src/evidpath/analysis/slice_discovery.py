"""Deterministic feature-signature mining for discovered failure slices."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from hashlib import sha1
from itertools import combinations
from math import ceil

from ..schema import (
    SliceDiscoveryResult,
    SliceFeature,
    SliceMembership,
    SliceSummary,
    TraceScore,
)


@dataclass(frozen=True)
class SliceTraceInput:
    """One trace and the discrete features it contributes to slice mining."""

    trace_score: TraceScore
    features: tuple[SliceFeature, ...]


def discover_slices(
    trace_inputs: tuple[SliceTraceInput, ...],
    *,
    summarize_slice,
    top_limit: int = 5,
) -> SliceDiscoveryResult:
    """Build deterministic 1-feature and 2-feature slices from trace evidence."""
    if not trace_inputs:
        return SliceDiscoveryResult(slice_summaries=(), memberships=())

    min_support = max(2, ceil(len(trace_inputs) * 0.15))
    candidate_memberships: dict[tuple[str, ...], list[TraceScore]] = defaultdict(list)
    for trace_input in trace_inputs:
        labels = sorted(
            {
                _feature_label(feature)
                for feature in trace_input.features
            }
        )
        for size in (1, 2):
            for signature in combinations(labels, size):
                candidate_memberships[signature].append(trace_input.trace_score)

    scored_candidates = []
    for signature, scores in candidate_memberships.items():
        if len(scores) < min_support:
            continue
        summary = summarize_slice(signature, tuple(scores))
        priority = _slice_priority(summary, min_support)
        scored_candidates.append((priority, summary))

    scored_candidates.sort(
        key=lambda item: (
            item[0],
            item[1].slice_id,
        ),
        reverse=True,
    )

    seen_memberships: set[tuple[str, ...]] = set()
    surfaced_candidates: list[tuple[SliceSummary, tuple[str, ...]]] = []
    for _priority, summary in scored_candidates:
        full_membership_key = tuple(
            sorted(
                score.trace_id
                for score in candidate_memberships[summary.feature_signature]
            )
        )
        if full_membership_key in seen_memberships:
            continue
        seen_memberships.add(full_membership_key)
        surfaced_candidates.append((summary, full_membership_key))

    kept_candidates = surfaced_candidates[: max(top_limit * 3, top_limit)]
    return SliceDiscoveryResult(
        slice_summaries=tuple(summary for summary, _membership in kept_candidates),
        memberships=tuple(
            SliceMembership(slice_id=summary.slice_id, trace_id=trace_id)
            for summary, membership in kept_candidates
            for trace_id in membership
        ),
    )


def build_slice_id(feature_signature: tuple[str, ...]) -> str:
    """Build a short stable slice identifier from the feature signature."""
    digest = sha1("|".join(feature_signature).encode("utf-8")).hexdigest()[:12]
    return f"slice-{digest}"


def _feature_label(feature: SliceFeature) -> str:
    return f"{feature.key}={feature.value}"


def _slice_priority(summary: SliceSummary, min_support: int) -> tuple[float, ...]:
    support_bonus = summary.trace_count / max(min_support, 1)
    severity_bonus = {"low": 0.0, "medium": 1.0, "high": 2.0}[summary.risk_level]
    failure_bonus = 0.3 if summary.dominant_failure_mode != "no_major_failure" else 0.0
    utility_penalty = 1.0 - summary.mean_session_utility
    trust_penalty = max(0.0, -summary.mean_trust_delta)
    abandonment_bonus = summary.abandonment_rate
    skip_bonus = summary.mean_skip_rate
    risk_bonus = summary.mean_trace_risk_score
    return (
        severity_bonus + failure_bonus + risk_bonus,
        utility_penalty + trust_penalty + abandonment_bonus + skip_bonus,
        support_bonus,
        float(len(summary.feature_signature)),
    )
