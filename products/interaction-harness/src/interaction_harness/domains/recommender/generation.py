"""Recommender-owned generation prompts and fixture payload builders."""

from __future__ import annotations

from dataclasses import dataclass

from ...generation_support import extract_focus_tokens
from ...schema import AgentSeed, GeneratedPersona
from .scenarios import BUILT_IN_RECOMMENDER_SCENARIO_NAMES


def supported_recommender_generation_runtime_profiles() -> tuple[str, ...]:
    """Return the recommender runtime profiles supported in generated packs."""
    return BUILT_IN_RECOMMENDER_SCENARIO_NAMES


@dataclass(frozen=True)
class RecommenderPersonaProfile:
    """Normalized recommender persona hints used for projection and selection."""

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


def build_recommender_scenario_brief_clarification(brief: str) -> str | None:
    """Return a follow-up prompt when a scenario brief is too underspecified."""
    normalized = brief.strip()
    if len(normalized.split()) >= 2:
        return None
    return (
        "Scenario generation needs a more specific recommender goal. Mention the user group, "
        "surface, or behavior you want to test, for example new users, returning users, "
        "exploration quality, or trust recovery."
    )


def build_recommender_population_brief_clarification(brief: str) -> str | None:
    """Return a follow-up prompt when a population brief is too underspecified."""
    normalized = brief.strip()
    if len(normalized.split()) >= 2:
        return None
    return (
        "Population generation needs a more specific recommender audience. Mention who the users "
        "are or what behavioral mix you want, for example impatient new users, niche seekers, "
        "or mainstream viewers with low trust."
    )


def build_fixture_recommender_scenarios(
    brief: str,
    *,
    scenario_count: int,
) -> list[dict[str, object]]:
    """Build deterministic recommender scenario-pack entries for fixture mode."""
    focus_tokens = extract_focus_tokens(brief)
    focus_label = " ".join(focus_tokens[:3]) or "general recommendation quality"
    base_slug = "-".join(focus_tokens[:3]) or "generated"
    templates = (
        {
            "slug": "context-rich",
            "runtime_profile": "returning-user-home-feed",
            "history_depth": 4,
            "max_steps": 5,
            "risk_focus_tags": ["staleness", "over-specialization"],
            "description": (
                f"Returning-user session for `{focus_label}` with meaningful prior history."
            ),
            "test_goal": (
                f"Check whether the system keeps recommendations relevant without becoming stale around {focus_label}."
            ),
        },
        {
            "slug": "thin-context",
            "runtime_profile": "sparse-history-home-feed",
            "history_depth": 1,
            "max_steps": 5,
            "risk_focus_tags": ["cold-start", "popularity-bias"],
            "description": (
                f"Thin-context session for `{focus_label}` where the system has very little prior evidence."
            ),
            "test_goal": (
                f"Check whether the system falls back too hard to generic popularity when the brief is {focus_label}."
            ),
        },
        {
            "slug": "taste-elicitation",
            "runtime_profile": "taste-elicitation-home-feed",
            "history_depth": 0,
            "max_steps": 4,
            "risk_focus_tags": ["cold-start", "weak-first-impression", "novelty-mismatch"],
            "description": (
                f"Onboarding-style session for `{focus_label}` where the system needs to infer taste with almost no prior evidence."
            ),
            "test_goal": (
                f"Check whether the system can earn an early click for {focus_label} while still learning fresh taste signals."
            ),
        },
        {
            "slug": "exploration-pressure",
            "runtime_profile": "returning-user-home-feed",
            "history_depth": 2,
            "max_steps": 6,
            "risk_focus_tags": ["novelty-mismatch", "trust-drop"],
            "description": (
                f"Mixed-history session for `{focus_label}` with stronger pressure to balance novelty against familiarity."
            ),
            "test_goal": (
                f"Check whether the system explores enough for {focus_label} without causing trust collapse."
            ),
        },
        {
            "slug": "low-patience",
            "runtime_profile": "sparse-history-home-feed",
            "history_depth": 1,
            "max_steps": 4,
            "risk_focus_tags": ["early-abandonment", "weak-first-impression"],
            "description": (
                f"Short low-patience session for `{focus_label}` where the first few slates matter heavily."
            ),
            "test_goal": (
                f"Check whether the system earns early engagement for {focus_label} before patience runs out."
            ),
        },
        {
            "slug": "re-engagement",
            "runtime_profile": "re-engagement-home-feed",
            "history_depth": 2,
            "max_steps": 5,
            "risk_focus_tags": ["staleness", "trust-drop", "weak-first-impression"],
            "description": (
                f"Drifted-user return session for `{focus_label}` where stale or off-target recommendations can quickly collapse trust."
            ),
            "test_goal": (
                f"Check whether the system can rebuild trust for {focus_label} after a period of low engagement."
            ),
        },
    )
    scenarios: list[dict[str, object]] = []
    for index, template in enumerate(templates[:scenario_count], start=1):
        scenarios.append(
            {
                "scenario_id": f"{base_slug}-{template['slug']}-{index}",
                "name": f"{focus_label.title()} / {template['slug'].replace('-', ' ')}",
                "description": template["description"],
                "test_goal": template["test_goal"],
                "risk_focus_tags": template["risk_focus_tags"],
                "max_steps": template["max_steps"],
                "allowed_actions": ["click", "skip", "abandon"],
                "adapter_hints": {
                    "recommender": {
                        "runtime_profile": template["runtime_profile"],
                        "history_depth": template["history_depth"],
                        "context_hint": focus_label,
                    }
                },
            }
        )
    return scenarios


