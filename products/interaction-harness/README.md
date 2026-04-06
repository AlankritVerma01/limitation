# Interaction Harness

This package is the active product track for the repository.

It is intentionally separate from the older
`studies/01-recommender-offline-eval` proof package.

## What It Does

Interaction Harness is a deterministic interaction-testing tool.

In the current build, it audits recommender systems by:

1. calling a system under test through a normalized adapter
2. running seeded synthetic users through short scenarios
3. recording the full session trace
4. judging the completed trace deterministically
5. summarizing cohort-level risks and representative traces
6. optionally comparing baseline vs candidate systems across reruns

Today it is recommender-first. Over time, the same core is meant to support broader non-deterministic systems without throwing away the rollout, judging, and regression machinery.

## Current Capabilities

- a real local reference recommender service
- an HTTP recommender adapter
- a local mock service kept only for narrow tests
- two recommender scenarios:
  - returning-user home feed
  - sparse-history home feed
- built-in four-seed deterministic baseline population
- saved recommender population packs with explicit generated swarms
- explicit agent state and decision explanations
- deterministic judging, cohort analysis, and failure surfacing
- deterministic discovered failure slices from trace evidence
- opt-in advisory semantic interpretation for traces and regression changes
- rerun-based regression comparisons with deterministic `pass` / `warn` /
  `fail` decisions
- structured AI-authored scenario packs with saved portable contracts
- markdown, JSON, trace, and chart artifacts

## How It Differs From The Existing Study

The existing study package is a public offline-evaluation proof.

This new package is the foundation for a broader interaction-testing product:

- system adapter
- seeded agents
- rollout engine
- judge
- analyzer
- reproducibility harness
- report

The product remains independent from the study package. Ideas are reused, but the new runtime does not import the old `recommender_offline_eval` code.

## Package Layout

- `src/interaction_harness/cli.py`
  - CLI entrypoint for single-run and compare modes
- `src/interaction_harness/audit.py`
  - single-run orchestration
- `src/interaction_harness/regression.py`
  - reruns and baseline-vs-candidate orchestration
- `src/interaction_harness/scenario_generation.py`
  - scenario-pack generation, validation, storage, and recommender projection
- `src/interaction_harness/population_generation.py`
  - recommender population-pack generation, selection, storage, and projection
- `src/interaction_harness/services/`
  - local reference service, mock fixture, and reference artifacts
- `src/interaction_harness/adapters/`
  - system-under-test adapter layer
- `src/interaction_harness/agents/`
  - seeded synthetic user policies
- `src/interaction_harness/rollout/`
  - session execution loop
- `src/interaction_harness/judges/`
  - deterministic trace scoring
- `src/interaction_harness/analysis/`
  - cohort-level summarization and risk surfacing
- `src/interaction_harness/reporting/`
  - markdown, JSON, and chart writers

## Run The Recommender Audit

From the repository root:

```bash
PYTHONPATH=products/interaction-harness/src .venv/bin/python -m interaction_harness
```

Run one scenario only:

```bash
PYTHONPATH=products/interaction-harness/src .venv/bin/python -m interaction_harness --scenario returning-user-home-feed --seed 7 --service-artifact-dir products/interaction-harness/output/reference-artifacts --output-dir products/interaction-harness/output/demo
```

Generate a saved scenario pack from a brief with the deterministic fixture path:

```bash
PYTHONPATH=products/interaction-harness/src .venv/bin/python -m interaction_harness --generate-scenarios --generation-mode fixture --scenario-brief "test recommendation quality for sparse-history users who still want novelty" --output-dir products/interaction-harness/output/generated-scenarios
```

Generate a saved scenario pack through the provider-backed path:

```bash
PYTHONPATH=products/interaction-harness/src .venv/bin/python -m interaction_harness --generate-scenarios --generation-mode provider --scenario-brief "test trust and exploration balance for returning users" --scenario-pack-path products/interaction-harness/output/generated-scenarios/provider-pack.json
```

Provider mode will auto-read a root `.env` when present. Useful environment
variables:

- `OPENAI_API_KEY`
- `OPENAI_BASE_URL`
- `OPENAI_TIMEOUT_SECONDS`
- `OPENAI_RETRY_COUNT`

Reuse a saved scenario pack in a normal audit run:

```bash
PYTHONPATH=products/interaction-harness/src .venv/bin/python -m interaction_harness --scenario-pack-path products/interaction-harness/output/generated-scenarios/provider-pack.json --service-mode mock --output-dir products/interaction-harness/output/generated-pack-run
```

Generate a saved recommender population pack with the deterministic fixture path:

```bash
PYTHONPATH=products/interaction-harness/src .venv/bin/python -m interaction_harness --generate-population --population-generation-mode fixture --population-brief "test a broad swarm of novelty-seeking and low-patience viewers" --population-size 12 --output-dir products/interaction-harness/output/generated-populations
```

Generate a saved recommender population pack through the provider-backed path:

```bash
PYTHONPATH=products/interaction-harness/src .venv/bin/python -m interaction_harness --generate-population --population-generation-mode provider --population-brief "test a broad swarm of risk-sensitive and exploration-seeking viewers" --population-pack-path products/interaction-harness/output/generated-populations/provider-population.json
```

