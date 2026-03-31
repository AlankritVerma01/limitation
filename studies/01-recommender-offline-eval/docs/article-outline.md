**Updated Outline**

## 1. Introduction: The Testing Gap

**Section goal**  
Introduce the central mismatch: recommendation systems are evaluated with offline historical data, but they are interactive systems that influence future behavior.

**Key claims**  
- Offline evaluation is common and useful.
- It is easy to mistake it for a full test of recommender quality.
- Recommenders do not merely predict clicks or watches; they shape what users see next and what they do next.

**Example or intuition to include**  
- Open with a contrast: testing deterministic software versus evaluating a recommender.
- Use a simple intuition: if a system changes exposure, it also changes the behavior later logged as data.

**What not to include**  
- Do not open with startup vision, synthetic users, or agents.
- Do not broaden into “all AI systems.”
- Do not sound adversarial toward current industry practice.

---

## 2. What Offline Evaluation Is

**Section goal**  
Give a clean, fair definition of offline evaluation in recommender systems.

**Key claims**  
- Offline evaluation uses historical logged interactions rather than live traffic.
- Teams typically train on one slice of logged data and evaluate on held-out interactions.
- Common ranking metrics are useful proxies for relevance under historical conditions.

**Example or intuition to include**  
- Introduce the movie recommender here.
- Explain that we might ask whether a held-out movie a user later watched appears near the top of the ranked list.
- Briefly mention familiar metrics like Recall@K, NDCG, or hit rate, without going deep into formulas.

**What not to include**  
- Do not turn this into a metric tutorial.
- Do not overload the section with notation.
- Do not yet argue that offline evaluation is broken.

---

## 3. Where Offline Evaluation Breaks

This is the core analytical section and the center of the article. It should feel rigorous rather than rhetorical. The unifying idea is that logged data is policy-dependent, so historical replay is partial. This section can carry the conceptual burden that was previously split across “core mismatch” and “what is missing from a purely offline view.”

**Section goal**  
Show, in a technically grounded way, why offline evaluation is structurally incomplete for recommenders.

**Key claims**  
- Logged interactions are generated under an earlier exposure policy.
- A new recommender is often judged using outcomes produced by a different recommender.
- That makes offline metrics informative but not policy-invariant.
- The missing quantity is not just one-step accuracy, but trajectory-level quality under changed exposure.

**Example or intuition to include**  
- Use the movie recommender lightly across subsections.
- Keep returning to the same contrast: mainstream-heavy historical exposure produces richer evidence for safe recommendations than for niche or exploratory ones.

**What not to include**  
- Do not make the tone accusatory or emotional.
- Do not imply the entire recommender literature missed this.
- Do not turn the section into a full causal inference survey.

### 3.1 Exposure Bias

**Section goal**  
Establish that observed user feedback is conditional on what the system decided to show.

**Key claims**  
- Users can only interact with exposed items.
- Missing feedback frequently means “not shown,” not “not relevant.”
- Offline evaluation therefore inherits the visibility pattern of the old policy.

**Example or intuition to include**  
- A user may have liked a niche science-fiction film, but if it was never surfaced, the log contains no direct evidence of that relevance.
- In movie logs, popular catalog items usually have denser interaction evidence simply because they were shown more often.

**What not to include**  
- Do not expand into general missing-data taxonomy.
- Do not switch to search or ads examples.

**Rigor note**  
- A compact formal sentence can help here: under a logging policy `pi_0`, observed reward is only available for exposed items, so evaluation support is concentrated on items with nontrivial `pi_0(i | u, c)`.

### 3.2 Old-Policy Lock-In

**Section goal**  
Show why policy dependence is not just a data issue but an evaluation issue.

**Key claims**  
- Offline evaluation usually compares a candidate policy `pi_1` using labels generated under `pi_0`.
- Models closer to `pi_0` often enjoy a structural advantage in historical replay.
- A policy shift can look weak offline simply because the log is thin where the new policy differs most.

**Example or intuition to include**  
- If the old movie recommender emphasized familiar blockbusters, a new model that also ranks them highly will match the held-out log more often.
- A more personalized model may move probability mass toward long-tail titles that old logs barely cover.

**What not to include**  
- Do not claim every policy change is unfairly penalized.
- Do not overstate this as a complete impossibility result.

**Rigor note**  
- This subsection can state the core mismatch directly: the evaluation target is performance under `pi_1`, but the observed outcomes were generated under `pi_0`.

### 3.3 Novel Items and Cold Start

