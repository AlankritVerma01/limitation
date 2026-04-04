# Canonical Robustness Note

This note supplements the official MovieLens demo. It does not replace the frozen canonical run.

## What Is Frozen

- Dataset: MovieLens 100K
- Fixed buckets: Conservative mainstream, Explorer / novelty-seeking, Niche-interest, Low-patience
- Models: Model A = Popularity baseline, Model B = Genre-profile recommender with popularity prior
- Canonical seed: 0
- Canonical holdout positives per user: 2

## What Is Diagnostic

- Bucket utility, novelty, repetition, and catalog concentration are behavioral diagnostics meant to make tradeoffs legible.
- Short traces are compact examples of how the two recommenders behave over a four-step sequence.
- These diagnostics do not replace online evaluation or claim to predict long-term production outcomes exactly.

## What Was Checked For Stability

- Seeds checked: 0, 1, 2
- Modest split variation: hold out the last positive interaction instead of the last two

| Variant | Recall@10 A | Recall@10 B | NDCG@10 A | NDCG@10 B | Explorer delta | Niche delta | Model B concentration |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Canonical config (seed 0) | 0.088 | 0.058 | 0.057 | 0.036 | 0.184 | 0.279 | 0.717 |
| Canonical config (seed 1) | 0.088 | 0.058 | 0.057 | 0.036 | 0.184 | 0.279 | 0.717 |
| Canonical config (seed 2) | 0.088 | 0.058 | 0.057 | 0.036 | 0.184 | 0.279 | 0.717 |
| Hold out the last positive interaction | 0.095 | 0.057 | 0.050 | 0.030 | 0.185 | 0.280 | 0.714 |

## What Changed And What Did Not

- Seed 0, 1, and 2 produced identical results in this pipeline.
- A smaller holdout split shifted the magnitudes slightly, but the same directional conclusion held.
- Across every checked variant, aggregate offline metrics still favored Model A.
- Across every checked variant, Explorer and Niche-interest still favored Model B.
- Across every checked variant, Model B remained less concentrated than Model A.

## What Remains Out Of Scope

- The robustness pass does not claim external validity beyond MovieLens 100K.
- The bucket lenses remain simplified evaluation constructs rather than discovered user segments.
- The supporting checks do not substitute for live online experiments.