If `--population-size` is omitted, provider mode may suggest the final explicit
swarm size. Fixture mode falls back to the default size of `12`.

Reuse a saved population pack in a normal audit run:

```bash
PYTHONPATH=products/interaction-harness/src .venv/bin/python -m interaction_harness --population-pack-path products/interaction-harness/output/generated-populations/provider-population.json --service-mode mock --output-dir products/interaction-harness/output/generated-population-run
```

Run a single audit with fixture-backed semantic interpretation:

```bash
PYTHONPATH=products/interaction-harness/src .venv/bin/python -m interaction_harness --semantic-mode fixture --service-mode mock
```

Run a single audit with provider-backed semantic interpretation:

```bash
PYTHONPATH=products/interaction-harness/src .venv/bin/python -m interaction_harness --semantic-mode provider --semantic-model gpt-5-mini --service-mode mock
```

Use the mock fixture explicitly:

```bash
PYTHONPATH=products/interaction-harness/src .venv/bin/python -m interaction_harness --service-mode mock
```

Run compare mode against two artifact-backed targets:

```bash
PYTHONPATH=products/interaction-harness/src .venv/bin/python -m interaction_harness --compare --baseline-artifact-dir products/interaction-harness/output/reference-artifacts-baseline --candidate-artifact-dir products/interaction-harness/output/reference-artifacts-candidate --rerun-count 3 --output-dir products/interaction-harness/output/regression-demo
```

Reuse one saved population pack across compare reruns:

```bash
PYTHONPATH=products/interaction-harness/src .venv/bin/python -m interaction_harness --compare --baseline-artifact-dir products/interaction-harness/output/reference-artifacts-baseline --candidate-artifact-dir products/interaction-harness/output/reference-artifacts-candidate --population-pack-path products/interaction-harness/output/generated-populations/provider-population.json --rerun-count 3 --output-dir products/interaction-harness/output/regression-demo
```

Add advisory semantic interpretation to compare mode:

```bash
PYTHONPATH=products/interaction-harness/src .venv/bin/python -m interaction_harness --compare --baseline-artifact-dir products/interaction-harness/output/reference-artifacts-baseline --candidate-artifact-dir products/interaction-harness/output/reference-artifacts-candidate --semantic-mode fixture --rerun-count 3 --output-dir products/interaction-harness/output/regression-demo
```

Use custom labels in compare mode:

```bash
PYTHONPATH=products/interaction-harness/src .venv/bin/python -m interaction_harness --compare --baseline-artifact-dir products/interaction-harness/output/reference-artifacts-baseline --candidate-artifact-dir products/interaction-harness/output/reference-artifacts-candidate --baseline-label current-prod --candidate-label next-build
```

See all CLI options:

```bash
PYTHONPATH=products/interaction-harness/src .venv/bin/python -m interaction_harness --help
```

## How To Read The Output

Single-run audit bundles include:

- `report.md`: human-readable audit with executive summary, launch risks, cohort summary, discovered slices, and compact traces to inspect
- `results.json`: machine-readable run result plus a top-level summary block and slice summaries
- `traces.jsonl`: full trace bundle for deeper inspection
- `cohort_summary_chart.svg`: simple cohort utility chart
- scenario-pack-backed runs also carry scenario-pack metadata in the run result
- population-pack-backed runs also carry population-pack metadata in the run result
- add `--include-slice-membership` when you want full slice membership in `results.json`
- semantic mode adds a structured `semantic_interpretation` block and a `Semantic Advisory` report section

Regression compare bundles include:

- `regression_report.md`: human-readable baseline-vs-candidate summary with deterministic slice changes
- `regression_summary.json`: machine-readable regression diff plus top-level
  summary block, decision, reasons, checks, and slice diffs
- `regression_traces.json`: notable trace-level changes
- nested `baseline/` and `candidate/` rerun directories with per-seed audit bundles
- semantic mode adds a structured `semantic_interpretation` block and a `Semantic Advisory` report section

## Current Limits

- built-in synthetic users are still hand-authored as the baseline path
- generated population packs are recommender-specific and still project into deterministic `AgentSeed` values
- scenario coverage is still narrow
- generated scenario packs are real now, but only the recommender projection is
  implemented today
- regression policy is real now, but still early and not the final long-term
  gating model
- semantic interpretation is advisory only and does not influence gating
- no LLM judge or LLM agents are in the critical path
- external service integrations are still early

## Development

Run checks from the repository root:

```bash
PYTHONPATH=products/interaction-harness/src .venv/bin/ruff check products/interaction-harness
PYTHONPATH=products/interaction-harness/src .venv/bin/pytest products/interaction-harness/tests -q
```

## Planning

The active roadmap for this package lives under
[plans/interaction-harness-v0](../plans/interaction-harness-v0/README.md).

The current architectural assumptions and subsystem boundaries are summarized in
[plans/interaction-harness-v0/architecture-assumptions.md](../plans/interaction-harness-v0/architecture-assumptions.md).

A short component review and the open product decisions are captured in
[plans/interaction-harness-v0/architecture-review.md](../plans/interaction-harness-v0/architecture-review.md) and
[plans/interaction-harness-v0/decision-questions.md](../plans/interaction-harness-v0/decision-questions.md).
