"""Rollout loop for the first real recommender interaction flow."""

from __future__ import annotations

from random import Random

from ..adapters.base import SystemAdapter
from ..agents.base import AgentPolicy
from ..agents.recommender import initial_state_from_seed
from ..scenarios.base import Scenario
from ..schema import RunConfig, SessionTrace, TraceStep


def run_rollouts(
    adapter: SystemAdapter,
    scenarios: tuple[Scenario, ...],
    agent_policy: AgentPolicy,
    run_config: RunConfig,
) -> tuple[SessionTrace, ...]:
    """Run seeded traces without scoring or report generation."""
    traces: list[SessionTrace] = []
    for scenario_index, scenario in enumerate(scenarios):
        matching_config = next(
            config for config in run_config.scenarios if config.name == scenario.name
        )
        for agent_index, agent_seed in enumerate(run_config.agent_seeds):
            trace_seed = run_config.rollout.seed + (scenario_index * 100) + agent_index
            rng = Random(trace_seed)
            observation = scenario.initialize(agent_seed, run_config)
            agent_state = initial_state_from_seed(agent_seed, observation.scenario_context)
            trace_steps: list[TraceStep] = []
            abandoned = False

            while not scenario.should_stop(observation):
                slate = adapter.get_slate(agent_state, observation, matching_config)
                decision = agent_policy.choose_action(
                    agent_state,
                    slate,
                    observation,
                    matching_config,
                    rng,
                )
                updated_state = agent_policy.update_state(
                    agent_state,
                    decision,
                    slate,
                    observation,
                    rng,
                )
                state_delta_summary = agent_policy.summarize_state_delta(
                    agent_state,
                    updated_state,
                    decision,
                    observation,
                )
                trace_steps.append(
                    TraceStep(
                        step_index=observation.step_index,
                        observation=observation,
                        slate=slate,
                        action=decision.action,
                        agent_state_before=agent_state,
                        agent_state_after=updated_state,
                        decision_explanation=decision.explanation,
                        state_delta_summary=state_delta_summary,
                    )
                )
                agent_state = updated_state
                if decision.action.name == "abandon":
                    abandoned = True
                    break
                observation = scenario.next_observation(observation, run_config)

            traces.append(
                SessionTrace(
                    trace_id=f"{scenario.name}-{agent_seed.agent_id}",
                    seed=trace_seed,
                    agent_seed=agent_seed,
                    scenario_name=scenario.name,
                    steps=tuple(trace_steps),
                    abandoned=abandoned,
                    completed_steps=len(trace_steps),
                )
            )
    return tuple(traces)
