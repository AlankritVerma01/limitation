## Why Offline Evaluation Is Not Enough for Recommendation Systems

_Offline evaluation is essential for recommender systems. It is also easy to mistake for a fuller measure of quality than it really is._

### TL;DR

- Offline evaluation is useful, fast, and necessary for recommender systems.
- But it is built on logged behavior generated under older exposure policies.
- That makes it weak at judging policy shifts, novel items, cold start behavior, and longer interaction trajectories.
- In a small MovieLens demo, the popularity baseline wins on aggregate offline ranking metrics, while a more personalized model does better for explorer, niche-interest, and low-patience user buckets.
- The practical conclusion is not to replace offline evaluation, but to stop treating it as a full test of recommender quality.

> Recommendation systems are interactive systems, but offline evaluation often treats them like static predictors.

---

### 1. The Testing Gap

We know how to test deterministic software. We are much less certain about how to test systems that influence the behavior they later observe.

Recommendation systems sit squarely in that second category. They do not just estimate what a user might click, watch, or purchase. They decide what the user gets a chance to see, and that choice helps shape the data that will later be treated as evidence.

Offline evaluation is one of the standard tools in recommender systems for good reason. It is practical, fast, and often highly informative. A team can compare candidate models on historical interaction data long before it is ready to send live traffic to a new ranking policy.

That usefulness, however, can make offline evaluation easy to over-interpret. A strong offline result often sounds like a strong statement about real recommendation quality. Sometimes it is. But the conclusion is narrower than it first appears.

Historical interaction logs are not simply records of user preference. They are records of user preference under a particular pattern of exposure. They reflect what earlier systems chose to rank, recommend, and repeat. In that sense, the data is policy-dependent from the beginning.

This matters because recommendation quality is not only about matching a fixed label. A recommender is an interactive system. Its outputs affect future inputs. Change the policy, and over time you may change what users discover, what they come to trust, what they ignore, and what they eventually consume.

Consider a movie recommender. One model may reliably surface popular, familiar titles. Another may be more personal and more willing to introduce niche films that fit a specific user's taste. If the historical logs were generated under a system that already emphasized mainstream titles, those logs may be much richer in evidence for the first model's choices than for the second model's.

That does not make offline evaluation wrong. It does mean the object being measured is more limited than many teams would like. Offline evaluation is useful, but insufficient.

The point of this article is narrow. It is not that offline evaluation should be discarded, and it is not a general argument about all machine learning systems. The claim is simpler: recommendation systems are interactive systems, and that fact places real limits on what historical replay can tell us.

---

### 2. What Offline Evaluation Is

Offline evaluation, in the recommender setting, means evaluating a model on historical logged interactions rather than on live user traffic. The usual pattern is straightforward: train on past user-item behavior, hold out a later slice of interactions, and ask whether the model ranks the held-out items highly for the relevant users.

In a movie recommendation system, the data might include watches, clicks, ratings, or add-to-list events. A model is trained on part of that history and then evaluated on interactions that were not shown during training. If a user later watched a particular film, one basic offline question is whether that film would have appeared near the top of the model's ranked list.

This setup supports the ranking-style metrics commonly used in recommender systems. Teams may report measures such as Recall@K, hit rate, or NDCG to summarize how well a model recovers held-out interactions. The exact metric matters, but the general logic is the same: use historical behavior as a proxy for whether the recommendations were good.

That approach is attractive because it gives a concrete and reproducible testing loop. Candidate models can be compared against the same held-out data. Regressions can be caught before launch. Incremental improvements can be measured without the cost and risk of online experimentation.

It is also important to be precise about what this evaluation is actually saying. Offline evaluation does not directly measure how users would respond to a new policy in a live environment. It measures how well a model aligns with historical interactions recorded under earlier exposure conditions.

That distinction is easy to blur because the workflow looks so familiar. We have training data, a test set, and a metric. But in recommendation systems, the labels are not independent of the system that helped generate them. The held-out watch or click is not just a fact about the user. It is also a fact about what the user was shown.

For now, that is enough of a working definition. Offline evaluation is historical replay over logged interactions, typically framed as a ranking problem, and used as a proxy for recommendation quality under observed conditions. It is a very useful proxy. The rest of the article asks where its boundaries are.

---

### 3. Where Offline Evaluation Breaks

The limitations of offline evaluation do not come from a single bad metric or a single avoidable mistake. They come from a more basic fact about recommender data: the data is generated under a policy. What users do in the logs depends in part on what earlier systems chose to show them.

