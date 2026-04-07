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

## Domain Plug-In Direction

The package now uses an in-repo domain plug-in shape:

- the shared foundation owns rollout, traces, artifacts, semantic layering, and regression lifecycle
- each domain module owns its own runtime inputs, adapter construction, policy, judge, analyzer, and domain-level regression semantics
- the recommender wedge is the first full implementation of that contract and now lives primarily in `src/interaction_harness/domains/recommender/`
- a small stub domain exists only as test-only architecture infrastructure to prove that new systems can plug in without shared-core surgery

The CLI is still recommender-first on purpose, but internally new systems are meant to land as domain modules rather than as branches spread through generic code.

## Current Capabilities

- a real local reference recommender service
- an HTTP recommender adapter
- a local mock service kept only for narrow tests
- four recommender scenarios:
  - returning-user home feed
  - sparse-history home feed
  - taste-elicitation home feed
  - re-engagement home feed
- built-in four-seed deterministic baseline population
- saved recommender population packs with explicit generated swarms
- explicit agent state and decision explanations
- richer scenario- and persona-aware recommender runtime shaping
- deterministic judging, cohort analysis, and failure surfacing
- additive recommender behavioral signals such as first-impression strength and
  abandonment pressure
- deterministic discovered failure slices from trace evidence
- opt-in advisory semantic interpretation for traces and regression changes
- rerun-based regression comparisons with deterministic `pass` / `warn` /
  `fail` decisions
- structured AI-authored scenario packs with saved portable contracts
- clearer external-target metadata and operator-facing target identity capture
- markdown, JSON, trace, and chart artifacts

## Supported User Path

Today the supported product path is:

- CLI-first recommender audits
- local reference recommender service for repeatable local runs
- external recommender base URLs for real-system integration
- artifact bundles as the main user-facing output

The mock recommender service still exists, but only as a narrow test/debug
fixture. It is not the primary user path.

## AI Boundary

The harness uses AI in additive layers, not in the critical runtime loop.

AI is used for:

- scenario-pack generation
- population-pack generation
- advisory semantic interpretation

The deterministic core still owns:

- rollout execution
- agent-policy decisions
- judging and analysis
- slice discovery
- regression decisioning

Recommended user stance:

- use provider-backed generation and semantic interpretation when you want a
  richer authoring and explanation workflow
- use fixture-backed generation and interpretation for tests, CI, offline
  demos, and no-key environments
- rely on the deterministic runtime and regression outputs as the source of truth

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
- `src/interaction_harness/config.py`
  - shared explicit-input run-config builder plus a small recommender entrypoint
- `src/interaction_harness/scenario_generation.py`
  - scenario-pack generation, validation, and storage
- `src/interaction_harness/population_generation.py`
  - population-pack generation, selection, and storage
- `src/interaction_harness/domains/recommender/`
  - the real cross-cutting recommender domain package:
    inputs, scenarios, policy, judge, analyzer, metrics, slices, local
    reference/mock services, catalog/reference-artifact helpers, and reporting
    hooks
- `src/interaction_harness/adapters/`
  - shared adapter interfaces only
- `src/interaction_harness/agents/`
  - shared agent interfaces only
- `src/interaction_harness/rollout/`
  - session execution loop
- `src/interaction_harness/judges/`
  - shared judge interfaces only
- `src/interaction_harness/analysis/`
  - shared analysis interfaces plus shared slice-discovery infrastructure
- `src/interaction_harness/reporting/`
  - shared markdown, JSON, regression, and chart writers driven by
    domain-supplied reporting hooks
- `src/interaction_harness/domain_registry.py`
  - internal adapter-domain registry
- `src/interaction_harness/domains/`
  - in-repo domain plug-ins plus the shared domain runner shell

The older recommender compatibility modules have been removed. Recommender code
should now be imported directly from `src/interaction_harness/domains/recommender/`.

## Run The Recommender Audit

From the repository root:

```bash
PYTHONPATH=products/interaction-harness/src .venv/bin/python -m interaction_harness
```

Run one scenario only:

```bash
PYTHONPATH=products/interaction-harness/src .venv/bin/python -m interaction_harness --scenario returning-user-home-feed --seed 7 --service-artifact-dir products/interaction-harness/output/reference-artifacts --output-dir products/interaction-harness/output/demo
```

Generate a saved scenario pack from a brief with the deterministic fixture path
for CI, tests, or offline demos:

```bash
PYTHONPATH=products/interaction-harness/src .venv/bin/python -m interaction_harness --generate-scenarios --generation-mode fixture --scenario-brief "test recommendation quality for sparse-history users who still want novelty" --output-dir products/interaction-harness/output/generated-scenarios
```

Generate a saved scenario pack through the provider-backed path recommended for
real authored workflows:

