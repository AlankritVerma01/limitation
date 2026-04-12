# Releasing `evidpath`

This package now has a GitHub Actions release path for building and publishing
distributions.

The intended flow for the first public release is:

1. finish release work on `v1`
2. open and merge a PR from `v1` into `main`
3. dry-run TestPyPI from `main`
4. create the GitHub Release from `main`
5. let `evidpath-publish` ship to PyPI

## Workflows

- `evidpath-ci`
  - runs lint, tests, `python -m build`, and `twine check`
  - uploads the built wheel and sdist as a workflow artifact
- `evidpath-publish`
  - builds distributions in a dedicated job
  - publishes with PyPI Trusted Publishing
  - supports:
    - automatic publish when a GitHub Release is published
    - manual publish to TestPyPI or PyPI through `workflow_dispatch`

## Required one-time setup

Configure Trusted Publishers in both PyPI and TestPyPI for this repository and
workflow.

Use the workflow file:

- `.github/workflows/evidpath-publish.yml`

Recommended environments:

- `testpypi`
- `pypi`

## Manual dry run to TestPyPI

1. Bump the package version in `products/evidpath/pyproject.toml` if
   needed.
2. Push the release branch and open a PR into `main`.
3. Merge into `main` after CI is green.
4. Run the `evidpath-publish` workflow manually from `main`.
5. Choose `testpypi` as the target repository.
6. Verify the package page, README rendering, and install flow from TestPyPI.

## Publish to PyPI

Option 1:

1. Create a GitHub Release from `main`.
2. The publish workflow will build and publish to PyPI automatically.

Option 2:

1. Run the `evidpath-publish` workflow manually.
2. Choose `pypi` as the target repository.

## Local release checks

From the repository root:

```bash
.venv/bin/python -m pip install -e products/evidpath[dev]
cd products/evidpath
python -m build
twine check dist/*
```

## `gh`-native branch and release flow

Create or update the PR from `v1` to `main`:

```bash
git push origin v1
gh pr create --base main --head v1 --fill
gh pr status
gh pr checks
```

Dry-run TestPyPI from `main` after the PR is merged:

```bash
gh workflow run evidpath-publish.yml --ref main -f repository=testpypi
gh run list --workflow evidpath-publish.yml
```

Create the public release from `main` after TestPyPI verification:

```bash
gh release create v0.1.0 --target main --generate-notes
```

## Current release caveat

The automation path is in place, but the package should still be treated as
pre-release until all of the following are true:

- Python `3.11+` validation is green
- package metadata is complete
- the published README is PyPI-safe
- the external-target-first installed package path is validated from a clean install
