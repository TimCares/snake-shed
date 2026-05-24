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
  <a href="https://docs.renovatebot.com/"><img src="https://img.shields.io/badge/renovate-enabled-1A1F6C?logo=renovatebot&logoColor=white" alt="Renovate"></a>
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
- Automated dependency updates via [Renovate](https://docs.renovatebot.com/) (uv, pre-commit hooks, container images, CI image pins)
- Built-in `Makefile` commands to simplify all of the above
- LLM-maintained [`wiki`](wiki/README.md) for easy (project) documentation
- A [`docs`](docs/) directory for usual documentation

**Disclaimer**: This template aims to serve a wide range of use cases, so you
should adjust it according to your requirements and taste. There is a lot to
take in — [`docs/REPO_SETUP.md`](docs/REPO_SETUP.md) walks through every
moving part, why it's there, and how to swap or remove it. (Feel free to
delete that file once you're done with it; `make bootstrap` will offer to
do it for you.)

## Prerequisites

Just [uv](https://docs.astral.sh/uv/getting-started/installation/)!

## Getting Started

Clone the template into a directory named after your project, then run a single command:

```bash
git clone <template-url> my-new-project
cd my-new-project
make bootstrap
```

On the **first run**, `make bootstrap` is interactive: it asks for a project
name (defaulting to the directory name), package name, description, and
author, then renames the placeholder layout (`src/my_project/` →
`src/<your_package>/`) and updates `pyproject.toml`, the README, and tests
accordingly. After that it installs the pinned Python, dependencies, and
pre-commit hooks. The rename script self-deletes when it's done, so
re-running `make bootstrap` later just re-installs the dev environment —
which is what you want.

For non-interactive use (CI, dotfiles, etc.) the rename step accepts a
`--yes` flag; see [`docs/REPO_SETUP.md`](docs/REPO_SETUP.md#bootstrap).

Finally, configure runtime env variables by copying
[`config/.env.dist`](config/.env.dist) to `config/.env` and filling in the values.

## Development

Run `make help` to see all available commands, grouped by category. The two
you'll use most:

```text
make check    Run the full local check suite — exactly what CI and
              pre-commit run. Read-only; never modifies files.
make fix      Run every auto-fixer (format + lint + repo hygiene).
              Run this locally before committing.
```

Pre-commit is intentionally **check-only** — it verifies but never modifies
files mid-commit. A failed commit means "run `make fix` and try again."
See [`docs/REPO_SETUP.md`](docs/REPO_SETUP.md#make-targets-check-vs-fix)
for the full check/fix breakdown.

## Project Structure

```text
src/
  my_project/             Your package (renamed by `make bootstrap` on first run)
    __main__.py           Entry point: `python -m my_project`
    __version__.py        Version (reads from pyproject.toml metadata)
    config/
      config.py           Pydantic configuration schemas
      config_loader.py    OmegaConf YAML loading + Pydantic validation
config/
  config.yaml             App config (env vars via OmegaConf interpolation)
  .env.dist               Environment variable template
docs/
  REPO_SETUP.md           Template internals & customization guide (safe to delete)
scripts/
  bootstrap_template.py   One-time template rename (deletes itself after first run)
  release.sh              python-semantic-release driver (called from CI)
tests/
Dockerfile                Hardened multi-stage image (removable via `make bootstrap`)
docker-compose.yaml       Hardened local-run compose (volume-mounted config)
.dockerignore             Build-context exclusions
wiki/
  index.md                Catalog of all wiki pages
  log.md                  Timeline of wiki activity
  inbox/                  Quick capture zone
  decisions/              Architecture Decision Records
  guides/                 How-tos and runbooks
  reference/              Architecture docs, specs, conventions
  journal/                Thoughts, observations, findings
  _templates/             Document templates
```

The `src/my_project/` layout is the standard PyPA-recommended *src layout*.
As the project grows, add subpackages directly under it (e.g.
`src/my_project/core/`, `src/my_project/api/`) rather than dumping modules at
the top level. No `pyproject.toml` change needed — see
[`docs/REPO_SETUP.md`](docs/REPO_SETUP.md#layout) for the full rationale.

## Configuration

Configuration is defined in [`config/config.yaml`](config/config.yaml) using OmegaConf's `${oc.env:VAR}` syntax to resolve environment variables. Values are validated at startup through Pydantic models in [`src/my_project/config/config.py`](src/my_project/config/config.py).

Environment variables are loaded from `config/.env` by default.
Missing default `.env` files are ignored, while an explicitly provided path to an env file (`env_file`) must point to a valid file.

## Wiki

The [`wiki/`](wiki/) directory is an LLM-maintained project wiki (inspired by Andrej Karpathy) for capturing decisions, guides, and reference material. The LLM handles all the bookkeeping — metadata, cross-references, index updates — so writing docs doesn't feel like a chore. Tell the LLM to "capture this", "document why we chose X", or "lint the wiki". See [`wiki/README.md`](wiki/README.md) for details.

## Commit Convention

This project uses [Conventional Commits](https://www.conventionalcommits.org/). Commitizen enforces the format via a pre-commit hook. Examples:

```text
feat (autograd): added support for gradient accumulation
fix (config): added missing environment variable handling
docs (readme): update config section in README
```

Versioning is handled automatically by [python-semantic-release](https://python-semantic-release.readthedocs.io/) in CI.