```bash
PYTHONPATH=products/interaction-harness/src .venv/bin/python -m interaction_harness --generate-scenarios --generation-mode provider --scenario-brief "test trust and exploration balance for returning users" --scenario-pack-path products/interaction-harness/output/generated-scenarios/provider-pack.json
```

Provider mode will auto-read a root `.env` when present. Useful environment
variables:

- `OPENAI_API_KEY`
- `OPENAI_BASE_URL`
- `OPENAI_TIMEOUT_SECONDS`
- `OPENAI_RETRY_COUNT`

Reuse a saved scenario pack in a normal audit run against the supported local
reference service:

```bash
PYTHONPATH=products/interaction-harness/src .venv/bin/python -m interaction_harness --scenario-pack-path products/interaction-harness/output/generated-scenarios/provider-pack.json --service-artifact-dir products/interaction-harness/output/reference-artifacts --output-dir products/interaction-harness/output/generated-pack-run
```

Generate a saved recommender population pack with the deterministic fixture path
for CI, tests, or offline demos:

```bash
PYTHONPATH=products/interaction-harness/src .venv/bin/python -m interaction_harness --generate-population --population-generation-mode fixture --population-brief "test a broad swarm of novelty-seeking and low-patience viewers" --population-size 12 --output-dir products/interaction-harness/output/generated-populations
```

Generate a saved recommender population pack through the provider-backed path
recommended for real authored workflows:

```bash
PYTHONPATH=products/interaction-harness/src .venv/bin/python -m interaction_harness --generate-population --population-generation-mode provider --population-brief "test a broad swarm of risk-sensitive and exploration-seeking viewers" --population-pack-path products/interaction-harness/output/generated-populations/provider-population.json
```

If `--population-size` is omitted, provider mode may suggest the final explicit
swarm size. Fixture mode falls back to the default size of `12`.

Reuse a saved population pack in a normal audit run against the supported local
reference service:

```bash
PYTHONPATH=products/interaction-harness/src .venv/bin/python -m interaction_harness --population-pack-path products/interaction-harness/output/generated-populations/provider-population.json --service-artifact-dir products/interaction-harness/output/reference-artifacts --output-dir products/interaction-harness/output/generated-population-run
```

Run a single audit with fixture-backed semantic interpretation for offline demos
or tests:

```bash
PYTHONPATH=products/interaction-harness/src .venv/bin/python -m interaction_harness --semantic-mode fixture --service-artifact-dir products/interaction-harness/output/reference-artifacts
```

Run a single audit with provider-backed semantic interpretation for a richer
user-facing explanation workflow:

```bash
PYTHONPATH=products/interaction-harness/src .venv/bin/python -m interaction_harness --semantic-mode provider --semantic-model gpt-5-mini --service-artifact-dir products/interaction-harness/output/reference-artifacts
```

Use the mock fixture explicitly only for narrow testing/debugging:

```bash
PYTHONPATH=products/interaction-harness/src .venv/bin/python -m interaction_harness --service-mode mock
```

Run compare mode against two artifact-backed targets:

```bash
PYTHONPATH=products/interaction-harness/src .venv/bin/python -m interaction_harness --compare --baseline-artifact-dir products/interaction-harness/output/reference-artifacts-baseline --candidate-artifact-dir products/interaction-harness/output/reference-artifacts-candidate --rerun-count 3 --output-dir products/interaction-harness/output/regression-demo
```

Run compare mode against an artifact-backed baseline and an external URL
candidate:

```bash
PYTHONPATH=products/interaction-harness/src .venv/bin/python -m interaction_harness --compare --baseline-artifact-dir products/interaction-harness/output/reference-artifacts-baseline --candidate-base-url http://localhost:8010 --rerun-count 3 --output-dir products/interaction-harness/output/regression-demo
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
- generated population packs are recommender-specific and still project into deterministic `AgentSeed` values, even though richer persona metadata now shapes runtime behavior on top
- scenario coverage is broader now, but it is still focused on short recommender home-feed style sessions rather than a wide set of product environments
- generated scenario packs are real now, but only the recommender projection is
  implemented today
- regression policy is real now, but still early and not the final long-term
  gating model
- semantic interpretation is advisory only and does not influence gating
- no LLM judge or LLM agents are in the critical path
- external service integrations are clearer and more trustworthy now, but still early
- the internal portability seam is now cleaner, but the recommender wedge is
  still the only fully implemented domain
- the shared config builder is now explicit-input-first, while recommender
  defaults remain available through compatibility wrappers

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

The current in-repo domain plug-in shape is documented in
[plans/interaction-harness-v0/domain-plugin-architecture.md](../plans/interaction-harness-v0/domain-plugin-architecture.md).

The foundation-vs-domain ownership rule for future extensions is documented in
[plans/interaction-harness-v0/foundation-vs-domain-boundaries.md](../plans/interaction-harness-v0/foundation-vs-domain-boundaries.md).
