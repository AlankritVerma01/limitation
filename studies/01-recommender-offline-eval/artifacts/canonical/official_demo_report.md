# Official MovieLens Demo

## Run summary

This canonical Phase 1 run evaluates MovieLens 100K with Model A (Popularity baseline) and Model B (Genre-profile recommender with popularity prior) across the fixed four user buckets to show where aggregate offline metrics hide segment-level and behavioral tradeoffs.

## Standard offline metrics

| Model | Recall@10 | NDCG@10 |
| --- | --- | --- |
| Model A | 0.088 | 0.057 |
| Model B | 0.058 | 0.036 |

- **Recall@10**: Mean recall on held-out positive items per eligible user.
- **NDCG@10**: Mean NDCG on held-out positive items per eligible user.

## Bucket-level utility

Bucket glossary:

- **Conservative mainstream**: Prefers familiar, high-exposure items and tolerates safe recommendations.
- **Explorer / novelty-seeking**: Values discovery and variety, and rewards recommendation sets that surface less familiar items.
- **Niche-interest**: Has narrower taste clusters and benefits when the model can match specialized catalog pockets.
- **Low-patience**: Needs good recommendations quickly and loses utility faster when sequences feel stale.

| Bucket | Model A | Model B | Delta (B-A) |
| --- | --- | --- | --- |
| Conservative mainstream | 0.519 | 0.532 | 0.012 |
| Explorer / novelty-seeking | 0.339 | 0.523 | 0.184 |
| Niche-interest | 0.443 | 0.722 | 0.279 |
| Low-patience | 0.321 | 0.364 | 0.043 |

- **Bucket utility**: Mean simulated per-step utility for a fixed bucket over the short canonical session.

## Behavioral diagnostics

| Model | Novelty | Repetition | Catalog concentration |
| --- | --- | --- | --- |
| Model A | 0.395 | 0.279 | 1.000 |
| Model B | 0.678 | 0.664 | 0.717 |

See `bucket_utility_comparison.svg` for the canonical bucket utility comparison chart.

- **Novelty**: Mean of 1 - popularity_norm over recommended or consumed items.
- **Repetition**: Mean similarity to the user's recent consumed items.
- **Catalog concentration**: Share of recommendations that fall in the top popularity decile.

## Key takeaways

- Aggregate offline metrics favor Model A, which posts higher Recall@10 (0.088 vs 0.058) and NDCG@10 (0.057 vs 0.036).
- Model B's strongest segment win is Niche-interest, where bucket utility improves by 0.279.
- Behaviorally, Model B increases novelty (0.678 vs 0.395), reduces catalog concentration (0.717 vs 1.000), and has higher repetition (0.664 vs 0.279).

## Short traces

### Explorer / novelty-seeking (user 366, delta 0.427)

**Model A — Popularity baseline**

| Step | Title | Utility | Affinity | Popularity | Novelty | Repetition penalty |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | Raiders of the Lost Ark (1981) | 0.177 | 0.156 | 0.694 | 0.306 | 0.000 |
| 2 | Fargo (1996) | 0.130 | 0.236 | 0.814 | 0.186 | 0.204 |
| 3 | Toy Story (1995) | 0.170 | 0.088 | 0.629 | 0.371 | 0.000 |
| 4 | Return of the Jedi (1983) | 0.162 | 0.167 | 0.751 | 0.249 | 0.000 |

**Model B — Genre-profile recommender with popularity prior**

| Step | Title | Utility | Affinity | Popularity | Novelty | Repetition penalty |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | Prophecy, The (1995) | 0.632 | 0.932 | 0.027 | 0.973 | 0.642 |
| 2 | Cat People (1982) | 0.591 | 0.932 | 0.022 | 0.978 | 0.854 |
| 3 | Wes Craven's New Nightmare (1994) | 0.563 | 0.932 | 0.018 | 0.982 | 1.000 |
| 4 | Relic, The (1997) | 0.564 | 0.932 | 0.016 | 0.984 | 1.000 |

### Niche-interest (user 366, delta 0.736)

**Model A — Popularity baseline**

| Step | Title | Utility | Affinity | Popularity | Novelty | Repetition penalty |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | Fargo (1996) | 0.121 | 0.236 | 0.814 | 0.186 | 0.371 |
| 2 | Godfather, The (1972) | 0.120 | 0.185 | 0.700 | 0.300 | 0.537 |
| 3 | Raiders of the Lost Ark (1981) | 0.101 | 0.156 | 0.694 | 0.306 | 0.204 |
| 4 | Contact (1997) | 0.097 | 0.141 | 0.671 | 0.329 | 0.204 |

**Model B — Genre-profile recommender with popularity prior**

| Step | Title | Utility | Affinity | Popularity | Novelty | Repetition penalty |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | Prophecy, The (1995) | 0.844 | 0.932 | 0.027 | 0.973 | 0.642 |
| 2 | Cat People (1982) | 0.845 | 0.932 | 0.022 | 0.978 | 0.854 |
| 3 | Wes Craven's New Nightmare (1994) | 0.847 | 0.932 | 0.018 | 0.982 | 1.000 |
| 4 | Relic, The (1997) | 0.847 | 0.932 | 0.016 | 0.984 | 1.000 |

### Low-patience (user 208, delta 0.228)

**Model A — Popularity baseline**

| Step | Title | Utility | Affinity | Popularity | Novelty | Repetition penalty |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | Star Wars (1977) | 0.169 | 0.273 | 1.000 | 0.000 | 0.316 |
| 2 | Fargo (1996) | 0.143 | 0.205 | 0.814 | 0.186 | 0.204 |
| 3 | Return of the Jedi (1983) | 0.089 | 0.273 | 0.751 | 0.249 | 0.500 |
| 4 | Toy Story (1995) | 0.357 | 0.490 | 0.629 | 0.371 | 0.000 |

**Model B — Genre-profile recommender with popularity prior**

| Step | Title | Utility | Affinity | Popularity | Novelty | Repetition penalty |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | Monty Python and the Holy Grail (1974) | 0.558 | 0.849 | 0.480 | 0.520 | 0.000 |
| 2 | Full Monty, The (1997) | 0.402 | 0.849 | 0.422 | 0.578 | 0.500 |
| 3 | American President, The (1995) | 0.383 | 0.894 | 0.198 | 0.802 | 0.577 |
| 4 | Truth About Cats & Dogs, The (1996) | 0.327 | 0.878 | 0.286 | 0.714 | 0.762 |

## Reproducibility note

- Fixed dataset: MovieLens 100K
- Fixed buckets: Conservative mainstream, Explorer / novelty-seeking, Niche-interest, Low-patience
- Fixed config: top_k=10, session_steps=4, slate_size=10, choice_pool=5, popularity_weight=0.25, diversity_weight=0.35, shortlist_size=75
- Fixed split: Chronological split with each eligible user's last 2 positive interactions held out.
- Fixed seed: 0