def build_recommender_scenario_generation_prompt(
    *,
    brief: str,
    scenario_count: int,
    domain_label: str,
) -> str:
    """Build the provider prompt for recommender scenario generation."""
    return (
        "You generate portable scenario packs for testing non-deterministic software.\n"
        "Return JSON only. No markdown, no prose outside the JSON object.\n"
        f"Generate exactly {scenario_count} scenarios for the domain `{domain_label}`.\n"
        "Return this exact top-level shape:\n"
        "{\n"
        '  "scenarios": [\n'
        "    {\n"
        '      "scenario_id": "string",\n'
        '      "name": "string",\n'
        '      "description": "string",\n'
        '      "test_goal": "string",\n'
        '      "risk_focus_tags": ["string"],\n'
        '      "max_steps": 5,\n'
        '      "allowed_actions": ["click", "skip", "abandon"],\n'
        '      "adapter_hints": {\n'
        '        "recommender": {\n'
        '          "runtime_profile": "returning-user-home-feed, sparse-history-home-feed, taste-elicitation-home-feed, or re-engagement-home-feed",\n'
        '          "history_depth": 1,\n'
        '          "context_hint": "string"\n'
        "        }\n"
        "      }\n"
        "    }\n"
        "  ]\n"
        "}\n"
        "Make the scenarios related but meaningfully different. Vary prior context, exploration pressure, "
        "and risk focus. Keep them clear, concise, and runtime-friendly.\n"
        f"Brief: {brief}"
    )


def build_fixture_recommender_population_candidates(
    brief: str,
    *,
    candidate_count: int,
) -> tuple[dict[str, object], ...]:
    """Build deterministic recommender population candidates for fixture mode."""
    focus_tokens = extract_focus_tokens(brief)
    focus_label = " ".join(focus_tokens[:3]) or "general recommendation quality"
    base_slug = "-".join(focus_tokens[:3]) or "population"
    templates = _fixture_persona_templates(focus_label)
    personas: list[dict[str, object]] = []
    for index in range(candidate_count):
        template = templates[index % len(templates)]
        personas.append(
            {
                "persona_id": f"{base_slug}-{template['slug']}-{index + 1}",
                "display_label": f"{template['label']} #{index + 1}",
                "persona_summary": template["persona_summary"],
                "behavior_goal": template["behavior_goal"],
                "diversity_tags": template["diversity_tags"],
                "adapter_hints": {"recommender": template["recommender_hints"]},
            }
        )
    return tuple(personas)