That sounds obvious when stated directly. But it has deeper consequences than it first appears. If the evidence used for evaluation is itself shaped by older recommendation decisions, then offline evaluation is not observing some neutral ground truth about relevance. It is observing relevance through the filter of past exposure.

In a static prediction task, that distinction is often less severe. In recommendation, it sits near the center of the problem. A new recommender is rarely judged against untouched labels. It is judged against behavior recorded under an older recommender, with its own ranking habits, popularity biases, and coverage patterns.

We can state the issue in simple notation. Let `pi_0` be the logging policy that generated the historical data, and let `pi_1` be the new policy we want to evaluate. Offline replay uses observations gathered under `pi_0` to estimate the quality of `pi_1`. If `pi_1` behaves much like `pi_0`, that may be informative. If it changes exposure materially, the estimate becomes much less complete.

This is the core mismatch. The quantity we want is user response under the candidate policy. The quantity we usually observe is user response under the previous policy. The two overlap, but they are not the same object.

#### 3.1 Exposure Bias

The first break is exposure bias. Users can only react to items they were actually shown.

That means an interaction log is not just a record of what users preferred. It is also a record of what the system made available. When an item receives no click, no watch, or no rating, that absence does not cleanly mean the item was irrelevant. In many cases it means the item was never placed in front of the user at all.

This matters immediately for offline evaluation. Suppose a movie platform has historically given heavy exposure to well-known studio releases and much lighter exposure to niche films. The resulting data will contain dense evidence for how users responded to the mainstream catalog and sparse evidence for how they would have responded to more specialized titles.

The bias here is structural rather than anecdotal. If observed feedback only exists for exposed items, then the support of the evaluation data is concentrated where the logging policy chose to spend attention. In compact form, observed reward is only available where `pi_0(i | u, c)` is nontrivial for user `u`, item `i`, and context `c`.

That is why historical replay is partial. It is not sampling uniformly from all relevant user-item pairs. It is sampling from the subset that earlier policies made visible. In a movie recommender, this can make “popular” look easier to measure than “personally relevant,” even when the latter is closer to the product goal.

#### 3.2 Old-Policy Lock-In

Exposure bias becomes more consequential when a new policy differs from the old one in systematic ways. This is where old-policy lock-in appears.

In most offline evaluations, the labels used to assess a candidate model were generated under a different ranking policy. A held-out watch event looks like a simple target, but it is downstream of earlier recommendation decisions. The new model is therefore being judged with evidence produced by the system it may be trying to replace.

This creates an asymmetry. Models that resemble the old policy often enjoy richer and cleaner evidence in the historical logs. Models that shift probability mass toward less exposed regions of the catalog are evaluated in the parts of the space where the logs are thinnest.

Return to the movie example. If the old system strongly favored familiar blockbusters, then the held-out data will naturally contain many interactions with those titles. A candidate model that continues to rank them highly will line up well with the log. Another model that is more willing to surface quieter but well-matched films may look weaker offline, not necessarily because users dislike those recommendations, but because the old system rarely created opportunities to observe that preference.

This is one reason a better recommender can look worse offline. The issue is not only model accuracy. It is evaluation support. When performance is estimated on outcomes generated under `pi_0`, the comparison can systematically favor policies that stay close to `pi_0`.

That does not make all offline comparisons invalid. If two models differ only slightly, offline evaluation can still be highly useful. But when a candidate policy changes exposure patterns in meaningful ways, offline results should be read with more caution than the metric alone suggests.

#### 3.3 Novel Items and Cold Start

The same logic becomes even sharper for new or rarely exposed content.

Offline evaluation is strongest where historical evidence is plentiful. It is weakest where exposure has been limited, recent, or absent. Unfortunately, those are often exactly the regions where recommendation systems are asked to do something valuable: introduce new items, expand coverage, and connect users to parts of the catalog they would not have reached on their own.

In a movie platform, consider a newly added independent film with very little interaction history. A model may have good reasons to recommend it to a narrow set of users based on metadata, embeddings, or nearby behavioral signals. But if the film barely appeared under the previous policy, then historical logs offer limited evidence for how good that recommendation would actually be.

The problem is not only that the item is new. The deeper issue is that offline replay inherits the conservatism of past exposure. It is much easier to validate recommendations for already visible inventory than for inventory the old policy neglected.

