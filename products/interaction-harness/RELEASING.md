# Releasing `interaction-harness`

This package now has a GitHub Actions release path for building and publishing
distributions.

## Workflows

- `interaction-harness-ci`
  - runs lint, tests, `python -m build`, and `twine check`
  - uploads the built wheel and sdist as a workflow artifact
- `interaction-harness-publish`
  - builds distributions in a dedicated job
  - publishes with PyPI Trusted Publishing
  - supports:
    - automatic publish when a GitHub Release is published
    - manual publish to TestPyPI or PyPI through `workflow_dispatch`

## Required one-time setup

Configure Trusted Publishers in both PyPI and TestPyPI for this repository and
workflow.

Use the workflow file:

- `.github/workflows/interaction-harness-publish.yml`

Recommended environments:

- `testpypi`
- `pypi`

## Manual dry run to TestPyPI

1. Bump the package version in `products/interaction-harness/pyproject.toml` if
   needed.
2. Run the `interaction-harness-publish` workflow manually.
3. Choose `testpypi` as the target repository.
4. Verify the package page, README rendering, and install flow from TestPyPI.

## Publish to PyPI

Option 1:

1. Create a GitHub Release.
2. The publish workflow will build and publish to PyPI automatically.

Option 2:

1. Run the `interaction-harness-publish` workflow manually.
2. Choose `pypi` as the target repository.

## Local release checks

From the repository root:

```bash
.venv/bin/python -m pip install -e products/interaction-harness[dev]
cd products/interaction-harness
python -m build
twine check dist/*
```

## Current release caveat

The automation path is in place, but the package should still be treated as
mid-release-readiness until the installed-wheel runtime story is fully honest
for the default reference/demo path.