def build_recommender_population_generation_prompt(
    *,
    brief: str,
    candidate_count: int,
    domain_label: str,
) -> str:
    """Build the provider prompt for recommender population generation."""
    return (
        "You generate structured recommender population packs for testing recommendation systems.\n"
        "Return JSON only. No markdown, no prose outside the JSON object.\n"
        f"Generate exactly {candidate_count} candidate personas for the domain `{domain_label}`.\n"
        "Return this exact top-level shape:\n"
        "{\n"
        '  "target_population_size": 12,\n'
        '  "personas": [\n'
        "    {\n"
        '      "persona_id": "string",\n'
        '      "display_label": "string",\n'
        '      "persona_summary": "string",\n'
        '      "behavior_goal": "string",\n'
        '      "diversity_tags": ["string"],\n'
        '      "adapter_hints": {\n'
        '        "recommender": {\n'
        '          "preferred_genres": ["string"],\n'
        '          "popularity_preference": 0.5,\n'
        '          "novelty_preference": 0.5,\n'
        '          "repetition_tolerance": 0.5,\n'
        '          "sparse_history_confidence": 0.5,\n'
        '          "abandonment_sensitivity": 0.5,\n'
        '          "patience": 3,\n'
        '          "engagement_baseline": 0.5,\n'
        '          "quality_sensitivity": 0.5,\n'
        '          "repeat_exposure_penalty": 0.2,\n'
        '          "novelty_fatigue": 0.2,\n'
        '          "frustration_recovery": 0.2,\n'
        '          "history_reliance": 0.5,\n'
        '          "skip_tolerance": 2,\n'
        '          "abandonment_threshold": 0.6\n'
        "        }\n"
        "      }\n"
        "    }\n"
        "  ]\n"
        "}\n"
        "Choose `target_population_size` as the number of personas that should be kept "
        "for the final explicit swarm. Use a value between 6 and 18 based on the brief.\n"
        "Keep the personas meaningfully distinct across preference profile, novelty appetite, "
        "patience, abandonment behavior, and history reliance. Keep values between 0 and 1 where applicable.\n"
        f"Brief: {brief}"
    )


def project_recommender_persona_to_agent_seed(persona: GeneratedPersona) -> AgentSeed:
    """Project one generated recommender persona into the deterministic runtime seed."""
    profile = normalize_recommender_persona_profile(persona)
    return AgentSeed(
        agent_id=persona.persona_id,
        archetype_label=persona.display_label,
        preferred_genres=profile.preferred_genres,
        popularity_preference=profile.popularity_preference,
        novelty_preference=profile.novelty_preference,
        repetition_tolerance=profile.repetition_tolerance,
        sparse_history_confidence=profile.sparse_history_confidence,
        abandonment_sensitivity=profile.abandonment_sensitivity,
        patience=profile.patience,
        engagement_baseline=profile.engagement_baseline,
        quality_sensitivity=profile.quality_sensitivity,
        repeat_exposure_penalty=profile.repeat_exposure_penalty,
        novelty_fatigue=profile.novelty_fatigue,
        frustration_recovery=profile.frustration_recovery,
        history_reliance=profile.history_reliance,
        skip_tolerance=profile.skip_tolerance,
        abandonment_threshold=profile.abandonment_threshold,
        persona_summary=persona.persona_summary,
        behavior_goal=persona.behavior_goal,
        diversity_tags=persona.diversity_tags,
    )


def select_recommender_population_personas(
    personas: tuple[GeneratedPersona, ...],
    target_population_size: int,
) -> tuple[GeneratedPersona, ...]:
    """Keep an explicit recommender swarm with deterministic diversity coverage."""
    if len(personas) <= target_population_size:
        return personas
    ordered_candidates = sorted(personas, key=lambda persona: persona.persona_id)
    selected: list[GeneratedPersona] = []
    while ordered_candidates and len(selected) < target_population_size:
        best = max(
            ordered_candidates,
            key=lambda persona: (
                _marginal_diversity_score(persona, tuple(selected)),
                -ordered_candidates.index(persona),
            ),
        )
        selected.append(best)
        ordered_candidates.remove(best)
    return tuple(selected)


