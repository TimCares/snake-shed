<h1 align="center">[Project Name]</h1>
<h3 align="center">Your project description</h3>

<p align="center">
  <a href="https://docs.astral.sh/uv/"><img src="https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/uv/main/assets/badge/v0.json" alt="uv"></a>
  <a href="https://www.python.org/"><img src="https://img.shields.io/badge/python-3.13-3776AB?logo=python&logoColor=white" alt="Python 3.13"></a>
  <a href="https://docs.astral.sh/ruff/"><img src="https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json" alt="Ruff"></a>
  <a href="https://docs.astral.sh/ty/"><img src="https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ty/main/assets/badge/v0.json" alt="ty"></a>
  <a href="https://github.com/econchick/interrogate"><img src="https://interrogate.readthedocs.io/en/latest/_static/interrogate_badge.svg" alt="interrogate"></a>
  <a href="https://docs.pytest.org/"><img src="https://img.shields.io/badge/tests-pytest-0A9EDC?logo=pytest&logoColor=white" alt="pytest"></a>
  <a href="https://img.shields.io/badge/coverage-≥80%25-brightgreen"><img src="https://img.shields.io/badge/coverage-%E2%89%A580%25-brightgreen" alt="coverage ≥80%"></a>
  <a href="https://pre-commit.com/"><img src="https://img.shields.io/badge/pre--commit-enabled-brightgreen?logo=pre-commit&logoColor=white" alt="pre-commit"></a>
  <a href="https://www.conventionalcommits.org/"><img src="https://img.shields.io/badge/Conventional%20Commits-1.0.0-FE5196?logo=conventionalcommits&logoColor=white" alt="Conventional Commits"></a>
  <a href="https://python-semantic-release.readthedocs.io/"><img src="https://img.shields.io/badge/semantic--release-python-e10079?logo=semantic-release" alt="semantic-release"></a>
  <a href="https://pypi.org/project/pip-audit/"><img src="https://img.shields.io/badge/pip--audit-checked-brightgreen" alt="pip-audit"></a>
  <a href="https://github.com/gitleaks/gitleaks"><img src="https://img.shields.io/badge/gitleaks-protected-4B0082" alt="Gitleaks"></a>
  <a href="https://github.com/aquasecurity/trivy"><img src="https://img.shields.io/badge/trivy-scanned-1904DA?logo=aquasecurity&logoColor=white" alt="Trivy"></a>
</p>

Setting up a new Python project should not require rebuilding the same tooling every time.

This project is a compact template with all the components already included. Features include:

- Easy python environment handling
- Full config handling with YAML and env files
- Strict code quality checks (some dare say even too strict!)
- Security scanning
- Automated testing
- CI (`gitlab`, easily swappable)
- Enterprise-ready git workflow (conventional commits, semantic-release, pre-commit hooks)
- Built-in `Makefile` commands to simplify all of the above

## Prerequisites

Just [uv](https://docs.astral.sh/uv/getting-started/installation/)!

## Getting Started

```bash
make bootstrap
make pre-commit-install
```

Make sure to configure the runtime env variables by copying `config/.env.dist` to `config/.env` and filling in the values.

## Development

Run `make help` to see all available commands. Key ones:

```text
make check            Run the full local validation suite
make test             Run tests
make test-cov         Run tests with coverage
make lint             Lint and auto-fix
make format           Format code
```

## Project Structure

```
src/
  __version__.py        Version (reads from pyproject.toml metadata)
  config.py             Pydantic configuration schemas
  config_loader.py      OmegaConf YAML loading + Pydantic validation
config/
  config.yaml           App config (env vars via OmegaConf interpolation)
  .env.dist             Environment variable template
tests/
```

## Configuration

Configuration is defined in `config/config.yaml` using OmegaConf's `${oc.env:VAR}` syntax to resolve environment variables. Values are validated at startup through Pydantic models in `src/config.py`.

Environment variables are loaded from `config/.env` by default. Missing default `.env` files are ignored, while an explicitly provided `env_file` must exist.

## Commit Convention

This project uses [Conventional Commits](https://www.conventionalcommits.org/). Commitizen enforces the format via a pre-commit hook. Examples:

```
feat (autograd): added support for gradient accumulation
fix (config): added missing environment variable handling
docs (readme): update config section in README
```

Versioning is handled automatically by [python-semantic-release](https://python-semantic-release.readthedocs.io/) in CI.
