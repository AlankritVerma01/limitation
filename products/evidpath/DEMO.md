# Evidpath Demo

This demo is the easiest way to show what Evidpath does without needing your
own recommender service first.

It uses the built-in reference target so the flow stays stable and repeatable.
The real customer path uses the same CLI flow against an external target URL.

## What This Demo Is For

Use this demo when you want to:

- show the product quickly
- prove the audit and compare flow end to end
- get a local onboarding path before your own endpoint is ready

If you already have a recommender endpoint, the better starting point is the
external-target flow in [README.md](./README.md) and the example services under
[`examples/`](./examples/).

## 30-Second Version

Evidpath helps you answer a simple question before launch:

"If we point this at a recommender, what happened, who struggled, and is the
candidate better or worse than the baseline?"

The quickest proof points in this repo are:

- single audit report: [output/demo-single/report.md](./output/demo-single/report.md)
- compare report: [output/demo-regression-stable/regression_report.md](./output/demo-regression-stable/regression_report.md)

## Before You Start

From the repository root:

```bash
uv sync
```

That gives you both:

- `uv run python -m evidpath`
- `evidpath`

The examples below use `uv run python -m evidpath` for clarity.

## 5-Minute Walkthrough

### 1. Run one audit

```bash
uv run python -m evidpath audit --domain recommender --seed 7 --scenario returning-user-home-feed --reference-artifact-dir products/evidpath/output/reference-artifacts-demo --output-dir products/evidpath/output/demo-single-live
```

### 2. Open the output

Open:

- `products/evidpath/output/demo-single-live/report.md`
- `products/evidpath/output/demo-single-live/results.json`

When you talk through the result, keep it simple:

- this is the readable summary
- this is the structured output
- the report shows where to inspect next

### 3. Inspect one trace

Use the report to open one trace where the user skips, loses trust, or gives
up. The point is to show that the output is concrete, not just a blended score.

### 4. Run compare mode

```bash
uv run python -m evidpath compare --domain recommender --baseline-artifact-dir products/evidpath/output/reference-artifacts-demo --candidate-artifact-dir products/evidpath/output/reference-artifacts-demo --baseline-label current-prod --candidate-label current-prod-copy --rerun-count 2 --output-dir products/evidpath/output/demo-regression-live
```

Then open:

- `products/evidpath/output/demo-regression-live/regression_report.md`
- `products/evidpath/output/demo-regression-live/regression_summary.json`

This is the release-decision story: compare two versions, summarize the change,
and save the evidence.

## What To Say During The Demo

Keep the message plain:

- we are testing a recommender before launch
- we are not relying on one aggregate metric
- we can read the report, inspect traces, and compare versions
- we can keep the same workflow when we switch to a real external endpoint

## After The Demo

When someone asks, "How would this work with our real service?", go here next:

1. [EXTERNAL_TARGET_CONTRACT.md](./EXTERNAL_TARGET_CONTRACT.md)
2. [examples/recommender_http_service/README.md](./examples/recommender_http_service/README.md)
3. [examples/hf_recommender_service/README.md](./examples/hf_recommender_service/README.md)

The usual next step is:

1. start an external-style example service
2. run `check-target`
3. run `audit --target-url ...`
4. run `compare --baseline-url ... --candidate-url ...`

## Notes

- `run_plan.json` captures the pre-run plan for workflows that support planning
- `run_manifest.json` captures what actually ran
- semantic advisory files are optional explanation sidecars, not the source of truth
- the mock target is only for narrow internal tests, not for demos or real usage
