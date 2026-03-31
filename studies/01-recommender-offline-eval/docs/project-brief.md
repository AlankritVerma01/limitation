# Project Brief
## Article + Demo
### Title
Why Offline Evaluation Is Not Enough for Recommendation Systems

---

# 1. Mission

Write a technical, research-style blog post arguing that offline evaluation is useful but insufficient for recommendation systems.

The article should:
- explain what offline evaluation is
- explain why it is widely used
- identify its structural limitations
- use one concrete running example throughout
- introduce a better direction without trying to solve everything
- feel thoughtful, technical, and credible

This is not a startup launch post.
This is not a broad post about all non-deterministic systems.
This is not a generic AI-agents article.

It is a focused technical argument:
offline evaluation does not fully capture real recommender quality because recommenders are interactive systems that shape user behavior.

---

# 2. Core Thesis

Offline evaluation for recommendation systems is useful, but incomplete.

It evaluates models using historical logged behavior generated under older exposure policies.
Because of that, it struggles to fairly measure:
- novel recommendations
- policy shifts
- cold start behavior
- long-horizon interaction quality
- user experience over trajectories rather than one-step outcomes

If recommendation systems shape what users see, then evaluating them only on past logged outcomes misses part of the true problem.

---

# 3. One-Sentence Version

Recommendation systems are interactive systems, but offline evaluation often treats them like static predictors.

---

# 4. What This Article Is Really About

This article is about a mismatch:

- what recommenders actually are:
  interactive systems that influence future user behavior

- what offline evaluation often assumes:
  fixed historical labels are enough to judge future quality

That mismatch is the heart of the piece.

---

# 5. Scope

Keep the article narrow.

Cover:
- offline evaluation
- recommendation systems
- exposure bias / old-policy lock-in
- trajectory blindness
- one concrete movie recommendation example
- a short preview of a better evaluation direction

Do not cover in depth:
- all LLM evals
- all agent systems
- all applications
- full startup/product vision
- robotics
- full synthetic population framework in detail

Those can come later.

---

# 6. Tone and Style

Tone:
- technical
- precise
- fair
- skeptical
- non-hype
- product-aware but not startup-pitchy

Style:
- short paragraphs
- strong transitions
- one main idea per section
- avoid buzzwords unless defined
- do not overclaim

Use phrases like:
- useful but insufficient
- constrained by logged exposure
- policy-dependent data
- trajectory-level quality
- interactive system
- historical replay is partial
- behavior is shaped, not merely observed

Avoid phrases like:
- revolutionary
- game-changing
- this changes everything
- the future of AI
- autonomous swarms everywhere

---

# 7. Audience

Primary audience:
- ML engineers
- recommender systems engineers
- applied researchers
- infra / eval people
- technical founders

Secondary audience:
- smart engineers who know offline eval conceptually but have not deeply thought about its limits

Write for readers who are technical enough to follow, but not necessarily recommender specialists.

---

# 8. Main Claims

## Claim 1
Offline evaluation is useful, but it is constrained by old exposure.

Meaning:
historical logs only tell us how users responded to what the previous system showed them.

## Claim 2
A better recommender can look worse offline.

Meaning:
if a new model surfaces content that was rarely or never exposed under the old policy, the historical data may not fairly reflect its true value.

## Claim 3
Recommendation quality is not purely one-step.

Meaning:
quality emerges over interaction trajectories:
- repetition
- boredom
- exploration
- novelty
- trust
- churn
- satisfaction over time

## Claim 4
Recommenders should be evaluated more like interactive systems than static predictors.

This is the bridge to the future direction.

---

# 9. Counterbalance / Fairness Section

The article should explicitly acknowledge that offline evaluation is still important.

Say clearly that offline evaluation is useful for:
- fast iteration
- benchmarking
- sanity checks
- relative model comparisons
- early-stage experimentation

Do not portray offline eval as useless.
The argument is:
offline eval is necessary, but not enough.

That makes the piece stronger and more credible.

---

# 10. Running Example

Use one example throughout:
a movie recommender.

## Model A
safe, popular, highly mainstream, repetitive

## Model B
more personalized, occasionally more exploratory, better for niche tastes

The point:
historical logs may unfairly favor Model A because the data was generated under prior exposure patterns that already emphasized popular items.

That makes the failure intuitive.

---

# 11. Key Concepts to Explain Clearly

## Offline Evaluation
Evaluating a recommender using historical logged interactions rather than live user traffic.

## Exposure Bias
Users can only interact with items they were shown.
So the data reflects past exposure decisions, not the full space of possible relevant items.

## Old-Policy Lock-In
A new model is evaluated using outcomes generated under an old policy.
This can systematically disadvantage models that change exposure patterns.

## Trajectory Blindness
One-step metrics do not fully capture what happens over repeated interaction:
repetition, drift, exploration, boredom, session quality, churn.

## Interactive System
A system whose outputs influence future inputs and future user behavior.

---

# 12. Article Structure

## Section 1 — Hook
Goal:
Open with the contrast between testing code and evaluating recommenders.

Possible direction:
We know how to test deterministic software.
Recommendation systems are harder because they do not just predict behavior; they shape it.

