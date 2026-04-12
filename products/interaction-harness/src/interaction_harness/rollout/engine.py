"""Rollout loop for deterministic interaction traces."""

from __future__ import annotations

from random import Random

from ..adapters.base import SystemAdapter
from ..agents.base import AgentPolicy
from ..cli_app.progress import ProgressCallback, emit_progress
from ..scenarios.base import Scenario
from ..schema import RunConfig, SessionTrace, TraceStep


def run_rollouts(
    adapter: SystemAdapter,
    scenarios: tuple[Scenario, ...],
    agent_policy: AgentPolicy,
    run_config: RunConfig,
    *,
    progress_callback: ProgressCallback | None = None,
) -> tuple[SessionTrace, ...]:
    """Run seeded traces without scoring or report generation."""
    traces: list[SessionTrace] = []
    scenario_config_by_id = {
        (config.scenario_id or config.name): config for config in run_config.scenarios
    }
    total_traces = len(scenarios) * len(run_config.agent_seeds)
    completed_traces = 0
    emit_progress(
        progress_callback,
        phase="run_traces",
        message="Running traces",
        stage="start",
    )
    for scenario_index, scenario in enumerate(scenarios):
        matching_config = scenario_config_by_id.get(scenario.scenario_id)
        if matching_config is None:
            raise ValueError(f"Missing scenario config for scenario '{scenario.scenario_id}'.")
        for agent_index, agent_seed in enumerate(run_config.agent_seeds):
            trace_seed = run_config.rollout.seed + (scenario_index * 100) + agent_index
            rng = Random(trace_seed)
            observation = scenario.initialize(agent_seed, run_config)
            agent_state = agent_policy.initialize_state(
                agent_seed,
                observation.scenario_context,
            )
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
                    trace_id=f"{scenario.scenario_id}-{agent_seed.agent_id}",
                    seed=trace_seed,
                    agent_seed=agent_seed,
                    scenario_id=scenario.scenario_id,
                    scenario_name=scenario.name,
                    steps=tuple(trace_steps),
                    abandoned=abandoned,
                    completed_steps=len(trace_steps),
                )
            )
            completed_traces += 1
            emit_progress(
                progress_callback,
                phase="run_traces",
                message="Running traces",
                stage="update",
                current=completed_traces,
                total=total_traces,
            )
    emit_progress(
        progress_callback,
        phase="run_traces",
        message="Running traces",
        stage="finish",
    )
    return tuple(traces)
