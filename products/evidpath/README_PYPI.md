# Evidpath

[Source](https://github.com/AlankritVerma01/limitation) |
[Releases](https://github.com/AlankritVerma01/limitation/releases) |
[Issues](https://github.com/AlankritVerma01/limitation/issues) |
[TestPyPI](https://test.pypi.org/project/evidpath/)

Evidpath is a deterministic interaction-testing CLI for auditing recommender
systems through seeded users, trace-based judging, and reproducible regression
workflows.

## What It Does

Evidpath helps teams evaluate recommender behavior through short interaction
trajectories instead of relying only on offline ranking metrics.

For `0.1.0`, the primary supported installed-package path is:

- install `evidpath`
- point it at an external recommender endpoint
- run `check-target`, `audit`, `compare`, or `run-swarm`

The in-repo reference/demo path remains available for repository workflows, CI,
and product demos, but it is not the primary packaged-user promise for the
first public release.

## Install

```bash
python -m pip install evidpath
```

Requirements:

- Python `3.11+`

## Quick Start

Validate an external target:

```bash
evidpath check-target --domain recommender --target-url http://127.0.0.1:8051
```

Run one audit against an external target:

```bash
evidpath audit --domain recommender --target-url http://127.0.0.1:8051 --scenario returning-user-home-feed --seed 7
```

Run a compare workflow across two external targets:

```bash
evidpath compare --domain recommender --baseline-url http://127.0.0.1:8051 --candidate-url http://127.0.0.1:8052 --rerun-count 2
```

Run the brief-driven swarm workflow:

```bash
evidpath run-swarm --domain recommender --target-url http://127.0.0.1:8051 --brief "test trust collapse and weak first-slate behavior"
```

## Product Model

- external target = the real customer integration path
- reference target = repo/demo/dev infrastructure
- mock target = internal-only fixture/debug path

## Provider Credentials

AI-backed generation and planning only need provider credentials when you use
provider mode. Evidpath reads existing environment variables first, then a
local `.env`, then `~/.evidpath.env`.

Common variables:

- `OPENAI_API_KEY`
- `OPENAI_BASE_URL`
- `OPENAI_TIMEOUT_SECONDS`
- `OPENAI_SCENARIO_TIMEOUT_SECONDS`
- `OPENAI_POPULATION_TIMEOUT_SECONDS`
- `OPENAI_SEMANTIC_TIMEOUT_SECONDS`
- `OPENAI_RETRY_COUNT`

## Links

- Source: https://github.com/AlankritVerma01/limitation
- Releases: https://github.com/AlankritVerma01/limitation/releases
- Product docs: https://github.com/AlankritVerma01/limitation/tree/main/products/evidpath
- External target contract: https://github.com/AlankritVerma01/limitation/blob/main/products/evidpath/EXTERNAL_TARGET_CONTRACT.md
- Issues: https://github.com/AlankritVerma01/limitation/issues
