# Releasing `evidpath`

This package has a GitHub Actions release path for versioning, building, and
publishing distributions.

The intended flow on `main` is:

1. merge normal feature/fix/docs PRs into `main`
2. let `evidpath-release-please` create or update the release PR
3. review and merge the release PR when you are ready to ship
4. let the generated GitHub Release trigger `evidpath-publish`
5. verify the new package on PyPI

## Workflows

- `evidpath-ci`
  - runs lint, tests, `python -m build`, and `twine check`
  - uploads the built wheel and sdist as a workflow artifact
- `evidpath-publish`
  - builds distributions in a dedicated job
  - publishes with PyPI Trusted Publishing
  - supports:
    - automatic publish when a `v<version>` GitHub Release is published
    - manual publish to TestPyPI or PyPI through `workflow_dispatch`
- `evidpath-release-please`
  - runs on pushes to `main` that touch Evidpath release inputs
  - opens or updates a release PR for `products/evidpath`
  - updates `products/evidpath/pyproject.toml`, the release manifest, and
    `products/evidpath/CHANGELOG.md`
  - creates the GitHub Release after the release PR is merged

## Required one-time setup

Configure Trusted Publishers in both PyPI and TestPyPI for this repository and
workflow.

Use this workflow filename in the PyPI form:

- `evidpath-publish.yml`

Recommended environments:

- `testpypi`
- `pypi`

Because the repository moved accounts, make sure both PyPI projects trust:

- owner: `NDETERMINA`
- repository: `limitation`
- workflow: `evidpath-publish.yml`
- environments: `testpypi` and `pypi`

## Manual dry run to TestPyPI

1. Make sure CI is green on `main`.
2. Run the `evidpath-publish` workflow manually from `main`.
3. Choose `testpypi` as the target repository.
4. Verify the package page, README rendering, and install flow from TestPyPI.

TestPyPI is useful before the first real release from the new account. After
that, the normal release path is the release PR created by Release Please.

## Publish to PyPI

Normal flow:

1. Merge conventional commits into `main`, for example `feat: ...` or
   `fix: ...`.
2. Review the release PR opened by `evidpath-release-please`.
3. Merge the release PR.
4. The generated `v<version>` GitHub Release triggers PyPI publish
   automatically.

Manual fallback:

1. Run the `evidpath-publish` workflow manually.
2. Choose `pypi` as the target repository.

Manual PyPI dispatch publishes the version currently in
`products/evidpath/pyproject.toml`, so only use it when that version does not
already exist on PyPI.

## Local release checks

From the repository root:

```bash
.venv/bin/python -m pip install -e products/evidpath[dev]
cd products/evidpath
python -m build
twine check dist/*
```

## `gh`-native release flow

Run the release automation after commits have landed on `main`:

```bash
gh workflow run evidpath-release-please.yml --ref main
gh run list --workflow evidpath-release-please.yml
```

Dry-run TestPyPI from `main`:

```bash
gh workflow run evidpath-publish.yml --ref main -f repository=testpypi
gh run list --workflow evidpath-publish.yml
```

## Current release caveat

The automation path is in place, but the package should still be treated as
pre-release until all of the following are true:

- Python `3.11+` validation is green
- package metadata is complete
- the published README is PyPI-safe
- the external-target-first installed package path is validated from a clean install
