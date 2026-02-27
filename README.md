<h1 align="center">🐍 snake shed</h1>
<h3 align="center">An opinionated python development template</h3>
<p align="center">
  <a href="https://github.com/auchenberg/volkswagen/tree/master">
    <img alt="Don't worry, all tests are passing! Nothing to see here!" src="https://auchenberg.github.io/volkswagen/volkswagen_ci.svg?v=1">
  </a>
</p>

Ever felt setting up your python project was a chore? Well, not anymore!

This project is a small template that contains all necessary features you expect the perfect python repository to have.
Features include:

- Easy python environment handling
- Full config handling with yaml and env files 
- Strict code quality checks (some dare say even too strict!)
- Automated testing
- CI (gitlab, easily swappable)
- Enterprise-ready git workflow (conventional commits, semantic-release, pre-commit hooks)
- Build-in Makefile commands to simply all the above

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

```
make check            Run all checks (format, lint, type, docstring, test, audit)
make test             Run tests
make test-cov         Run tests with coverage
make lint-fix         Lint and auto-fix
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

Environment variables are loaded from `config/.env` by default.

## Commit Convention

This project uses [Conventional Commits](https://www.conventionalcommits.org/). Commitizen enforces the format via a pre-commit hook. Examples:

```
feat (autograd): added support for gradient accumulation
fix (config): added missing environment variable handling
docs (readme): update config section in README
```

Versioning is handled automatically by [python-semantic-release](https://python-semantic-release.readthedocs.io/) in CI.