This creates a subtle but important pressure. Systems that stay near the historically exposed core of the catalog are easier to justify with offline evidence. Systems that broaden exposure toward the tail are often evaluated precisely where the data is least informative. Over time, that can make conservative recommendation strategies look more reliable than they really are, and exploratory strategies look less supported than they might deserve.

The claim is not that offline evaluation fails in every cold-start setting. It is that historical replay is structurally weak exactly where a recommender tries to broaden exposure. For recommenders, novelty is often where the evidence is thinnest.

#### 3.4 Trajectory Blindness

Even if the exposure problem disappeared, there would still be another limitation. Recommendation quality is not purely one-step.

Most offline metrics compress evaluation into local ranking success. Did the model place the held-out item near the top? Did it recover the next watch? Did it improve a ranking score on observed interactions? Those are reasonable questions, but they are mostly questions about immediate alignment with historical events.

Users, however, experience recommendation systems as sequences. They return across sessions. They compare one recommendation to the previous one. They notice repetition. They develop trust or impatience. They learn whether the system helps them explore or merely loops them through slight variations of what it already knows how to sell.

This is where trajectory blindness enters. A recommender can look strong on one-step relevance and still create a poor multi-step experience.

Imagine a movie recommender that repeatedly serves highly similar popular thrillers because those titles have strong historical watch signals. In a one-step offline evaluation, this may look sensible. The recommendations are close to what users have previously consumed, and the metrics may reward that closeness. But over several sessions the user may experience the system as narrow, repetitive, and increasingly unhelpful.

Another model might trade a small amount of one-step certainty for a better sequence. It may alternate between reliable choices and occasional high-fit long-tail discoveries. That kind of quality often lives in the trajectory rather than in any single ranking event.

In notation, many offline metrics focus on something close to the quality of `r_t` at a single step. But recommender quality often depends on properties of the sequence `(a_1, r_1), ..., (a_T, r_T)`: how concentrated the recommendations are, whether novelty appears at the right rate, whether boredom accumulates, and whether the system adapts well after earlier choices.

This is not an argument against ranking metrics. It is an argument about what they leave out. They summarize one-step fit to logged behavior. They do not, by themselves, tell us whether the interaction over time becomes richer, narrower, more repetitive, or more satisfying.

#### 3.5 What This Means

Taken together, these limitations point to a single conclusion. Offline evaluation often treats recommendation as if it were a static prediction problem with fixed labels. In practice, recommendation is an interactive system problem.

The system chooses what to expose. Exposure shapes what users can respond to. Those responses become the data for future training and evaluation. Change the policy, and you may change the distribution of behavior itself.

Once that is clear, the goal of evaluation also becomes clearer. The question is not only whether a model can replay the past. It is whether it can support good interaction under a changed policy. Historical replay helps answer that question, but only in part.

---

### 4. Why It Still Matters

None of these limitations make offline evaluation disposable. They define its scope. That distinction matters.

Recommendation teams rely on offline evaluation because it solves real engineering problems well. It is fast, reproducible, and comparatively cheap. It allows model changes to be screened before they reach users. It supports regression testing, debugging, ablation work, and benchmarking across candidate approaches. In most practical settings, there is no credible evaluation stack that excludes it.

That remains true even after the critique above. A recommender team still needs a way to reject clearly weak models, validate implementation changes, and compare alternatives under a common protocol. Offline evaluation is often the first place where obvious failures become visible. If a ranking model cannot perform competitively in historical replay, it is usually hard to justify sending it to live traffic.

This is especially important because online tests are expensive in more than one sense. They consume time, user attention, and organizational focus. They are also constrained by risk. A platform may be willing to test a modest ranking change online, but not a model that already appears unstable or uncompetitive offline. Historical evaluation remains the practical filter through which many candidate models must pass.

The right conclusion, then, is not that offline evaluation should be replaced. It is that offline evaluation should be placed correctly. It is a strong tool for iteration and a weak tool for making broad claims about full recommender quality under changed exposure.

In other words, the critique is intentional. Offline evaluation is widely used because it earns its place. The mistake is not using it. The mistake is mistaking it for a complete test.

One compact way to summarize that balance is to separate what offline replay usually measures well from what it tends to leave undermeasured.