**Section goal**  
Explain why old logs are especially weak for evaluating recommendations that expand coverage.

**Key claims**  
- Historical replay is partial because it contains little information about items that were new, rare, or previously underexposed.
- This creates a conservative bias toward already visible inventory.
- Novel recommendation quality is exactly where offline evidence is often thinnest.

**Example or intuition to include**  
- A newly added indie film has little interaction history, so a model that intelligently recommends it receives limited credit from historical logs.
- The same issue applies to catalog corners that past systems rarely surfaced.

**What not to include**  
- Do not turn this into a long cold-start methods section.
- Do not drift into supply-side marketplace dynamics.

**Rigor note**  
- A short support argument works well: if an item or item class has near-zero exposure under `pi_0`, offline replay cannot confidently estimate user response under broader exposure.

### 3.4 Trajectory Blindness

**Section goal**  
Argue that one-step relevance metrics miss important aspects of recommender quality that emerge over repeated interaction.

**Key claims**  
- Recommendation quality is not purely the quality of the next ranked list.
- Repetition, boredom, novelty, trust, and session fatigue are trajectory-level phenomena.
- A system can perform well on one-step offline metrics while degrading the longer-run user experience.

**Example or intuition to include**  
- A movie recommender that repeatedly serves slight variations of familiar titles may optimize short-term watch probability while making the experience stale over several sessions.
- Another model may sacrifice a small amount of one-step confidence to create healthier exploration over time.

**What not to include**  
- Do not promise exact long-horizon utility estimation.
- Do not collapse into product philosophy or retention strategy.

**Rigor note**  
- This is the place for a short technical contrast: most offline metrics summarize `r_t` at one step, while the user experience often depends on properties of the sequence `(a_1, r_1), ..., (a_T, r_T)`.

### 3.5 What This Means: Recommenders Are Not Static Predictors

**Section goal**  
Synthesize the previous subsections into one explicit statement of the article’s thesis.

**Key claims**  
- Offline evaluation often treats recommender quality as if it were a static prediction problem with fixed labels.
- In practice, recommendation is an interactive system problem because the policy changes exposure and exposure changes behavior.
- The key missing object is quality under interaction, not just agreement with historical outcomes.

**Example or intuition to include**  
- Ask what happens after the first recommendation: does the user get more of the same, discover a better niche fit, or disengage from repetition?
- Tie the synthesis back to the movie example without adding new machinery.

**What not to include**  
- Do not introduce the solution stack yet.
- Do not repeat all prior subsections in different words.

---

## 4. Why It Still Matters

This section should be intentionally placed after the critique. The critique is not an accident to be softened away; it is the core argument. This section exists to show discipline and fairness after the structural limitations have been made explicit.

**Section goal**  
Explain why offline evaluation remains indispensable despite its limitations.

**Key claims**  
- Offline evaluation is still valuable for fast iteration, benchmarking, sanity checks, and regression detection.
- It is often the cheapest and safest first screen before online testing.
- The right conclusion is not “discard offline evaluation,” but “place it correctly in a broader evaluation stack.”

**Example or intuition to include**  
- In the movie setting, a team still needs an inexpensive way to reject clearly weak ranking models before any live test.
- Offline comparisons remain useful when the policy shift is small or when the goal is model debugging rather than full product judgment.

**What not to include**  
- Do not apologize for the critique.
- Do not undo the force of the previous section.
- Do not imply offline metrics become sufficient once enough data is collected.

---

## 5. Running Example: Model A vs. Model B

**Section goal**  
Make the structural argument concrete with one consistent and intuitive example.

**Key claims**  
- Model A is safe, mainstream, and repetitive.
- Model B is more personalized and occasionally exploratory.
- Logs shaped by mainstream-heavy exposure may systematically make A look stronger than B in aggregate offline metrics.

**Example or intuition to include**  
- Conservative users may genuinely prefer A.
- Explorer and niche-interest users may benefit more from B.
- The key point is heterogeneity plus exposure dependence, not universal superiority.

**What not to include**  
- Do not introduce too many personas beyond what the demo will later use.
- Do not claim B is objectively better in all cases.
- Do not let the example become overly narrative.

---

## 6. A Better Direction, Briefly

**Section goal**  
Point toward a more behavior-aware evaluation approach without pretending to solve the whole problem.

**Key claims**  
- Offline evaluation should remain one layer, not the whole stack.
- Better evaluation should be more sensitive to segment-level differences and trajectory-level effects.
- Useful additions may include per-bucket diagnostics, repetition and novelty measures, and carefully designed simulated interaction.