def normalize_recommender_persona_profile(
    persona: GeneratedPersona,
) -> RecommenderPersonaProfile:
    """Normalize and validate recommender hints before projection or selection."""
    hints = _require_recommender_hints(persona)
    return RecommenderPersonaProfile(
        preferred_genres=tuple(
            _require_hint_string_list(hints, persona.persona_id, "preferred_genres")
        ),
        popularity_preference=_require_hint_float(
            hints, persona.persona_id, "popularity_preference"
        ),
        novelty_preference=_require_hint_float(
            hints, persona.persona_id, "novelty_preference"
        ),
        repetition_tolerance=_require_hint_float(
            hints, persona.persona_id, "repetition_tolerance"
        ),
        sparse_history_confidence=_require_hint_float(
            hints, persona.persona_id, "sparse_history_confidence"
        ),
        abandonment_sensitivity=_require_hint_float(
            hints, persona.persona_id, "abandonment_sensitivity"
        ),
        patience=_require_hint_int(hints, persona.persona_id, "patience", minimum=1),
        engagement_baseline=_require_hint_float(
            hints, persona.persona_id, "engagement_baseline"
        ),
        quality_sensitivity=_require_hint_float(
            hints, persona.persona_id, "quality_sensitivity"
        ),
        repeat_exposure_penalty=_require_hint_float(
            hints, persona.persona_id, "repeat_exposure_penalty"
        ),
        novelty_fatigue=_require_hint_float(
            hints, persona.persona_id, "novelty_fatigue"
        ),
        frustration_recovery=_require_hint_float(
            hints, persona.persona_id, "frustration_recovery"
        ),
        history_reliance=_require_hint_float(
            hints, persona.persona_id, "history_reliance"
        ),
        skip_tolerance=_require_hint_int(
            hints, persona.persona_id, "skip_tolerance", minimum=0
        ),
        abandonment_threshold=_require_hint_float(
            hints, persona.persona_id, "abandonment_threshold"
        ),
    )