| Evaluation aspect | What offline replay usually captures | What it tends to miss or undermeasure | Movie recommender example |
| --- | --- | --- | --- |
| Immediate relevance under existing exposure | Whether held-out watched items appear near the top of the ranked list | Whether that ranking would still look good under a materially different exposure policy | A familiar blockbuster appears in the top `K` because it was already heavily exposed |
| Performance under policy shift | Small improvements that stay near the old policy | Quality of recommendations in regions where the candidate policy differs most | A model that surfaces more niche dramas has little historical support where it differs from the old system |
| Novel or underexposed items | Some signal for items with enough prior exposure | Items that were new, rare, or historically under-shown | A newly added indie film receives little offline credit even if it fits the user well |
| Cold start behavior | Very coarse performance on sparse users or items | Early recommendation quality when interaction history is thin | A new documentary enters the catalog with too little evidence for replay to judge it fairly |
| Repetition over sessions | Little, unless explicitly measured | Accumulated sameness across repeated visits | The recommender keeps offering slight variations of the same thriller over multiple sessions |
| Novelty and exploration | Limited signal through held-out interactions | Whether the system introduces useful discovery at the right rate | A long-tail science-fiction recommendation may be good, but the old logs barely contain exposure to it |
| Segment-level differences | Aggregate averages over the evaluation set | Which user groups are helped or hurt by the new policy | Mainstream users may do well under Model A while exploration-seeking users do better under Model B |
| Trajectory-level user experience | Almost nothing in standard one-step metrics | Trust, boredom, fatigue, and satisfaction over sequences | A user keeps getting acceptable next picks but gradually disengages from repetition |

---

### 5. Running Example: Model A vs. Model B

The structural issues above become easier to see with a simple running example. Consider a movie recommendation system with two candidate rankers.

Model A is conservative. It leans toward popular, broadly watched titles and tends to recommend within the historically dominant regions of the catalog. It is usually safe, usually familiar, and often repetitive.

Model B is more personalized. It still recommends mainstream films when they fit, but it is more willing to surface niche titles, less obvious matches, and items from thinner parts of the catalog when the user profile suggests they are a good fit.

Suppose the historical logs were generated under an earlier recommendation policy that behaved more like Model A. Popular titles received heavy exposure. Niche titles were shown less often. Over time, that policy produced abundant feedback on the mainstream catalog and much weaker evidence on long-tail items.

Now evaluate both models offline on held-out interactions from those logs.

Model A will often look strong for a simple reason: it aligns well with the exposure pattern that helped generate the data. It ranks many of the same kinds of items the old system already showed, so the held-out interactions contain ample opportunities to reward it.

Model B may be better calibrated to particular users, especially users with narrower tastes or stronger appetite for discovery. But if many of its most valuable recommendations lie in regions of the catalog that were rarely exposed before, the offline log may not give it much credit. The evidence needed to validate those choices was never fully collected.

This does not mean Model B is necessarily better overall. Some users may indeed prefer the safer behavior of Model A. That is part of the point. Recommendation quality is heterogeneous across users and across sessions, and a single aggregate score can hide that heterogeneity.

The difference becomes clearer over repeated interaction. Model A may continue to produce acceptable next-item recommendations while gradually narrowing the user's experience into a small, overexposed slice of the catalog. Model B may produce a slightly noisier immediate ranking while creating a better long-run sequence for users who value novelty or have specialized tastes.

This is the kind of divergence a later demo can make visible. Two models may look similar on an aggregate offline metric and still differ meaningfully in repetition, novelty, and which user groups they serve well.

#### A Small MovieLens Demo

To make that less abstract, I built a small comparison on MovieLens 100K. The setup is intentionally simple. Model A is a popularity baseline. Model B is a lightweight personalized recommender built from user genre profiles with a modest popularity prior. The point is not to produce the strongest possible recommender. The point is to see what different layers of evaluation say about the same pair of systems.

**Aggregate view:** on standard offline ranking metrics, Model A looks better.

| Model | Recall@10 | NDCG@10 | Novelty | Repetition | Catalog concentration |
| --- | --- | --- | --- | --- | --- |
| Model A | 0.088 | 0.057 | 0.395 | 0.675 | 1.000 |
| Model B | 0.058 | 0.036 | 0.678 | 0.693 | 0.717 |

If we stopped there, the conclusion would be straightforward: the popularity baseline wins offline.

But that is exactly the point of the article. Once the evaluation is widened beyond a single aggregate view, the picture changes.

**Bucketed view:** the same two models look quite different once we ask who is being served well.