**Example or intuition to include**  
- For the movie case, compare models not only on average relevance proxy but also on per-bucket behavior, repetition, novelty, and short traces.
- Position this as a better measurement direction, not a finished framework.

**What not to include**  
- Do not dive into synthetic users or agents in detail yet.
- Do not dump the full demo architecture.
- Do not sound like a platform pitch.

---

## 7. Conclusion

**Section goal**  
Close with a calm, strong restatement of the thesis.

**Key claims**  
- Offline evaluation remains indispensable.
- It is useful but insufficient because it is constrained by logged exposure and historical replay.
- If recommenders shape behavior, serious evaluation should account for interaction and trajectories.

**Example or intuition to include**  
- Return briefly to the movie example: what looks best in old logs is not always what produces the best experience under changed exposure.

**What not to include**  
- Do not end with hype.
- Do not claim the problem is solved.
- Do not broaden into a manifesto about AI evaluation generally.

---

**Artifacts Plan**

The article should not read like uninterrupted prose. It should have a small number of concrete artifacts that sharpen the argument and foreshadow the demo.

## Editorial Guidance

The next drafting pass should avoid solving repetition by simply deleting important ideas. The better approach is to give each important idea one clear home in the article and let later sections build on it rather than re-explain it.

**Primary homes for key ideas**
- Definition of offline evaluation: Section 2
- Policy dependence and exposure-conditioned evidence: opening of Section 3 plus Section 3.1
- Old-policy lock-in: Section 3.2
- Novelty and cold start limits: Section 3.3
- Trajectory-level quality: Section 3.4
- Counterbalance and practical value: Section 4
- Concrete intuition through Model A / Model B: Section 5
- Forward-looking measurement additions: Section 6

**Writing rule for later sections**
- Later sections should reference earlier ideas with lighter language rather than restating the full concept.
- The conclusion should restate the thesis once, not re-summarize each failure mode.
- The running example should carry concreteness, not re-teach the full theory.

**Jargon control**
- Keep technical terms that do real work, such as `logging policy`, `exposure`, `historical replay`, and `one-step metric`.
- Avoid stacking near-synonymous phrases in the same paragraph.
- Prefer plain research-engineering prose over literature-style label accumulation.
- If an idea needs repeated explanation, move part of that burden into a figure, table, or demo artifact.

## Artifact 1: One Compact Comparison Table

**Working title**  
What Offline Evaluation Captures, and What It Misses

**Columns**  
- Evaluation aspect
- Usually visible in offline replay
- Weakly captured or missed
- Movie recommender example

**Rows**  
- Immediate relevance under existing exposure
- Performance under policy shift
- Novel or underexposed items
- Cold start behavior
- Repetition over sessions
- Novelty and exploration
- Segment-level differences
- Trajectory-level user experience

**Draft content direction**
- Immediate relevance under existing exposure: often captured reasonably well by held-out ranking metrics.
- Performance under policy shift: weak where the candidate policy differs most from the logging policy.
- Novel or underexposed items: weak because prior exposure is sparse.
- Cold start behavior: weak because replay has little support for new items or very sparse users.
- Repetition over sessions: usually missed unless measured explicitly.
- Novelty and exploration: only partially visible in one-step replay.
- Segment-level differences: often hidden by aggregates unless metrics are bucketed.
- Trajectory-level user experience: largely missed by standard one-step metrics.

**Placement in article**
- Put this table after `Why It Still Matters` and before `Running Example: Model A vs. Model B`.
- The table should act as a hinge: it keeps the critique fair while setting up the example and the later demo.

## Artifact 2: One Small Diagram

**Working idea**  
Old policy -> exposure -> observed interactions -> offline metric

**Purpose**  
- Visually show that the evaluation data is downstream of earlier recommendation decisions.
- Make policy dependence intuitive in one glance.

## Artifact 3: One Lightweight Result Table Linked to the Demo

**Working idea**  
Compare Model A and Model B on:
- aggregate offline score
- repetition
- novelty
- per-bucket outcomes

**Purpose**  
- Reinforce the article’s main point without requiring a large experimental section.
- Show how similar aggregate scores can hide meaningful behavioral differences.

**Editorial role**
- This table should absorb some of the explanatory repetition that would otherwise recur in Sections 5, 6, and 7.
- It can carry the contrast between aggregate relevance, novelty, repetition, and bucket-level differences more compactly than prose.

---

**Demo Alignment Notes**

The writing should quietly prepare the reader for the later demo rather than bolting it on at the end.

## Demo goals

