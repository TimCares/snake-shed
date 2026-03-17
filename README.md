<h1 align="center">🐍 snake shed</h1>
<h3 align="center">An opinionated python development template</h3>
Setting up a new Python project should not require rebuilding the same tooling every time.

`snake-shed` is a compact project template with the batteries already included. Features include:

- Easy python environment handling
- Full config handling with YAML and env files
- Strict code quality checks (some dare say even too strict!)
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