def _fixture_persona_templates(focus_label: str) -> tuple[dict[str, object], ...]:
    """Return stable recommender persona templates for fixture generation."""
    return (
        _template(
            slug="mainstream",
            label="Conservative mainstream",
            summary=f"Popular familiar viewer around {focus_label}.",
            goal=f"Stress whether the system stays reliable and not overly stale for {focus_label}.",
            tags=("mainstream", "familiarity", "high-popularity"),
            genres=("action", "comedy", "family"),
            popularity=0.92,
            novelty=0.18,
            repetition=0.82,
            sparse_confidence=0.55,
            abandonment=0.45,
            patience=3,
            engagement=0.66,
            quality=0.52,
            repeat_penalty=0.18,
            novelty_fatigue=0.22,
            frustration_recovery=0.14,
            history_reliance=0.82,
            skip_tolerance=2,
            abandonment_threshold=0.68,
        ),
        _template(
            slug="explorer",
            label="Explorer / novelty-seeking",
            summary=f"Novelty-hungry viewer around {focus_label}.",
            goal=f"Stress whether the system explores enough for {focus_label} without breaking trust.",
            tags=("exploration", "novelty", "indie"),
            genres=("sci-fi", "thriller", "indie"),
            popularity=0.32,
            novelty=0.92,
            repetition=0.24,
            sparse_confidence=0.62,
            abandonment=0.38,
            patience=3,
            engagement=0.58,
            quality=0.61,
            repeat_penalty=0.08,
            novelty_fatigue=0.44,
            frustration_recovery=0.12,
            history_reliance=0.36,
            skip_tolerance=3,
            abandonment_threshold=0.76,
        ),
        _template(
            slug="niche",
            label="Niche-interest",
            summary=f"Genre-loyal specialist around {focus_label}.",
            goal=f"Stress whether the system respects niche intent for {focus_label}.",
            tags=("niche", "genre-loyal", "high-quality"),
            genres=("horror", "documentary", "indie"),
            popularity=0.28,
            novelty=0.78,
            repetition=0.45,
            sparse_confidence=0.41,
            abandonment=0.52,
            patience=3,
            engagement=0.54,
            quality=0.72,
            repeat_penalty=0.15,
            novelty_fatigue=0.30,
            frustration_recovery=0.11,
            history_reliance=0.74,
            skip_tolerance=2,
            abandonment_threshold=0.71,
        ),
        _template(
            slug="low-patience",
            label="Low-patience",
            summary=f"Quick-bounce viewer around {focus_label}.",
            goal=f"Stress whether early slates hook users focused on {focus_label}.",
            tags=("low-patience", "first-impression", "bounce-risk"),
            genres=("action", "drama", "comedy"),
            popularity=0.81,
            novelty=0.33,
            repetition=0.31,
            sparse_confidence=0.48,
            abandonment=0.92,
            patience=2,
            engagement=0.63,
            quality=0.48,
            repeat_penalty=0.24,
            novelty_fatigue=0.18,
            frustration_recovery=0.08,
            history_reliance=0.58,
            skip_tolerance=1,
            abandonment_threshold=0.52,
        ),
        _template(
            slug="quality-first",
            label="Quality-first skeptic",
            summary=f"Quality-sensitive viewer around {focus_label}.",
            goal=f"Stress whether the system avoids low-quality filler for {focus_label}.",
            tags=("quality", "skeptical", "trust"),
            genres=("drama", "documentary", "thriller"),
            popularity=0.39,
            novelty=0.58,
            repetition=0.34,
            sparse_confidence=0.44,
            abandonment=0.61,
            patience=3,
            engagement=0.49,
            quality=0.92,
            repeat_penalty=0.18,
            novelty_fatigue=0.20,
            frustration_recovery=0.16,
            history_reliance=0.66,
            skip_tolerance=2,
            abandonment_threshold=0.61,
        ),
        _template(
            slug="headline-chaser",
            label="Headline chaser",
            summary=f"Popularity-anchored viewer around {focus_label}.",
            goal=f"Stress whether the system over-indexes on obvious hits for {focus_label}.",
            tags=("head-items", "popularity", "mainstream"),
            genres=("action", "thriller", "family"),
            popularity=0.96,
            novelty=0.14,
            repetition=0.74,
            sparse_confidence=0.72,
            abandonment=0.36,
            patience=4,
            engagement=0.71,
            quality=0.41,
            repeat_penalty=0.14,
            novelty_fatigue=0.12,
            frustration_recovery=0.20,
            history_reliance=0.48,
            skip_tolerance=3,
            abandonment_threshold=0.73,
        ),
        _template(
            slug="cold-start-fragile",
            label="Cold-start fragile",
            summary=f"User with weak history confidence around {focus_label}.",
            goal=f"Stress cold-start behavior for {focus_label} without over-falling back to generic popularity.",
            tags=("cold-start", "fragile", "trust"),
            genres=("comedy", "sci-fi", "documentary"),
            popularity=0.57,
            novelty=0.51,
            repetition=0.29,
            sparse_confidence=0.16,
            abandonment=0.74,
            patience=2,
            engagement=0.42,
            quality=0.56,
            repeat_penalty=0.21,
            novelty_fatigue=0.26,
            frustration_recovery=0.09,
            history_reliance=0.22,
            skip_tolerance=1,
            abandonment_threshold=0.49,
        ),
        _template(
            slug="slow-burn-curious",
            label="Slow-burn curious",
            summary=f"Patient mixed-intent viewer around {focus_label}.",
            goal=f"Stress long-session balance of exploration and coherence for {focus_label}.",
            tags=("patient", "curious", "mixed-intent"),
            genres=("drama", "sci-fi", "indie"),
            popularity=0.46,
            novelty=0.68,
            repetition=0.42,
            sparse_confidence=0.52,
            abandonment=0.27,
            patience=5,
            engagement=0.57,
            quality=0.69,
            repeat_penalty=0.11,
            novelty_fatigue=0.31,
            frustration_recovery=0.28,
            history_reliance=0.59,
            skip_tolerance=4,
            abandonment_threshold=0.82,
        ),
        _template(
            slug="comfort-loop",
            label="Comfort-loop loyalist",
            summary=f"Familiarity-seeking repeat viewer around {focus_label}.",
            goal=f"Stress over-repetition risk while preserving comfort for {focus_label}.",
            tags=("comfort", "repeat", "loyalist"),
            genres=("family", "comedy", "romance"),
            popularity=0.74,
            novelty=0.19,
            repetition=0.94,
            sparse_confidence=0.63,
            abandonment=0.25,
            patience=4,
            engagement=0.69,
            quality=0.44,
            repeat_penalty=0.05,
            novelty_fatigue=0.14,
            frustration_recovery=0.24,
            history_reliance=0.88,
            skip_tolerance=4,
            abandonment_threshold=0.85,
        ),
        _template(
            slug="novelty-fragile",
            label="Novelty-fragile experimenter",
            summary=f"Exploration-friendly but trust-sensitive viewer around {focus_label}.",
            goal=f"Stress whether the system can explore for {focus_label} without abrupt trust collapse.",
            tags=("exploration", "fragile", "trust"),
            genres=("thriller", "indie", "documentary"),
            popularity=0.33,
            novelty=0.83,
            repetition=0.26,
            sparse_confidence=0.57,
            abandonment=0.68,
            patience=3,
            engagement=0.53,
            quality=0.67,
            repeat_penalty=0.12,
            novelty_fatigue=0.52,
            frustration_recovery=0.10,
            history_reliance=0.31,
            skip_tolerance=2,
            abandonment_threshold=0.58,
        ),
        _template(
            slug="head-to-tail-bridge",
            label="Head-to-tail bridge",
            summary=f"User who likes a mix of hits and long-tail items around {focus_label}.",
            goal=f"Stress balance between relevance and discovery for {focus_label}.",
            tags=("balanced", "head-tail", "bridge"),
            genres=("action", "indie", "documentary"),
            popularity=0.61,
            novelty=0.61,
            repetition=0.36,
            sparse_confidence=0.49,
            abandonment=0.43,
            patience=4,
            engagement=0.60,
            quality=0.66,
            repeat_penalty=0.17,
            novelty_fatigue=0.24,
            frustration_recovery=0.17,
            history_reliance=0.53,
            skip_tolerance=3,
            abandonment_threshold=0.69,
        ),
        _template(
            slug="precision-seeker",
            label="Precision seeker",
            summary=f"High-alignment viewer around {focus_label}.",
            goal=f"Stress whether the system stays tightly relevant for {focus_label} without collapsing diversity.",
            tags=("precision", "alignment", "relevance"),
            genres=("documentary", "drama", "sci-fi"),
            popularity=0.42,
            novelty=0.47,
            repetition=0.28,
            sparse_confidence=0.37,
            abandonment=0.55,
            patience=3,
            engagement=0.50,
            quality=0.84,
            repeat_penalty=0.20,
            novelty_fatigue=0.17,
            frustration_recovery=0.13,
            history_reliance=0.79,
            skip_tolerance=2,
            abandonment_threshold=0.64,
        ),
        _template(
            slug="casual-wanderer",
            label="Casual wanderer",
            summary=f"Light-intent browsing viewer around {focus_label}.",
            goal=f"Stress whether the system can keep casual sessions alive for {focus_label}.",
            tags=("casual", "browsing", "low-commitment"),
            genres=("comedy", "family", "sci-fi"),
            popularity=0.63,
            novelty=0.44,
            repetition=0.47,
            sparse_confidence=0.68,
            abandonment=0.34,
            patience=4,
            engagement=0.56,
            quality=0.38,
            repeat_penalty=0.14,
            novelty_fatigue=0.22,
            frustration_recovery=0.21,
            history_reliance=0.35,
            skip_tolerance=3,
            abandonment_threshold=0.74,
        ),
        _template(
            slug="strict-filter",
            label="Strict filterer",
            summary=f"Low-noise viewer around {focus_label}.",
            goal=f"Stress whether noisy or generic items break confidence for {focus_label}.",
            tags=("strict", "low-noise", "quality"),
            genres=("thriller", "documentary", "drama"),
            popularity=0.27,
            novelty=0.55,
            repetition=0.19,
            sparse_confidence=0.33,
            abandonment=0.77,
            patience=2,
            engagement=0.43,
            quality=0.89,
            repeat_penalty=0.28,
            novelty_fatigue=0.25,
            frustration_recovery=0.07,
            history_reliance=0.71,
            skip_tolerance=1,
            abandonment_threshold=0.47,
        ),
    )