- Use a public movie recommendation dataset.
- Compare a popularity baseline against a simple personalized recommender.
- Report both aggregate offline metrics and behavior-sensitive diagnostics.
- Show at least one case where aggregate offline results understate meaningful differences.

## Demo buckets

- Conservative mainstream user
- Explorer / novelty-seeking user
- Niche-interest user
- Low-patience user

## Demo metrics to keep in mind while writing

- Standard offline metric: Recall@K or NDCG
- Repetition metric: repeated exposure or genre/item concentration
- Novelty metric: average popularity rank or tail exposure
- Bucket-specific score
- Short trace examples showing fatigue or discovery

## Writing implication

When drafting Section 3, we should use language that naturally connects to these later measurements:
- exposure
- support
- repetition
- novelty
- segment differences
- trajectories

That way the demo feels like evidence for the argument rather than a separate add-on.

---

**Demo Build Plan**

The demo should stay small, reproducible, and easy to explain in screenshots. The point is not to build the best recommender. The point is to build the smallest comparison that makes the article’s claim visible.

## Recommended dataset choice

- Start with `MovieLens 100K` for simplicity and speed.
- It is small enough for a single script, but still has enough user-item structure and genre metadata to support a meaningful demo.
- If we later need more variety, we can swap to `ml-latest-small` without changing the architecture much.

## Recommended recommenders

### Recommender A: Popularity baseline

- Score items by global interaction count or positive-rating count in the training split.
- Use this as the intentionally safe, high-exposure baseline.
- Keep it deterministic and easy to inspect.

### Recommender B: Simple personalized recommender

- Recommended first version: a lightweight user-profile scorer using genre affinity plus a mild popularity prior.
- User representation: average genre vector of positively rated training items for each user.
- Item representation: multi-hot genre vector plus normalized popularity.
- Candidate score: `score_B = cosine(user_genre_profile, item_genres) + lambda * popularity`.

**Why this choice**
- It is easy to implement.
- It is easy to explain in the article.
- It makes the bucket behavior more interpretable than a heavier latent-factor model.
- It preserves room to swap in item-item collaborative filtering later if needed.

## Bucket design

The buckets should not require a full generative user simulator. They can be implemented as lightweight scoring preferences layered on top of recommendation lists.

### 1. Conservative mainstream user
- Prefers high relevance and high popularity.
- Penalizes long-tail items lightly.
- Tolerates repetition.

### 2. Explorer / novelty-seeking user
- Values relevance, but receives a positive bonus for lower-popularity or less repetitive recommendations.
- Rewards controlled exploration.

### 3. Niche-interest user
- Strongly rewards match to a narrow genre profile.
- Cares less about global popularity.
- Makes long-tail personalization more visible.

### 4. Low-patience user
- Has a steeper penalty for repeated or low-fit items.
- Session quality can degrade quickly if the list becomes stale.

## Minimal evaluation outputs

- Aggregate offline metric: `Recall@K` or `NDCG@K`
- Per-bucket score: mean bucket utility for each recommender
- Repetition metric: concentration or duplication score over top-`K` / short session traces
- Novelty metric: inverse popularity or average popularity rank of recommended items
- Three short plain-English bucket summaries generated from the metric differences

## Suggested architecture

### `data_loader`
- Load ratings and movie metadata.
- Create a chronological or leave-last-out train/test split per user.

### `representations`
- Build item genre vectors and popularity features.
- Build user profiles from training interactions.

### `recommenders`
- Shared interface: `fit(train)`, `recommend(user_id, k)`
- Implement `PopularityRecommender`
- Implement `ProfileRecommender`

### `bucket_simulator`
- Convert recommendation lists into bucket-specific utility scores.
- Keep this logic explicit and inspectable rather than learned.

### `evaluator`
- Compute aggregate offline metrics.
- Compute per-bucket scores.
- Compute repetition and novelty metrics.

### `report_generator`
- Produce one screenshot-friendly markdown or HTML report.
- Include one comparison table and one simple plot if convenient.

## Report shape

The report should be easy to drop into the article.

- Header with dataset and recommender definitions
- One compact comparison table: A vs B on aggregate metrics and bucket metrics
- One plot or heatmap for bucket-level differences
- Three short bucket summaries in plain English
- Optional appendix block with a few sample recommendation traces

## Implementation guardrails

- Prefer a single script or notebook with small helper modules over a large package.
- Avoid deep training pipelines, hyperparameter search, or heavy dependency stacks.
- Keep metric definitions simple and visible in code.
- Optimize for interpretability and article value, not benchmark performance.
