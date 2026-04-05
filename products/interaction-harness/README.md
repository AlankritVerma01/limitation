# Interaction Harness

This package is the new product-facing area for the next stage of the project.

It is intentionally separate from the existing
`studies/01-recommender-offline-eval` study package.

## What This Package Is

The package now contains Chunk 7: a stronger deterministic audit layer, a first
reproducibility and regression harness, and a more polished product-facing
artifact surface on top of the real reference recommender service.

It proves:

- a service-shaped adapter boundary through a real local reference service
- two real scenarios: returning user and sparse-history home feed
- seeded archetypes reused from the public recommender study
- an artifact-backed backend built from local MovieLens 100K data
- richer deterministic trace scoring, cohort summaries, and failure surfacing
- rerun summaries and baseline-vs-candidate regression artifacts
- clearer markdown and JSON summaries, run metadata, and a simple chart artifact bundle

## How It Differs From The Existing Study

The current study package is a public proof centered on offline recommender
evaluation and behavioral diagnostics.

This new package is the foundation for a broader interaction-testing product:

- system adapter
- seeded agents
- rollout engine
- judge
- analyzer
- reproducibility harness
- report

## Chunk 7 Status

Implemented here:

- offline reference artifact build flow
- artifact-backed reference recommender service
- local mock recommender fixture for narrow tests only
- HTTP recommender adapter
- returning-user and sparse-history scenarios
- parameter-driven seeded archetypes
- normalized runtime item signals
- richer recommender-aware runtime policy
- step-level decision explanations in traces
- stronger deterministic judge and cohort analyzer
- explicit failure modes, risk flags, and representative success/failure traces
- report-only regression diffs across two artifact-backed systems
- deterministic rerun summaries with simple variance reporting
- polished reports with executive summaries and compact trace inspection sections
- clearer run IDs, generated-at metadata, and more consistent output bundles
- report, results, traces, and chart outputs

The product remains independent from the existing study package. Ideas are
reused intentionally, but the new package does not import the old
`recommender_offline_eval` code.

## Run The Recommender Audit

From the repository root:

```bash
PYTHONPATH=products/interaction-harness/src .venv/bin/python -m interaction_harness
```

Run one scenario only:

```bash
PYTHONPATH=products/interaction-harness/src .venv/bin/python -m interaction_harness --scenario returning-user-home-feed --seed 7 --service-artifact-dir products/interaction-harness/output/reference-artifacts --output-dir products/interaction-harness/output/demo
```

Use the mock fixture explicitly:

```bash
PYTHONPATH=products/interaction-harness/src .venv/bin/python -m interaction_harness --service-mode mock
```

Run the new regression compare mode:

```bash
PYTHONPATH=products/interaction-harness/src .venv/bin/python -m interaction_harness --compare --baseline-artifact-dir products/interaction-harness/output/reference-artifacts-baseline --candidate-artifact-dir products/interaction-harness/output/reference-artifacts-candidate --rerun-count 3 --output-dir products/interaction-harness/output/regression-demo
```

Use custom labels in compare mode:

```bash
PYTHONPATH=products/interaction-harness/src .venv/bin/python -m interaction_harness --compare --baseline-artifact-dir products/interaction-harness/output/reference-artifacts-baseline --candidate-artifact-dir products/interaction-harness/output/reference-artifacts-candidate --baseline-label current-prod --candidate-label next-build
```

## How To Read The Output

Single-run audit bundles include:

- `report.md`: human-readable audit with executive summary, launch risks, cohort summary, and compact traces to inspect
- `results.json`: machine-readable run result plus a top-level summary block
- `traces.jsonl`: full trace bundle for deeper inspection
- `cohort_summary_chart.svg`: simple cohort utility chart

Regression compare bundles include:

- `regression_report.md`: human-readable baseline-vs-candidate summary
- `regression_summary.json`: machine-readable regression diff plus top-level summary block
- `regression_traces.json`: notable trace-level changes
- nested `baseline/` and `candidate/` rerun directories with per-seed audit bundles

## What Is Real Today

- a real local reference recommender service
- seeded synthetic agents with multi-step state transitions
- deterministic trace scoring and cohort analysis
- report-only regression comparisons across reruns

## What Is Still Simplified

- synthetic users are still hand-authored and parameterized
- scenario coverage is still narrow
- regression is still informational and not a hard gate
- no LLM judge or LLM agents are in the critical path
