# Testing ML Systems

This repository is one ongoing project about making ML testing better.

The core idea is simple: most ML systems are still tested too narrowly. We often check point metrics, benchmark scores, or one-step outcomes, but miss behavior over time, edge cases, failure modes, and the gap between offline evaluation and real system quality.

This repo is where that larger project lives. It will grow through a sequence of studies, demos, notebooks, and writing pieces that each explore one part of the problem.

## What This Repo Is

This is not a collection of unrelated mini-projects.

It is one main project focused on:

- better evaluation for ML systems
- better testing workflows for model-driven products
- more realistic diagnostics than single aggregate metrics
- practical demos and writing that make those ideas easy to understand

## Current Structure

- [studies/README.md](studies/README.md): index of the studies in this project
- [studies/01-recommender-offline-eval](studies/01-recommender-offline-eval): the first study, about offline evaluation limits for recommender systems
- [Makefile](Makefile): common developer commands
- [requirements.txt](requirements.txt): shared tooling for the repo

Study-local datasets, caches, and generated outputs are intentionally ignored by git so the public repo stays cleaner and does not redistribute third-party data by default.

## Study 01

The first study asks a concrete question:

> What does offline evaluation miss when the system being evaluated shapes future user behavior?

https://dev.to/alankritverma/why-offline-evaluation-is-not-enough-for-recommendation-systems-15ii

It uses a small MovieLens-based recommender demo, a notebook walkthrough, and a linked article draft to show why aggregate offline metrics can be useful and still incomplete.

## Quickstart

```bash
python3 -m venv .venv
source .venv/bin/activate
make install
make run
```

Open the current notebook:

```bash
make notebook
```

Run checks:

```bash
make lint
```

## Where This Is Going

The recommender write-up and demo are only the first slice of the project.

Over time, this repo is meant to expand into a broader body of work around ML testing, including richer evaluation setups, stress tests, trajectory-aware diagnostics, and eventually more automated ways to test ML algorithms and ML-driven product behavior.
