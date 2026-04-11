# Interaction Harness Demo

This is the canonical v1 demo for recommender-system buyers.

Important framing:

- this demo uses the product-owned reference target
- that keeps the walkthrough stable, local, and reproducible
- the real customer path uses the same CLI flow against an external target URL
- the repo now also includes a customer-style external service example for that path
- `check-target` is the fast preflight step when a team brings an endpoint
- `run_plan.json` captures the pre-run plan for `run-swarm` and `compare`
- `run_manifest.json` captures the realized execution after the run finishes

## 30-Second Version

Interaction Harness audits a recommender before launch.

It runs deterministic synthetic users through saved scenarios, shows which
cohorts fail, explains why they fail with trace evidence, and compares a
candidate build against a baseline with reproducible artifacts.

The fastest proof points in this repo are:

- [single-run audit report](./output/demo-single/report.md)
- [regression report](./output/demo-regression-stable/regression_report.md)

## 5-Minute Walkthrough

### 1. Start with the business problem

“We are about to ship a recommender change. Aggregate metrics are not enough.
We need to know which users get hurt, why they get hurt, and whether the
candidate is safe to ship.”

### 2. Run one audit

```bash
.venv/bin/python -m interaction_harness audit --domain recommender --seed 7 --scenario returning-user-home-feed --reference-artifact-dir products/interaction-harness/output/reference-artifacts-demo --output-dir products/interaction-harness/output/demo-single-live
```

Open `products/interaction-harness/output/demo-single-live/report.md`.

Why this target is used:

- it is our stable local stand-in for demos and onboarding
- it exercises the same audit/report flow the product uses for real targets
- it is not meant to replace the real customer integration path

What to say:

- “The audit does not just emit one score. It surfaces the highest-risk cohorts.”
- “It tells us the main concern, the strongest cohort, and where to inspect next.”
- “This is release-safety evidence, not just a dashboard.”

### 3. Open one failure trace

Use the report to zoom into a failure trace where the user skips, loses trust,
and abandons.

What to say:

- “This is why users are not clicking.”
- “We can see the session degrade step by step instead of guessing from a KPI.”
- “The trace is deterministic and reproducible for the same seed and scenario.”

### 4. Contrast with a healthy cohort

Use the strongest cohort in the same report.

What to say:

- “The system is not claiming everything is broken.”
- “It shows who is healthy and who is underserved.”
- “That makes the output useful for launch decisions and prioritization.”

### 5. Show compare mode

```bash
.venv/bin/python -m interaction_harness compare --domain recommender --baseline-artifact-dir products/interaction-harness/output/reference-artifacts-demo --candidate-artifact-dir products/interaction-harness/output/reference-artifacts-demo --baseline-label current-prod --candidate-label current-prod-copy --rerun-count 2 --output-dir products/interaction-harness/output/demo-regression-live
```

Open `products/interaction-harness/output/demo-regression-live/regression_report.md`.

What to say:

- “This is the release workflow.”
- “We can rerun a baseline and a candidate, summarize deltas, and turn the result into a ship decision.”
- “In this stable example, the system shows no material change. In a real launch review, this is where regressions surface.”

### 6. Mention saved coverage

Close by pointing out that saved scenario packs and saved population packs let
teams reuse coverage instead of re-authoring tests every time.

What to say:

- “We can keep the deterministic core and expand coverage over time.”
- “AI is part of the product here: it helps author richer scenarios, broader populations, and more realistic behavior plans.”
- “The deterministic trace and regression layer still decides what ships.”
- “In production, the same flow points at the customer recommender endpoint rather than our reference target.”

## Demo Takeaway

The buyer takeaway should be:

“This helps us prevent bad recommender launches with evidence we can actually
act on.”

## External Proof Path

When the conversation moves from “show me the product” to “show me how a team
would really use it,” use the example external service:

- [external target contract](./EXTERNAL_TARGET_CONTRACT.md)
- [example external service](./examples/recommender_http_service/README.md)
- [HF-backed external service](./examples/hf_recommender_service/README.md)

Recommended order:

1. start the example service
2. run `check-target --domain recommender --target-url ...`
3. run `audit --domain recommender --target-url ...`
4. run `compare --domain recommender --baseline-url ... --candidate-url ...`
5. inspect `run_plan.json` and `run_manifest.json` beside the report bundle

That path uses:

- `run-swarm --target-url ... --brief ...`
- `audit --target-url ...`
- `compare --baseline-url ... --candidate-url ...`

which is the real customer-style workflow in v1.
