# limitation

[![PyPI version](https://img.shields.io/pypi/v/evidpath.svg)](https://pypi.org/project/evidpath/)
[![Python versions](https://img.shields.io/pypi/pyversions/evidpath.svg)](https://pypi.org/project/evidpath/)
[![CI](https://github.com/NDETERMINA/limitation/actions/workflows/evidpath-ci.yml/badge.svg)](https://github.com/NDETERMINA/limitation/actions/workflows/evidpath-ci.yml)
[![License](https://img.shields.io/pypi/l/evidpath.svg)](https://github.com/NDETERMINA/limitation/blob/main/products/evidpath/LICENSE)

Evidpath helps teams check a recommender before launch by running interaction
tests, saving clear evidence, and comparing two versions before they ship.

## What Evidpath Helps You Do

- check that your recommender endpoint or Python callable is wired correctly
- run a repeatable audit against a real target URL or in-process target
- open a report that shows who struggled and why
- compare a baseline and a candidate before launch

## Get Started In 3 Steps

Install the package:

```bash
python -m pip install evidpath
```

Check your endpoint:

```bash
evidpath check-target --domain recommender --target-url http://127.0.0.1:8051
```

Run one audit:

```bash
evidpath audit --domain recommender --target-url http://127.0.0.1:8051 --scenario returning-user-home-feed --seed 7
```

That run writes an output folder with files such as `report.md`,
`results.json`, and `traces.jsonl`.

## Where To Go Next

- product guide: [products/evidpath/README.md](products/evidpath/README.md)
- PyPI: <https://pypi.org/project/evidpath/>
- TestPyPI: <https://test.pypi.org/project/evidpath/>
- releases: <https://github.com/NDETERMINA/limitation/releases>
- demo guide: [products/evidpath/DEMO.md](products/evidpath/DEMO.md)
- external target contract: [products/evidpath/EXTERNAL_TARGET_CONTRACT.md](products/evidpath/EXTERNAL_TARGET_CONTRACT.md)
- contributing: [CONTRIBUTING.md](CONTRIBUTING.md)

## What Is In This Repo

This repository contains two closely related things:

- the product package under [products/evidpath](products/evidpath/README.md)
- the public proof and study under [studies/01-recommender-offline-eval](studies/01-recommender-offline-eval/README.md)

If you are here to use the product, start with the product guide. If you are
here to understand the original proof behind the direction, read the study.

## Public Proof

The study package shows the original argument behind Evidpath: offline ranking
metrics can miss important user-level tradeoffs.

Useful links:

- study README: [studies/01-recommender-offline-eval/README.md](studies/01-recommender-offline-eval/README.md)
- canonical report: [studies/01-recommender-offline-eval/artifacts/canonical/official_demo_report.md](studies/01-recommender-offline-eval/artifacts/canonical/official_demo_report.md)
- canonical JSON: [studies/01-recommender-offline-eval/artifacts/canonical/official_demo_results.json](studies/01-recommender-offline-eval/artifacts/canonical/official_demo_results.json)

![Offline versus bucket story](studies/01-recommender-offline-eval/artifacts/canonical/offline_vs_bucket_story.svg)

## Repo Guide

- product docs: [products/evidpath/README.md](products/evidpath/README.md)
- PyPI README: [products/evidpath/README_PYPI.md](products/evidpath/README_PYPI.md)
- plans: [plans/evidpath-v0/README.md](plans/evidpath-v0/README.md)
- code of conduct: [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md)
- security: [SECURITY.md](SECURITY.md)
- support: [SUPPORT.md](SUPPORT.md)

## Development

This repo uses `uv` as the Python project manager. The root is a virtual
workspace, and the publishable package lives in `products/evidpath`.

Install `uv`, then sync the default development environment:

```bash
uv sync
```

Common commands:

```bash
make lint
make test
make build
make check-dist
make ci
```

Run the package CLI from the workspace:

```bash
uv run evidpath --help
```

The Hugging Face example dependencies are intentionally opt-in because they are
large:

```bash
uv sync --group hf-example
```

Framework adapters for in-process audits are also optional package extras:
`evidpath[huggingface]`, `evidpath[mlflow]`, and `evidpath[sklearn]`.

## Background

The earlier public write-up that motivated this direction is here:

https://dev.to/alankritverma/why-offline-evaluation-is-not-enough-for-recommendation-systems-15ii
