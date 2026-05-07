# Contributing

Thanks for contributing to Evidpath.

## Before You Start

- Open an issue or discussion for significant changes before starting large work.
- Keep changes focused. Smaller PRs are much easier to review and release.
- Preserve the public package contract for `evidpath` unless the change is intentionally breaking.

## Local Setup

```bash
uv sync
```

## Common Checks

Run these before opening a PR:

```bash
make lint
make test
make build
make check-dist
make smoke-package
```

## Pull Requests

- Describe the user-visible change clearly.
- Include verification notes in the PR body.
- Update docs when CLI behavior, release flow, or package metadata changes.
- Prefer adding or updating tests when behavior changes.

## Release Notes

- Package releases happen from `main`.
- TestPyPI is the rehearsal environment.
- PyPI is the real public release target.