| Bucket | Model A utility | Model B utility | Delta (B-A) |
| --- | --- | --- | --- |
| Conservative mainstream | 0.519 | 0.532 | 0.012 |
| Explorer / novelty-seeking | 0.339 | 0.523 | 0.184 |
| Niche-interest | 0.443 | 0.722 | 0.279 |
| Low-patience | 0.321 | 0.364 | 0.043 |

The bucketed results are more revealing than the aggregate ones. Explorer users and niche-interest users benefit much more from Model B. Low-patience users also do slightly better under Model B in the short-session simulation, even though the aggregate offline ranking metrics still prefer Model A.

The behavior diagnostics tell a related story. Model B is substantially more novel and much less concentrated in the most popular slice of the catalog. For explorer users, bucket-level novelty rises from `0.405` under Model A to `0.808` under Model B. For niche-interest users, mean bucket utility rises by `0.279`. That is not a rounding error. It is a segment-level change that the aggregate offline metrics compress away.

![Bucket-level utility comparison from the MovieLens demo](https://dev-to-uploads.s3.amazonaws.com/uploads/articles/kffspju06ezccanmrb2o.png)

**What the demo says in one glance**

- Aggregate offline metrics favor Model A.
- Explorer, niche-interest, and low-patience buckets do better under Model B.
- Model B is much more novel and less concentrated in the most popular slice of the catalog.

**Two short traces make the difference more tangible.**

**Explorer / novelty-seeking user**

```text
Model A: Raiders of the Lost Ark -> Fargo -> Toy Story -> Return of the Jedi
Model B: Prophecy, The -> Cat People -> Wes Craven's New Nightmare -> Relic, The
```

The first sequence stays close to familiar, high-exposure titles. The second is much more novel and much more tailored to a narrower taste profile.

**Low-patience user**

```text
Model A: Star Wars -> Fargo -> Return of the Jedi -> Toy Story
Model B: Monty Python and the Holy Grail -> Full Monty -> American President -> Truth About Cats & Dogs
```

Here the difference is not just novelty. The second sequence moves through a less concentrated slice of the catalog rather than repeatedly returning to the same mainstream core.

This small demo does not prove that Model B is globally better. It does something more modest and more useful. It shows that the answer depends on what we mean by "better," which users we care about, and whether we look only at historical ranking recovery or also at the behavior a recommender produces over short trajectories.

---

### 6. A Better Direction, Briefly

If offline evaluation is necessary but incomplete, the natural response is not to discard it. The better response is to build a broader evaluation stack around it.

That broader stack should start from the failure modes already discussed. If logged exposure is policy-dependent, then evaluation should be more explicit about where the evidence is strong and where it is weak. If quality emerges over time, then some part of evaluation should examine sequences rather than only one-step ranking recovery.

In practice, this suggests a modest shift in emphasis. Instead of asking only for a single aggregate offline score, teams can also ask how models behave across user segments, how concentrated their recommendations become, how much novelty they introduce, and whether their behavior looks meaningfully different over short interaction traces.

For the movie example, that might mean comparing Model A and Model B not only on Recall@K or NDCG, but also on repetition, tail exposure, and bucket-level outcomes for users with different appetites for familiarity or exploration. None of these measurements solves the full problem. They simply make the evaluation better matched to the system being evaluated.

The same logic also motivates carefully designed simulated interaction or short trajectory-based testing. The point is not that such methods are already complete or universally trustworthy. The point is narrower: if recommenders shape future behavior, then some part of the evaluation stack should attempt to probe that interaction rather than treating historical replay as the whole story.

This is best understood as complement, not replacement. Offline evaluation remains the fast and reliable first layer. But serious evaluation of recommender quality likely needs additional layers that are more sensitive to exposure shifts, segment differences, and longer-run experience.

---

### 7. Conclusion

Offline evaluation remains one of the most useful tools in recommender systems. It is fast, practical, and deeply embedded in how teams iterate on models.

Its limitation is structural rather than procedural. The data it relies on is constrained by prior exposure and generated under earlier policies, so it provides only a partial test of recommender quality.

That matters most when a model changes what gets shown, expands beyond historically overexposed items, or affects the experience over repeated interaction. In those settings, replaying the past is not the same as evaluating the new system on its own terms.

Offline evaluation is indispensable, but it is not the whole test. Recommendation systems shape the behavior they later observe, so any serious evaluation stack should measure interaction, not just replay the past.
