"""Typed shared contracts for the interaction harness."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

ActionName = Literal["click", "skip", "abandon"]
RiskSeverity = Literal["low", "medium", "high"]
TargetMode = Literal["reference_artifact", "external_url"]
FailureMode = Literal[
    "trust_collapse",
    "low_relevance",
    "over_repetition",
    "head_item_concentration",
    "poor_genre_alignment",
    "novelty_mismatch",
    "early_abandonment",
    "no_major_failure",
]


@dataclass(frozen=True)
class Item:
    item_id: str
    title: str
    genre: str
    popularity: float
    novelty: float
    quality: float


@dataclass(frozen=True)
class SlateItem:
    item_id: str
    title: str
    genre: str
    score: float
    rank: int
    popularity: float
    novelty: float


@dataclass(frozen=True)
class Slate:
    slate_id: str
    step_index: int
    items: tuple[SlateItem, ...]


@dataclass(frozen=True)
class RuntimeItemSignals:
    item_id: str
    rank: int
    base_relevance: float
    genre: str
    familiarity_signal: float
    novelty_signal: float
    quality_signal: float
    domain_tags: tuple[str, ...] = ()


@dataclass(frozen=True)
class AgentSeed:
    agent_id: str
    archetype_label: str
    preferred_genres: tuple[str, ...]
    popularity_preference: float
    novelty_preference: float
    repetition_tolerance: float
    sparse_history_confidence: float
    abandonment_sensitivity: float
    patience: int
    engagement_baseline: float
    quality_sensitivity: float
    repeat_exposure_penalty: float
    novelty_fatigue: float
    frustration_recovery: float
    history_reliance: float
    skip_tolerance: int
    abandonment_threshold: float


@dataclass(frozen=True)
class AgentState:
    agent_id: str
    archetype_label: str
    step_index: int
    click_threshold: float
    preferred_genres: tuple[str, ...]
    popularity_preference: float
    novelty_preference: float
    repetition_tolerance: float
    sparse_history_confidence: float
    abandonment_sensitivity: float
    engagement_baseline: float
    quality_sensitivity: float
    repeat_exposure_penalty: float
    novelty_fatigue: float
    frustration_recovery: float
    history_reliance: float
    skip_tolerance: int
    abandonment_threshold: float
    patience_remaining: int
    last_action: str
    history_item_ids: tuple[str, ...] = ()
    recent_exposure_ids: tuple[str, ...] = ()
    clicked_item_ids: tuple[str, ...] = ()
    skipped_steps: int = 0
    click_count: int = 0
    frustration: float = 0.0
    satisfaction: float = 0.0
    trust: float = 0.6
    confidence: float = 0.6


@dataclass(frozen=True)
class Action:
    name: ActionName
    selected_item_id: str | None
    reason: str


@dataclass(frozen=True)
class UtilityBreakdown:
    base_relevance: float
    affinity: float
    familiarity: float
    novelty: float
    quality: float
    repetition_penalty: float
    scenario_adjustment: float
    confidence_adjustment: float
    jitter: float
    total: float


@dataclass(frozen=True)
class DecisionExplanation:
    chosen_item_id: str | None
    top_candidate_item_id: str | None
    action_threshold: float
    chosen_utility: float
    top_candidate_utility: float
    dominant_component: str
    top_candidate_breakdown: UtilityBreakdown | None
    reason: str


@dataclass(frozen=True)
class ActionDecision:
    action: Action
    explanation: DecisionExplanation


@dataclass(frozen=True)
class ScenarioContext:
    scenario_name: str
    history_depth: int
    history_item_ids: tuple[str, ...]
    description: str


@dataclass(frozen=True)
class Observation:
    session_id: str
    step_index: int
    max_steps: int
    available_actions: tuple[ActionName, ...]
    scenario_context: ScenarioContext


@dataclass(frozen=True)
class AdapterRequest:
    request_id: str
    agent_id: str
    scenario_name: str
    step_index: int
    history_depth: int
    history_item_ids: tuple[str, ...]
    recent_exposure_ids: tuple[str, ...]
    preferred_genres: tuple[str, ...]


@dataclass(frozen=True)
class AdapterResponse:
    request_id: str
    items: tuple[SlateItem, ...]


@dataclass(frozen=True)
class TraceStep:
    step_index: int
    observation: Observation
    slate: Slate
    action: Action
    agent_state_before: AgentState
    agent_state_after: AgentState
    decision_explanation: DecisionExplanation | None = None
    state_delta_summary: str = ""


@dataclass(frozen=True)
class SessionTrace:
    trace_id: str
    seed: int
    agent_seed: AgentSeed
    scenario_name: str
    steps: tuple[TraceStep, ...]
    abandoned: bool
    completed_steps: int


@dataclass(frozen=True)
class ScenarioConfig:
    name: str
    max_steps: int
    allowed_actions: tuple[ActionName, ...]
    history_depth: int
    description: str


@dataclass(frozen=True)
class RolloutConfig:
    seed: int
    output_dir: str
    service_mode: str
    service_artifact_dir: str | None
    adapter_base_url: str | None
    service_timeout_seconds: float


@dataclass(frozen=True)
class ScoringConfig:
    utility_weight: float = 0.55
    frustration_weight: float = 0.45
    high_popularity_threshold: float = 0.75


@dataclass(frozen=True)
class RunConfig:
    run_name: str
    scenarios: tuple[ScenarioConfig, ...]
    rollout: RolloutConfig
    scoring: ScoringConfig
    agent_seeds: tuple[AgentSeed, ...]


@dataclass(frozen=True)
class TraceScore:
    trace_id: str
    scenario_name: str
    archetype_label: str
    steps_completed: int
    abandoned: bool
    click_count: int
    session_utility: float
    repetition: float
    concentration: float
    engagement: float
    frustration: float
    abandonment_step: int | None = None
    mean_click_quality: float = 0.0
    mean_top_candidate_utility: float = 0.0
    trust_delta: float = 0.0
    confidence_delta: float = 0.0
    frustration_delta: float = 0.0
    skip_rate: float = 0.0
    click_depth: float = 0.0
    stale_exposure_rate: float = 0.0
    genre_alignment_rate: float = 0.0
    novelty_intensity: float = 0.0
    dominant_failure_mode: FailureMode = "no_major_failure"
    trace_risk_score: float = 0.0
    failure_evidence_summary: str = ""


@dataclass(frozen=True)
class CohortSummary:
    scenario_name: str
    archetype_label: str
    trace_count: int
    abandonment_rate: float
    mean_session_utility: float
    mean_engagement: float
    mean_frustration: float
    risk_level: RiskSeverity
    representative_trace_id: str | None = None
    mean_trust_delta: float = 0.0
    mean_confidence_delta: float = 0.0
    mean_skip_rate: float = 0.0
    dominant_failure_mode: FailureMode = "no_major_failure"
    high_risk_trace_count: int = 0
    representative_success_trace_id: str | None = None
    representative_failure_trace_id: str | None = None


@dataclass(frozen=True)
class RiskFlag:
    scenario_name: str
    archetype_label: str
    severity: RiskSeverity
    message: str
    trace_id: str | None
    dominant_failure_mode: FailureMode = "no_major_failure"
    evidence_summary: str = ""


@dataclass(frozen=True)
class AnalysisResult:
    cohort_summaries: tuple[CohortSummary, ...]
    risk_flags: tuple[RiskFlag, ...]


@dataclass
class RunResult:
    run_config: RunConfig
    traces: tuple[SessionTrace, ...]
    trace_scores: tuple[TraceScore, ...]
    cohort_summaries: tuple[CohortSummary, ...]
    risk_flags: tuple[RiskFlag, ...]
    metadata: dict[str, str | int | float] = field(default_factory=dict)


@dataclass(frozen=True)
class RegressionTarget:
    label: str
    mode: TargetMode
    service_artifact_dir: str | None = None
    adapter_base_url: str | None = None


@dataclass(frozen=True)
class MetricSummary:
    metric_name: str
    mean: float
    minimum: float
    maximum: float
    spread: float


@dataclass(frozen=True)
class FailureModeCount:
    failure_mode: FailureMode
    count: int


@dataclass(frozen=True)
class RunArtifactPaths:
    seed: int
    output_dir: str
    report_path: str
    results_path: str
    traces_path: str
    chart_path: str


@dataclass(frozen=True)
class RerunSummary:
    target: RegressionTarget
    run_count: int
    seed_schedule: tuple[int, ...]
    metric_summaries: tuple[MetricSummary, ...]
    high_risk_cohort_count_mean: float
    dominant_failure_mode_counts: tuple[FailureModeCount, ...]
    metadata: dict[str, str | int | float] = field(default_factory=dict)
    run_artifacts: tuple[RunArtifactPaths, ...] = ()


@dataclass(frozen=True)
class MetricDelta:
    metric_name: str
    baseline_mean: float
    candidate_mean: float
    delta: float


@dataclass(frozen=True)
class CohortDelta:
    scenario_name: str
    archetype_label: str
    baseline_risk_level: RiskSeverity
    candidate_risk_level: RiskSeverity
    baseline_failure_mode: FailureMode
    candidate_failure_mode: FailureMode
    baseline_mean_session_utility: float
    candidate_mean_session_utility: float
    session_utility_delta: float
    abandonment_rate_delta: float
    trust_delta_delta: float
    skip_rate_delta: float


@dataclass(frozen=True)
class RiskFlagDelta:
    scenario_name: str
    archetype_label: str
    baseline_count: int
    candidate_count: int
    delta: int
    baseline_top_severity: RiskSeverity | None
    candidate_top_severity: RiskSeverity | None


@dataclass(frozen=True)
class TraceDelta:
    trace_id: str
    scenario_name: str
    archetype_label: str
    baseline_mean_utility: float
    candidate_mean_utility: float
    session_utility_delta: float
    baseline_mean_risk_score: float
    candidate_mean_risk_score: float
    trace_risk_score_delta: float
    baseline_failure_mode: FailureMode
    candidate_failure_mode: FailureMode


@dataclass(frozen=True)
class RegressionDiff:
    gating_mode: str
    baseline_summary: RerunSummary
    candidate_summary: RerunSummary
    metric_deltas: tuple[MetricDelta, ...]
    cohort_deltas: tuple[CohortDelta, ...]
    risk_flag_deltas: tuple[RiskFlagDelta, ...]
    notable_trace_deltas: tuple[TraceDelta, ...]
    metadata: dict[str, str | int | float] = field(default_factory=dict)
