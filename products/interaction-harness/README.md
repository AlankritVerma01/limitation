# Interaction Harness

This package is the active product track for the repository.

## What It Does

Interaction Harness is a deterministic interaction-testing tool.

V1 audits recommender systems by:

1. calling a system under test through a normalized adapter
2. running seeded synthetic users through short scenarios
3. recording the full session trace
4. judging the completed trace deterministically
5. summarizing cohort-level risks and representative traces
6. optionally comparing baseline vs candidate systems across reruns

The supported product domain in v1 is recommender evaluation.

## Why Teams Buy It

Teams buy Interaction Harness when they need more than offline ranking metrics
and more than manual QA before shipping recommender changes.

It helps teams:

- catch bad recommender launches before users feel them
- see which cohorts are underserved instead of relying on one blended metric
- explain non-clicking, abandonment, trust collapse, and repetition with trace evidence
- compare baseline vs candidate systems with reproducible artifacts
- expand coverage with generated scenarios and generated populations without letting AI decide ship gates

The buyer story in v1 is recommender release safety:

- product and recs leaders get a concrete launch-risk readout
- ML teams get deterministic evidence tied to trace behavior
- eval and platform teams get saved artifacts, reruns, and compare workflows they can operationalize

## What Problems It Solves

Interaction Harness is built for questions like:

- Which user cohorts are likely to bounce or stop trusting this recommender?
- Why are users not clicking even when aggregate metrics look acceptable?
- Did the candidate build materially regress against the current baseline?
- Are we testing only one narrow happy path, or do we have reusable scenario and population coverage?

## Why Not The Alternatives

Why not just offline metrics?

- Offline metrics compress too much. They rarely tell you which session shape breaks, which cohort gets hurt, or what behavior produced the failure.

Why not just manual QA?

- Manual QA does not scale to seeded populations, repeatable reruns, or regression-ready evidence bundles.

Why not just LLM evals?

- LLMs help with authoring and explanation here, but release decisions stay grounded in deterministic traces, judging, and regression policy.

Why not build it in-house?

- Teams can, but they still need synthetic populations, reproducible traces, explainable cohort risk surfacing, saved coverage artifacts, and repeatable compare workflows before the system becomes trustworthy.

## Demo Value

The strongest v1 story is simple:

1. run a recommender audit
2. surface the highest-risk cohorts
3. inspect one failure trace where users skip and abandon because trust collapses
4. contrast it with a healthy cohort so the result is specific, not alarmist
5. compare baseline vs candidate and turn the result into a ship/no-ship style decision workflow

The repository already includes stable demo artifacts you can open directly:

- single-run audit: [output/demo-single/report.md](./output/demo-single/report.md)
- compare flow: [output/demo-regression-stable/regression_report.md](./output/demo-regression-stable/regression_report.md)
- demo script: [DEMO.md](./DEMO.md)

## Architecture

The package is organized around:

- the shared foundation owns rollout, traces, artifacts, semantic layering, and regression lifecycle
- each domain module owns its own runtime inputs, adapter construction, policy, judge, analyzer, and domain-level regression semantics
- the recommender implementation lives in `src/interaction_harness/domains/recommender/`

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

The supported product path is:

- CLI-first recommender audits
- external recommender base URLs for real-system integration
- local reference recommender service for repeatable local runs, demos, CI, and onboarding
- artifact bundles as the main user-facing output

The mock recommender service exists only as a narrow test/debug fixture. It is
not the primary user path.

## Customer Integration Model

For real usage, the main path is an external target.

In v1, a customer typically gives the harness:

- a reachable recommender base URL
- any required auth or gateway details
- a service that can answer the harness request/response contract

The reference target is different.

It is a product-owned local stand-in used for:

- demos
- local development
- CI and smoke runs
- onboarding when a customer endpoint is not ready yet

So the mental model is:

- external target = the real customer path
- reference target = the product-owned demo and local baseline path

## Canonical Demo Flow

Install the package once from the repository root:

```bash
.venv/bin/python -m pip install -e products/interaction-harness
```

Run the buyer-facing single audit demo:

```bash
.venv/bin/python -m interaction_harness audit --domain recommender --seed 7 --scenario returning-user-home-feed --reference-artifact-dir products/interaction-harness/output/reference-artifacts-demo --output-dir products/interaction-harness/output/demo-single-live
```

Then open:

- `products/interaction-harness/output/demo-single-live/report.md`
- `products/interaction-harness/output/demo-single-live/results.json`

Run the compare demo:

```bash
.venv/bin/python -m interaction_harness compare --domain recommender --baseline-artifact-dir products/interaction-harness/output/reference-artifacts-demo --candidate-artifact-dir products/interaction-harness/output/reference-artifacts-demo --baseline-label current-prod --candidate-label current-prod-copy --rerun-count 2 --output-dir products/interaction-harness/output/demo-regression-live
```

Then open:

- `products/interaction-harness/output/demo-regression-live/regression_report.md`
- `products/interaction-harness/output/demo-regression-live/regression_summary.json`

Use generated scenario and population packs after the core story lands. They
are powerful coverage expanders, but they are not the headline in the first
buyer conversation.

This demo uses the reference target on purpose. It proves the product workflow
without requiring a customer-owned endpoint. In real usage, the same audit flow
is pointed at an external recommender URL.

## AI Boundary

The harness uses AI in additive layers, not in the critical runtime loop.

AI is used for:

- scenario-pack generation
- population-pack generation
- advisory semantic interpretation

The deterministic core owns:

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

## Relationship To The Study Package

The repository also contains `studies/01-recommender-offline-eval/`, which is a
separate proof package. Interaction Harness is the product package. Ideas are
reused, but the runtime does not import the `recommender_offline_eval`
code.

## Package Layout

- `src/interaction_harness/cli.py`
  - CLI entrypoint for task-shaped commands: `audit`, `compare`,
    `generate-scenarios`, `generate-population`, and `serve-reference`
- `src/interaction_harness/audit.py`
  - single-run orchestration
- `src/interaction_harness/regression.py`
  - reruns and baseline-vs-candidate orchestration
- `src/interaction_harness/config.py`
  - shared explicit-input run-config builder
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
  - in-repo domain modules plus the shared domain runner shell

## Run The Recommender Audit

From the repository root:

```bash
.venv/bin/python -m pip install -e products/interaction-harness
.venv/bin/python -m interaction_harness --help
```

Every runtime and generation command requires an explicit `--domain`.
Progress is shown live while commands run so users are not left staring at a
silent wait.

Run one scenario only:

```bash
.venv/bin/python -m interaction_harness audit --domain recommender --scenario returning-user-home-feed --seed 7 --reference-artifact-dir products/interaction-harness/output/reference-artifacts --output-dir products/interaction-harness/output/demo
```

Run the same audit shape against a real external target:

```bash
.venv/bin/python -m interaction_harness audit --domain recommender --scenario returning-user-home-feed --seed 7 --target-url http://localhost:8010 --output-dir products/interaction-harness/output/external-audit-demo
```

Generate a saved scenario pack from a brief with the deterministic fixture path
for CI, tests, or offline demos:

```bash
.venv/bin/python -m interaction_harness generate-scenarios --domain recommender --mode fixture --brief "test recommendation quality for sparse-history users who still want novelty" --output-dir products/interaction-harness/output/generated-scenarios
```

Generate a saved scenario pack through the provider-backed path recommended for
real authored workflows:

```bash
.venv/bin/python -m interaction_harness generate-scenarios --domain recommender --mode provider --brief "test trust and exploration balance for returning users" --scenario-pack-path products/interaction-harness/output/generated-scenarios/provider-pack.json
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
.venv/bin/python -m interaction_harness audit --domain recommender --scenario-pack-path products/interaction-harness/output/generated-scenarios/provider-pack.json --reference-artifact-dir products/interaction-harness/output/reference-artifacts --output-dir products/interaction-harness/output/generated-pack-run
```

Generate a saved recommender population pack with the deterministic fixture path
for CI, tests, or offline demos:

```bash
.venv/bin/python -m interaction_harness generate-population --domain recommender --mode fixture --brief "test a broad swarm of novelty-seeking and low-patience viewers" --population-size 12 --output-dir products/interaction-harness/output/generated-populations
```

Generate a saved recommender population pack through the provider-backed path
recommended for real authored workflows:

```bash
.venv/bin/python -m interaction_harness generate-population --domain recommender --mode provider --brief "test a broad swarm of risk-sensitive and exploration-seeking viewers" --population-pack-path products/interaction-harness/output/generated-populations/provider-population.json
```

If `--population-size` is omitted, provider mode may suggest the final explicit
swarm size. Fixture mode falls back to the default size of `12`.

Reuse a saved population pack in a normal audit run against the supported local
reference service:

```bash
.venv/bin/python -m interaction_harness audit --domain recommender --population-pack-path products/interaction-harness/output/generated-populations/provider-population.json --reference-artifact-dir products/interaction-harness/output/reference-artifacts --output-dir products/interaction-harness/output/generated-population-run
```

Run a single audit with fixture-backed semantic interpretation for offline demos
or tests:

```bash
.venv/bin/python -m interaction_harness audit --domain recommender --semantic-mode fixture --reference-artifact-dir products/interaction-harness/output/reference-artifacts
```

Run a single audit with provider-backed semantic interpretation for a richer
user-facing explanation workflow:

```bash
.venv/bin/python -m interaction_harness audit --domain recommender --semantic-mode provider --semantic-model gpt-5-mini --reference-artifact-dir products/interaction-harness/output/reference-artifacts
```

Use the mock fixture explicitly only for narrow testing/debugging:

```bash
.venv/bin/python -m interaction_harness audit --domain recommender --use-mock
```

Start the local reference recommender service explicitly when you want a stable
URL for repeated manual checks or external integration:

```bash
.venv/bin/python -m interaction_harness serve-reference --domain recommender --artifact-dir products/interaction-harness/output/reference-artifacts --host 127.0.0.1 --port 8020
```

Run compare mode against two artifact-backed targets:

```bash
.venv/bin/python -m interaction_harness compare --domain recommender --baseline-artifact-dir products/interaction-harness/output/reference-artifacts-baseline --candidate-artifact-dir products/interaction-harness/output/reference-artifacts-candidate --rerun-count 3 --output-dir products/interaction-harness/output/regression-demo
```

Run compare mode against an artifact-backed baseline and an external URL
candidate:

```bash
.venv/bin/python -m interaction_harness compare --domain recommender --baseline-artifact-dir products/interaction-harness/output/reference-artifacts-baseline --candidate-url http://localhost:8010 --rerun-count 3 --output-dir products/interaction-harness/output/regression-demo
```

Reuse one saved population pack across compare reruns:

```bash
.venv/bin/python -m interaction_harness compare --domain recommender --baseline-artifact-dir products/interaction-harness/output/reference-artifacts-baseline --candidate-artifact-dir products/interaction-harness/output/reference-artifacts-candidate --population-pack-path products/interaction-harness/output/generated-populations/provider-population.json --rerun-count 3 --output-dir products/interaction-harness/output/regression-demo
```

Add advisory semantic interpretation to compare mode:

```bash
.venv/bin/python -m interaction_harness compare --domain recommender --baseline-artifact-dir products/interaction-harness/output/reference-artifacts-baseline --candidate-artifact-dir products/interaction-harness/output/reference-artifacts-candidate --semantic-mode fixture --rerun-count 3 --output-dir products/interaction-harness/output/regression-demo
```

Use custom labels in compare mode:

```bash
.venv/bin/python -m interaction_harness compare --domain recommender --baseline-artifact-dir products/interaction-harness/output/reference-artifacts-baseline --candidate-artifact-dir products/interaction-harness/output/reference-artifacts-candidate --baseline-label current-prod --candidate-label next-build
```

See all CLI options:

```bash
.venv/bin/python -m interaction_harness --help
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

## Scope

- built-in synthetic users provide the default baseline path
- generated population packs project into deterministic `AgentSeed` values,
  with richer persona metadata shaping runtime behavior on top
- scenario coverage focuses on short recommender home-feed sessions
- generated scenario packs project into the recommender domain
- semantic interpretation is advisory and does not influence gating
- no LLM judge or LLM agents are in the critical path

## Development

Run checks from the repository root:

```bash
.venv/bin/ruff check products/interaction-harness
.venv/bin/pytest products/interaction-harness/tests -q
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
