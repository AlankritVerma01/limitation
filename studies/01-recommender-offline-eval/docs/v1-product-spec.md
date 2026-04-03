# V1 Product Spec

## Name

Behavioral QA for recommender systems

Working description:
trajectory-aware, segment-aware recommender evaluation

## One-Line Definition

A public, reproducible test harness that compares a baseline recommender against a candidate recommender and surfaces tradeoffs that aggregate offline metrics miss.

## Product Goal

Help recommender, ranking, and ML engineers decide whether to trust a new recommender before launch.

The tool should not only answer:

- Which model wins on Recall@10 or NDCG@10?

It should also answer:

- Which users get better results?
- Which users get worse results?
- Does the candidate become more repetitive?
- Does it collapse toward head items?
- Do important user segments regress before launch?

## Primary User

Recommender, ranking, and ML engineers who already have:

- offline benchmarks
- a baseline model
- a candidate model
- standard ranking metrics

## Core Job To Be Done

Catch hidden pre-launch regressions and hidden wins that aggregate offline metrics compress away.

## V1 Scope

### In Scope

- recommendation systems only
- MovieLens as the first public dataset
- comparison of exactly 2 models: baseline vs candidate
- fixed evaluation config and seed
- fixed user bucket definitions
- standard offline ranking metrics
- behavioral diagnostics
- short trajectory simulation
- reproducible public report artifacts

### Out of Scope

- chat systems
- search systems
- agents
- robots
- hosted SaaS
- custom UI platform
- fully general non-deterministic testing framework

## Inputs

Each run takes:

- one dataset
- one baseline recommender
- one candidate recommender
- fixed bucket definitions
- fixed evaluation config
- fixed random seed

## Evaluation Workflow

1. Run both recommenders on the same dataset and evaluation split.
2. Compute standard offline ranking metrics.
3. Slice results into fixed user buckets.
4. Compute behavioral diagnostics for both models.
5. Generate short example trajectories that make the tradeoffs legible.
6. Produce one comparison report with a clear launch-oriented conclusion.

## Evaluation Layers

### Layer 1: Standard Offline Ranking

- Recall@10
- NDCG@10

### Layer 2: Behavioral Diagnostics

- per-bucket utility
- novelty
- repetition
- catalog concentration
- short trajectory traces

## Fixed User Buckets

V1 keeps four bucket definitions fixed so the story is clean and reproducible:

1. Conservative mainstream
2. Explorer / novelty-seeking
3. Niche-interest
4. Low-patience

## Outputs

Each run should produce:

- a markdown report
- a JSON metrics artifact
- a comparison chart
- a notebook or scripted run path that reproduces the result

The report should answer:

1. who wins on standard offline metrics
2. who wins per user bucket
3. whether the candidate is more novel, more repetitive, or more concentrated
4. where aggregate metrics hide important tradeoffs
5. what short example traces look like

## Good V1 Criteria

V1 is successful if:

- a user can compare 2 recommenders in one clean run
- the report clearly separates aggregate, bucket-level, and behavioral results
- the run produces at least one concrete hidden-tradeoff insight
- the run is reproducible
- the output is easy to screenshot, share, and cite in a README or blog post
- the repo looks like a small real tool, not a messy experiment

## Example Conclusion

The tool should be able to support a conclusion like:

> Offline metrics favor Model A, but Model B improves experience for explorers and niche users while reducing catalog concentration.

## Positioning

### What We Say Publicly

- Behavioral QA for recommender systems
- trajectory-aware, segment-aware recommender evaluation

### What We Do Not Say Yet

- universal AI eval stack
- full non-deterministic testing company
- robot testing platform

## Roadmap After V1

This is the first wedge into broader testing for non-deterministic systems:

- v1: recommenders
- v2: search and ranking
- v3: chat and assistant systems
- later: broader interactive AI systems

The v1 bar is narrower:

- sharp
- useful
- credible
- public