def _template(
    *,
    slug: str,
    label: str,
    summary: str,
    goal: str,
    tags: tuple[str, ...],
    genres: tuple[str, ...],
    popularity: float,
    novelty: float,
    repetition: float,
    sparse_confidence: float,
    abandonment: float,
    patience: int,
    engagement: float,
    quality: float,
    repeat_penalty: float,
    novelty_fatigue: float,
    frustration_recovery: float,
    history_reliance: float,
    skip_tolerance: int,
    abandonment_threshold: float,
) -> dict[str, object]:
    """Build one fixture persona template."""
    return {
        "slug": slug,
        "label": label,
        "persona_summary": summary,
        "behavior_goal": goal,
        "diversity_tags": list(tags),
        "recommender_hints": {
            "preferred_genres": list(genres),
            "popularity_preference": popularity,
            "novelty_preference": novelty,
            "repetition_tolerance": repetition,
            "sparse_history_confidence": sparse_confidence,
            "abandonment_sensitivity": abandonment,
            "patience": patience,
            "engagement_baseline": engagement,
            "quality_sensitivity": quality,
            "repeat_exposure_penalty": repeat_penalty,
            "novelty_fatigue": novelty_fatigue,
            "frustration_recovery": frustration_recovery,
            "history_reliance": history_reliance,
            "skip_tolerance": skip_tolerance,
            "abandonment_threshold": abandonment_threshold,
        },
    }


