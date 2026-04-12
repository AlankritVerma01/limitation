# Evidpath

[![PyPI version](https://img.shields.io/pypi/v/evidpath.svg)](https://pypi.org/project/evidpath/)
[![Python versions](https://img.shields.io/pypi/pyversions/evidpath.svg)](https://pypi.org/project/evidpath/)
[![CI](https://github.com/AlankritVerma01/limitation/actions/workflows/evidpath-ci.yml/badge.svg)](https://github.com/AlankritVerma01/limitation/actions/workflows/evidpath-ci.yml)
[![License](https://img.shields.io/pypi/l/evidpath.svg)](https://github.com/AlankritVerma01/limitation/blob/main/products/evidpath/LICENSE)

[PyPI](https://pypi.org/project/evidpath/) |
[TestPyPI](https://test.pypi.org/project/evidpath/) |
[Releases](https://github.com/AlankritVerma01/limitation/releases) |
[Issues](https://github.com/AlankritVerma01/limitation/issues) |
[External target contract](./EXTERNAL_TARGET_CONTRACT.md)

Evidpath helps teams evaluate a recommender before launch. You point it at a
recommender endpoint, run a few commands, and get a report that shows what
happened, who struggled, and whether a candidate looks safer or riskier than a
baseline.

## What It Does

Evidpath is built for a simple job:

- check that your recommender endpoint responds in the expected shape
- run a repeatable audit against that endpoint
- save a report and machine-readable output
- compare a baseline and a candidate before launch

For `0.1.0`, the primary supported path is an external recommender endpoint.
The built-in reference target is still useful for demos, onboarding, and local
development, but it is not the main packaged-user path.

## Who It Is For

Evidpath is for teams that already have a recommender service and want a better
pre-launch check than a single offline metric or a few manual spot checks.

Typical users:

- ML teams reviewing a recommender change before rollout
- product teams that want a readable report, not just a raw score
- evaluation or platform teams that want saved evidence and repeatable compare runs

## Before You Start

You need:

- Python `3.11+`
- a recommender HTTP endpoint you want to test
- an endpoint that follows the request and response shape in
  [EXTERNAL_TARGET_CONTRACT.md](./EXTERNAL_TARGET_CONTRACT.md)

Install the package:

```bash
python -m pip install evidpath
```

You can also preview the latest package build from TestPyPI:

```bash
python -m pip install --index-url https://test.pypi.org/simple/ --extra-index-url https://pypi.org/simple evidpath
```

## 5-Minute Quickstart

Assume your recommender is running at `http://127.0.0.1:8051`.

### 1. Check the target

```bash
evidpath check-target --domain recommender --target-url http://127.0.0.1:8051
```

This is the fast preflight step. It helps you catch contract and connectivity
problems before a full run.

### 2. Run one audit

```bash
evidpath audit --domain recommender --target-url http://127.0.0.1:8051 --scenario returning-user-home-feed --seed 7
```

### 3. Open the output

By default, Evidpath writes to an `evidpath-output/` folder in your current
working directory. The most useful files in a single audit are:

- `report.md` for the human-readable summary
- `results.json` for structured output
- `traces.jsonl` for full trace-level detail

### 4. Compare two versions before launch

```bash
evidpath compare --domain recommender --baseline-url http://127.0.0.1:8051 --candidate-url http://127.0.0.1:8052 --baseline-label current-prod --candidate-label next-build --rerun-count 2
```

This writes a regression bundle with files such as:

- `regression_report.md`
- `regression_summary.json`
- nested `baseline/` and `candidate/` audit runs

## What You Get After A Run

A normal audit gives you evidence you can read and evidence you can process:

- a readable report that highlights the main concerns
- JSON output for automation or later analysis
- full traces if you need to inspect what happened step by step
- charts and summary files that are easy to share internally

A compare run adds:

- a clear baseline-vs-candidate summary
- a deterministic `pass`, `warn`, or `fail` decision
- the per-seed reruns used to produce that comparison

## Common Workflows

### Check One Target

```bash
evidpath check-target --domain recommender --target-url http://127.0.0.1:8051
```

Use this first whenever you are pointing Evidpath at a new service.

### Audit One Target

```bash
evidpath audit --domain recommender --target-url http://127.0.0.1:8051 --scenario returning-user-home-feed --seed 7 --output-dir ./audit-run
```

Use this when you want one concrete, inspectable run.

### Compare A Baseline And A Candidate

```bash
evidpath compare --domain recommender --baseline-url http://127.0.0.1:8051 --candidate-url http://127.0.0.1:8052 --baseline-label current-prod --candidate-label next-build --rerun-count 2 --output-dir ./compare-run
```

Use this when you are deciding whether a change is safe to ship.

### Start From A Plain-English Testing Goal

```bash
evidpath run-swarm --domain recommender --target-url http://127.0.0.1:8051 --brief "test trust collapse and weak first-slate behavior for impatient and exploratory users"
```

Use this when you want Evidpath to expand one testing goal into a broader saved
coverage bundle. This is powerful, but it is not the first command most users
need.

## Using Your Own Recommender

The main user path is an external HTTP target.

In practice that means:

- your team owns the recommender service
- Evidpath calls that service over HTTP
- the service returns recommendation slates and metadata in the documented shape

Most teams do not need to hand Evidpath their model files or training data.
They just need a reachable endpoint.

Start here if you want the exact contract:

- [EXTERNAL_TARGET_CONTRACT.md](./EXTERNAL_TARGET_CONTRACT.md)

If you want a local service that behaves like a customer-owned endpoint, use:

- [examples/recommender_http_service/README.md](./examples/recommender_http_service/README.md)
- [examples/hf_recommender_service/README.md](./examples/hf_recommender_service/README.md)

## Reference, Demo, And Mock Paths

Keep this mental model in mind:

- external target: the real user path
- reference target: the local demo and onboarding path
- mock target: narrow internal test/debug path

The local reference target is still useful when:

- you want a stable demo
- you are onboarding before your own endpoint is ready
- you want a repeatable local proof path

Start here for that:

- [DEMO.md](./DEMO.md)

## Provider Credentials

Most normal `check-target`, `audit`, and `compare` runs against an external
endpoint do not need an API key.

Provider credentials only matter when you use AI-backed generation or advisory
semantic interpretation.

Evidpath reads environment variables first, then looks for:

- `./.env`
- `~/.evidpath.env`
- the repo-root `.env` as a fallback for repo workflows

Common variables:

- `OPENAI_API_KEY`
- `OPENAI_BASE_URL`
- `OPENAI_TIMEOUT_SECONDS`
- `OPENAI_SCENARIO_TIMEOUT_SECONDS`
- `OPENAI_POPULATION_TIMEOUT_SECONDS`
- `OPENAI_SEMANTIC_TIMEOUT_SECONDS`
- `OPENAI_RETRY_COUNT`

Use [`products/evidpath/.env.example`](/Users/alankritverma/projects/limitation/products/evidpath/.env.example)
as the starting template.

## Advanced Workflows

These are useful after the basic check-target/audit/compare flow is clear.

### `run-swarm`

Starts from one plain-English testing brief and expands it into saved coverage
for a broader run.

### `plan-run` And `execute-plan`

If you want a saved plan before you execute, use:

```bash
evidpath plan-run --workflow audit --domain recommender --target-url http://127.0.0.1:8051 --scenario returning-user-home-feed --output-dir ./planned-audit
evidpath execute-plan --run-plan-path ./planned-audit/run_plan.json
```

This is helpful when you want review, approval, or reproducible handoff before
the actual run.

### Generation And Semantic Features

Evidpath can also:

- generate scenario packs
- generate population packs
- add advisory semantic explanations

These help expand coverage and explanation, but they do not replace the
deterministic scoring and compare outputs.

## Troubleshooting

If `check-target` fails:

- confirm the service is running
- confirm the base URL is correct
- confirm the endpoint matches the external target contract

If an audit runs but the output is not where you expect:

- pass `--output-dir` explicitly
- otherwise look for `./evidpath-output/` in your current working directory

If you are using provider-backed features and they fail:

- confirm `OPENAI_API_KEY` is set
- confirm your `.env` or `~/.evidpath.env` has the right values

## Package Layout

You do not need this section to get started, but it helps once you want to go
deeper.

- `src/evidpath/cli.py`
  - public CLI entrypoint
- `src/evidpath/cli_app/`
  - parser, handlers, progress, and CLI support code
- `src/evidpath/orchestration/`
  - shared run planning and execution support
- `src/evidpath/artifacts/`
  - saved run contracts and manifests
- `src/evidpath/reporting/`
  - markdown, JSON, and chart writers
- `src/evidpath/domains/recommender/`
  - recommender-specific runtime, judging, analysis, and example targets

## Development And Planning

- release instructions: [RELEASING.md](./RELEASING.md)
- roadmap: [../plans/evidpath-v0/README.md](../plans/evidpath-v0/README.md)
- contributing: [../../CONTRIBUTING.md](../../CONTRIBUTING.md)
- code of conduct: [../../CODE_OF_CONDUCT.md](../../CODE_OF_CONDUCT.md)
- security: [../../SECURITY.md](../../SECURITY.md)
- support: [../../SUPPORT.md](../../SUPPORT.md)