## Section 2 — What Offline Evaluation Is
Goal:
Give a clean and fair explanation.

Should cover:
- historical data
- held-out interactions
- ranking metrics
- why teams use it

Keep it simple and non-mathy unless necessary.

## Section 3 — Why Offline Evaluation Works Well in Practice
Goal:
Show respect for current practice.

Mention:
- cheap
- fast
- reproducible
- useful for iteration
- useful for benchmarking

This section prevents the article from sounding naive.

## Section 4 — Where Offline Evaluation Breaks
This is the core section.

Subsections:
### 4.1 Exposure bias
You only observe what users were shown.

### 4.2 Old-policy lock-in
You judge new policies using data created by older policies.

### 4.3 Cold start / novel content
New item exposure is poorly captured by old logs.

### 4.4 Trajectory blindness
A recommender can look good on one-step relevance but still produce boring or unhealthy long-term sessions.

## Section 5 — Concrete Example
Use the movie recommender example.

Explain:
Model A surfaces popular, familiar movies.
Model B introduces a better long-tail / niche mix for certain users.

Offline data may systematically underrate B because the historical logs were mostly shaped by older popular-item exposure.

## Section 6 — What Is Missing
State the gap:
we are evaluating recommenders as if they were static predictors rather than interactive systems.

This is the turning point of the article.

## Section 7 — A Better Direction
Keep this section short and forward-looking.

Introduce only lightly:
- user buckets / personas
- simulated interaction
- trajectory-based evaluation
- per-segment diagnostics

Do not dump the whole startup here.
Just show that a more behavior-aware approach is possible and likely necessary.

## Section 8 — Conclusion
End with:
offline evaluation remains necessary, but it should not be mistaken for a full test of recommender quality.
If recommenders shape behavior, then better evaluation must account for interaction.

---

# 13. Demo Pairing

The article should ideally have a small side demo that supports the thesis.

## Goal of Demo
Compare two recommenders on a public dataset and show that aggregate offline metrics are not the full story.

## Minimal Demo Inputs
- public recommendation dataset
- recommender A
- recommender B
- 4 synthetic user buckets

## Minimal Demo Outputs
- average score / relevance proxy
- per-bucket score
- repetition metric
- novelty metric
- a few failing traces or bucket summaries

## Buckets
Suggested 4:
1. Conservative mainstream user
2. Explorer / novelty-seeking user
3. Niche-interest user
4. Low-patience user

## Recommenders
Suggested:
- popularity baseline
- simple personalized model

## What the demo should show
Even if average offline score looks similar, bucket-level or trajectory-level behavior can diverge:
- one model is more repetitive
- one model underserves niche users
- one model does better for explorers
- one model causes faster session fatigue

---

# 14. What the Article Should Not Do

Do not:
- claim that offline eval should be replaced entirely
- claim that synthetic users are already the answer to everything
- claim that this is solved
- broaden too much into all AI systems
- write like a startup pitch deck
- use too many applications
- introduce too many new terms

Keep it sharp and narrow.

---

# 15. What Makes This Article Strong

The article is strong if:
- it is fair to offline eval
- it makes one clean argument
- the movie recommender example is intuitive
- it clearly explains why historical logged behavior is policy-dependent
- it avoids hype
- it leaves the reader feeling:
  "yes, this is a real structural issue"

---

# 16. Drafting Rules

When writing:
- lead with the problem, not the solution
- do not mention agents too early
- do not mention the startup too early
- stay on recommenders throughout
- use the phrase "interactive systems" deliberately
- keep paragraphs short
- avoid giant literature-survey tone
- prioritize clarity over jargon

---

# 17. Potential Title Options

Preferred:
- Why Offline Evaluation Is Not Enough for Recommendation Systems

Alternatives:
- The Limits of Backtesting Recommenders
- Recommendation Systems Are Interactive Systems. We Should Evaluate Them That Way.
- What Offline Evals Miss in Recommendation Systems

Use the first one unless a better title emerges naturally.

---

# 18. Potential Opening Lines

Option A:
We know how to test code. We are much less certain about how to test behavior.

Option B:
Offline evaluation is one of the most common tools in recommendation systems. It is also easy to mistake for a full test of product quality.

Option C:
Recommendation systems are usually evaluated on historical interactions, but those interactions were produced by earlier recommendation policies. That detail matters more than it first appears.

---

# 19. Potential Closing Direction

The final note should be calm and strong, something like:

Offline evaluation remains indispensable, but recommendation systems are not static predictors. They are interactive systems that shape the behavior they later observe. Any serious evaluation stack should account for that fact.

---

# 20. Next Deliverables

After this brief, the work should happen in this order:

1. Write a detailed outline section by section
2. Draft the introduction
3. Draft the core "where offline eval breaks" section
4. Add the running movie example
5. Add the short "better direction" section
6. Tighten language and remove fluff
7. Build the tiny demo
8. Connect the article and demo with one figure or one result table

---

# 21. If Expanding Later

Possible follow-up posts:
- Synthetic population testing for recommenders
- Beyond LLM-as-a-judge: testing systems in interaction
- CI for non-deterministic systems
- Bucketed trajectory evaluation for AI products

But not in this first article.