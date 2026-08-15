# Contributing to EgoFlow Python Client

Thank you for helping improve EgoFlow Python Client.

## Pull Requests

1. Fork the repository and create a focused branch from `main`.
2. Add or update tests for behavior changes.
3. Update public documentation when an API or supported workflow changes.
4. Run the test, lint, type-check, and package-build commands below.
5. Open a pull request that explains the user-visible effect of the change.

Keep pull requests scoped to one logical change. Do not commit credentials, local caches, virtual
environments, build output, or generated package artifacts.

## Development Checks

```bash
python3.12 -m venv .venv
. .venv/bin/activate
python -m pip install -e ".[test,release]" ruff mypy
python -m pytest
python -m ruff check src tests
python -m mypy src
python -m build
python -m twine check dist/*
```

The supported Python versions are documented in `pyproject.toml`. Changes that affect the EgoFlow
Server contract should remain compatible with the server release named in `README.md` or document
the required version change.

## Automated Gates

`.github/workflows/ci.yml` runs the test, Ruff, Mypy, build, and Twine checks on `main` and
`v0.0.1`. It also performs a checksum-verified Gitleaks scan, deterministically recreates and
validates the package-level CycloneDX 1.6 SBOM, checks DCO sign-offs, and reviews new pull-request
dependencies for high-severity advisories and restricted licenses. An intentional fake credential
fixture may use `gitleaks:allow` only on the exact fixture line with a reason; broader suppressions
require a security review.

## Reporting Issues

Use [GitHub Issues](https://github.com/ego-flow/ego-flow-py/issues) for reproducible bugs and feature
requests. Do not include Python tokens, server credentials, private repository names, or sensitive
dataset contents in public reports.

Report conduct concerns through the private contact in `CODE_OF_CONDUCT.md`.

## License

By contributing to this project, you agree that your contributions will be licensed under the
[MIT License](LICENSE) in the root of this repository.
