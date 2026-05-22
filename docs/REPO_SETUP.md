# Repo Setup Guide

This document is the long-form companion to the [README](../README.md). It
explains what every moving part of the template is, why it's there, and how
to customize or remove it. Once you've finished setting up your project you
can safely delete this file — `make bootstrap` offers to do that for you on
its first run.

---

## Bootstrap

The template ships with a one-time initialization script,
[`scripts/bootstrap_template.py`](../scripts/bootstrap_template.py), which is
invoked automatically by `make bootstrap` on the very first run. It:

1. **Infers defaults** from the current directory name and your local
   `git config user.{name,email}`. You can override every value at the prompt.
2. **Renames the placeholder package** `src/my_project/` to
   `src/<your_package>/`.
3. **Rewrites placeholders** in `pyproject.toml` (`[project].name`,
   `description`, `authors`, `[tool.uv.build-backend].module-name`),
   `src/<your_package>/__version__.py`, the `README.md`, and any
   `from my_project...` imports under `tests/`.
4. **Deletes `uv.lock`** so the next `uv sync` regenerates it under the new
   project name.
5. **Offers to delete this file** (`docs/REPO_SETUP.md`), since it's
   template-specific and probably isn't useful to keep around in a real
   project.
6. **Optionally resets git history** — wipes `.git/` and creates a fresh
   repo with a single initial commit, so your project doesn't carry the
   template's commit history. Prompted interactively (default Yes); skipped
   under `--yes` unless `--reset-git` is passed explicitly.

The script then self-deletes (and removes the `scripts/` directory if it's
empty). Re-running `make bootstrap` later just re-installs the dev
environment — there's no template state left to migrate.

### Non-interactive use

For CI, dotfiles, or anywhere you can't answer prompts:

```bash
uv run --no-project --script scripts/bootstrap_template.py --yes
uv run --no-project --script scripts/bootstrap_template.py --yes --reset-git
uv run --no-project --script scripts/bootstrap_template.py --no-reset-git
```

`--yes` accepts every inferred default; `--reset-git` / `--no-reset-git`
override the git-reset decision regardless of mode. You can preview what
would change by running `--yes` against a fresh clone in a throwaway
directory.

### Reverting

If you opted *out* of the git history reset, you can roll back the template
init with `git reset --hard HEAD` (or by re-cloning). If you opted *in*,
the original template history is gone — you'd need to re-clone. The
`make teardown` target only removes the *environment* (venv, pre-commit
hook, pinned Python); it does not undo the template rename.

---

## Layout

The template uses the standard [PyPA "src layout"](https://packaging.python.org/en/latest/discussions/src-layout-vs-flat-layout/):

```text
src/
  my_project/         ← renamed by bootstrap
    __init__.py
    __version__.py
    config/
      ...
```

The `[tool.uv.build-backend]` block in `pyproject.toml` is configured
accordingly:

```toml
[tool.uv.build-backend]
module-name = "my_project"
module-root = "src"
```

**Why src layout?** The package can only be imported after install, which
catches missing-file bugs in the wheel that a flat layout silently hides.
It's also the convention every modern Python tutorial and library expects.

**How to grow it.** Adding subpackages is purely additive — no
`pyproject.toml` change needed. A common pattern as a project grows:

```text
src/my_project/
  core/         domain logic, framework-agnostic
  api/          HTTP / CLI entry points
  config/       configuration loading & schemas
  infra/        I/O, DB, external services
```

The tooling configs (`[tool.ruff]`, `[tool.coverage.run]`,
`[tool.interrogate]`, `[tool.pytest.ini_options]`) all reference the `src/`
*directory*, not the package name, so they keep working unchanged when you
add or rearrange subpackages.

---

## Tooling Overview

A whirlwind tour of every tool wired into the template, why it's here, and
the `make` target that drives it.

| Concern        | Tool                          | `make` target          | Config location                          |
| -------------- | ----------------------------- | ---------------------- | ---------------------------------------- |
| Env / deps     | [uv](https://docs.astral.sh/uv/) | `install`, `install-dev`, `bootstrap`, `teardown` | `pyproject.toml`, `uv.lock`, `.python-version` |
| Lint           | [ruff](https://docs.astral.sh/ruff/) | `lint`, `lint-check`   | `[tool.ruff]` in `pyproject.toml`        |
| Format         | ruff format                   | `format`, `format-check` | `[tool.ruff.format]`                     |
| Type check     | [ty](https://docs.astral.sh/ty/) | `type-check`           | `[tool.ty]`                              |
| Docstring cov. | [interrogate](https://github.com/econchick/interrogate) | `docstring-check` | `[tool.interrogate]`                     |
| Tests          | [pytest](https://docs.pytest.org/) + `pytest-cov` | `test`, `test-cov` | `[tool.pytest.ini_options]`, `[tool.coverage.*]` |
| Dep audit      | [pip-audit](https://pypi.org/project/pip-audit/) | `audit`                | `PIP_AUDIT_IGNORE` in `Makefile`         |
| Secret scan    | [gitleaks](https://github.com/gitleaks/gitleaks) | `find-secrets`         | `.gitleaks.toml`                         |
| Image scan     | [trivy](https://github.com/aquasecurity/trivy) | `trivy`                | `trivy.yaml`                             |
| Pre-commit     | [pre-commit](https://pre-commit.com/) | `pre-commit-install`   | `.pre-commit-config.yaml`                |
| Commit style   | [commitizen](https://commitizen-tools.github.io/commitizen/) | (commit-msg hook) | `[tool.commitizen]`                      |
| Releases       | [python-semantic-release](https://python-semantic-release.readthedocs.io/) | (CI) | `[tool.semantic_release]`                |
| CI             | GitLab CI                     | (CI)                   | `.gitlab-ci.yml`, `.gitlab/ci/*.yml`     |

`make check` runs the full local validation suite (everything except `trivy`,
which is omitted from the default loop because it downloads a large
vulnerability DB on every run).

---

## Customization

### Loosen the lint rules

`[tool.ruff.lint].select` is intentionally broad. To drop a rule family
(say, `D` for docstrings if you're prototyping) add it to the `ignore` list
or remove the code from `select`.

### Lower the coverage / docstring bars

Edit `fail_under` in `[tool.coverage.report]` and `[tool.interrogate]`.

### Switch CI provider

The template ships with GitLab CI (`.gitlab-ci.yml` + `.gitlab/ci/*.yml`)
and `[tool.semantic_release.remote].type = "gitlab"`. For GitHub:

1. Replace `.gitlab*` with a `.github/workflows/` directory that runs
   `make check` on push/PR.
2. Set `[tool.semantic_release.remote].type = "github"`.

---

## What `make teardown` actually does

`teardown` is the inverse of `bootstrap`'s *environment* setup only:

1. Uninstalls the pre-commit hook (`pre-commit uninstall`).
2. Removes caches and the virtualenv (`make clean-all`).
3. Uninstalls the pinned Python toolchain (`uv python uninstall`).

It deliberately does **not** revert the one-time template rename — by the
time you'd want that, the rename script is gone. Use `git reset --hard` or
a fresh clone for that.

The target is highlighted in red in `make help` because it touches things
outside the repo (the uv-managed Python install). It is safe to run, but
re-running `bootstrap` afterwards will re-download Python.