def _marginal_diversity_score(
    persona: GeneratedPersona,
    selected: tuple[GeneratedPersona, ...],
) -> int:
    signature = _persona_signature(persona)
    if not selected:
        return len(signature)
    covered = set().union(*(_persona_signature(existing) for existing in selected))
    new_signal_count = len(signature.difference(covered))
    tag_bonus = len(set(persona.diversity_tags).difference(*(set(p.diversity_tags) for p in selected)))
    genre_bonus = len(set(normalize_recommender_persona_profile(persona).preferred_genres[:2]).difference(
        *(set(normalize_recommender_persona_profile(existing).preferred_genres[:2]) for existing in selected)
    ))
    return new_signal_count + tag_bonus + genre_bonus


def _persona_signature(persona: GeneratedPersona) -> set[str]:
    profile = normalize_recommender_persona_profile(persona)
    signature = {f"genre:{genre}" for genre in profile.preferred_genres[:2]}
    signature.update(
        {
            f"popularity:{_bucket(profile.popularity_preference)}",
            f"novelty:{_bucket(profile.novelty_preference)}",
            f"patience:{profile.patience}",
            f"abandonment:{_bucket(profile.abandonment_sensitivity)}",
            f"history:{_bucket(profile.history_reliance)}",
            f"quality:{_bucket(profile.quality_sensitivity)}",
        }
    )
    signature.update(f"tag:{tag}" for tag in persona.diversity_tags)
    return signature


def _bucket(value: float) -> str:
    if value < 0.34:
        return "low"
    if value < 0.67:
        return "mid"
    return "high"


def _require_recommender_hints(
    persona: GeneratedPersona,
) -> dict[str, str | int | float | bool | list[str]]:
    hints = persona.adapter_hints.get("recommender")
    if not isinstance(hints, dict):
        raise ValueError(f"Persona `{persona.persona_id}` is missing recommender adapter hints.")
    return hints


def _require_hint_string_list(
    hints: dict[str, str | int | float | bool | list[str]],
    persona_id: str,
    key: str,
) -> list[str]:
    value = hints.get(key)
    if not isinstance(value, list) or not value or not all(isinstance(item, str) for item in value):
        raise ValueError(f"Persona `{persona_id}` has invalid recommender hint `{key}`.")
    normalized = [item.strip() for item in value if item.strip()]
    if not normalized:
        raise ValueError(f"Persona `{persona_id}` has invalid recommender hint `{key}`.")
    return normalized


def _require_hint_float(
    hints: dict[str, str | int | float | bool | list[str]],
    persona_id: str,
    key: str,
) -> float:
    value = hints.get(key)
    if not isinstance(value, int | float) or isinstance(value, bool):
        raise ValueError(f"Persona `{persona_id}` has invalid recommender hint `{key}`.")
    normalized = float(value)
    if not 0.0 <= normalized <= 1.0:
        raise ValueError(f"Persona `{persona_id}` has out-of-range recommender hint `{key}`.")
    return normalized


def _require_hint_int(
    hints: dict[str, str | int | float | bool | list[str]],
    persona_id: str,
    key: str,
    *,
    minimum: int,
) -> int:
    value = hints.get(key)
    if not isinstance(value, int) or isinstance(value, bool) or value < minimum:
        raise ValueError(f"Persona `{persona_id}` has invalid recommender hint `{key}`.")
    return value
