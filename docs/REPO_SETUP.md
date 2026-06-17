# Repo Setup Guide

This document is the long-form companion to the [README](../README.md). It
explains what every moving part of the template is, why it's there, and how
to customize or remove it. Once you've finished setting up your project you
can safely delete this file. `make bootstrap` offers to do that for you on
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
   `src/<your_package>/__version__.py`, the `README.md`, any
   `from my_project...` imports under `tests/`, and the `Dockerfile`,
   `docker-compose.yaml`, and `.gitlab/ci/docker.yml`.
4. **Deletes `uv.lock`** so the next `uv sync` regenerates it under the new
   project name.
5. **Offers to delete this file** (`docs/REPO_SETUP.md`), since it's
   template-specific and probably isn't useful to keep around in a real
   project.
6. **Optionally resets git history** — wipes `.git/` and creates a fresh
   repo with a single initial commit, so your project doesn't carry the
   template's commit history. Prompted interactively (default Yes); skipped
   under `--yes` unless `--reset-git` is passed explicitly.

Docker support is always kept on bootstrap. If your project genuinely has
no use for it, follow the [manual-removal recipe](#removing-docker-support)
below — it's a handful of `git rm` calls plus a couple of small edits.

The script then self-deletes. The surrounding `scripts/` directory stays
(it hosts other permanent project scripts).
Re-running `make bootstrap` later just re-installs the dev environment,
there's no template state left to migrate.

### Non-interactive use

For CI, dotfiles, or anywhere you can't answer prompts:

```bash
uv run --no-project --script scripts/bootstrap_template.py --yes
uv run --no-project --script scripts/bootstrap_template.py --yes --reset-git
uv run --no-project --script scripts/bootstrap_template.py --no-reset-git
```

`--yes` accepts every inferred default (no git reset). `--reset-git` /
`--no-reset-git` overrides that decision regardless of mode. You can
preview what would change by running `--yes` against a fresh clone in a
throwaway directory.

### Reverting

If you opted *out* of the git history reset, you can roll back the template
init with `git reset --hard HEAD` (or by re-cloning). If you opted *in*,
the original template history is gone — you'd need to re-clone. The
`make teardown` target only removes the *environment* (venv, pre-commit
hook, pinned Python); it does not undo the template rename.

---

## Pipeline Variables

In order for GitLab Pipelines to run correctly, you will need the following Pipeline Variables:

### Docker
- CI_REGISTRY -> URL of your docker registry (e.g. docker-registry.my-company.com)
- CI_REGISTRY_USER -> (robot user for docker-registry.my-company.com)
- CI_REGISTRY_PASSWORD -> (robot user password for docker-registry.my-company.com)

### Semantic Release
Uses `CI_JOB_TOKEN`. If this is not allowed in the project, create a repository access token with `api` permissions
and save it as a pipeline variable with the name `GITLAB_TOKEN`.
 
### Renovate (see [here](#renovate-automated-dependency-updates) for more)

- `RENOVATE_TOKEN` -> repository access token with `api` and
  `write_repository` permissions

If your GitLab instance does not allow `CI_JOB_TOKEN` to push release commits
and tags, create a project access token and adjust
[`.gitlab/ci/release.yml`](../.gitlab/ci/release.yml) to use it.

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

## Make targets: check vs. fix

`make help` groups targets into **Setup**, **Check**, **Fix**, **Other**,
and **Danger** sections so it's obvious what each command does.

The split that matters day-to-day:

- **Check** targets are read-only — they verify but never modify files.
  `make check` aggregates them all. CI runs the individual check targets;
  pre-commit runs them on every commit. Whatever passes `make check`
  passes CI.
- **Fix** targets modify files. `make fix` runs every auto-fixer in the
  project (`format` + `lint` + `repo-fix`). Run it locally before
  committing; it is never invoked by pre-commit or CI.

`repo-fix` is the auto-fix counterpart of `repo-check` — it runs the
`trailing-whitespace` and `end-of-file-fixer` pre-commit hooks across all
files. These hooks are intentionally absent from `.pre-commit-config.yaml`
(they have no check-only mode and would silently modify files at commit
time); call `make repo-fix` when you want them.

## Tooling Overview

A whirlwind tour of every tool wired into the template, why it's here, and
the `make` target(s) that drive it.

| Concern        | Tool                          | `make` target(s)                  | Config location                          |
| -------------- | ----------------------------- | --------------------------------- | ---------------------------------------- |
| Env / deps     | [uv](https://docs.astral.sh/uv/) | `install`, `install-dev`, `bootstrap`, `teardown` | `pyproject.toml`, `uv.lock`, `.python-version` |
| Lint           | [ruff](https://docs.astral.sh/ruff/) | `lint-check` / `lint`             | `[tool.ruff]` in `pyproject.toml`        |
| Format         | ruff format                   | `format-check` / `format`         | `[tool.ruff.format]`                     |
| Pre-Commit     | pre-commit-hooks              | `repo-check` / `repo-fix`         | `.pre-commit-config.yaml`                |
| Type check     | [ty](https://docs.astral.sh/ty/) | `type-check`                      | `[tool.ty]`                              |
| Docstring cov. | [interrogate](https://github.com/econchick/interrogate) | `docstring-check`                 | `[tool.interrogate]`                     |
| Spell check    | [codespell](https://github.com/codespell-project/codespell) | `spell-check`                     | `[tool.codespell]` in `pyproject.toml` (optional) |
| Shell lint     | [shellcheck](https://www.shellcheck.net/) (via `shellcheck-py`) | `shell-check`                     | (none; defaults)                         |
| Dockerfile lint| [hadolint](https://github.com/hadolint/hadolint) (via Docker) | `dockerfile-check`                | `.hadolint.yaml` (optional)              |
| Tests          | [pytest](https://docs.pytest.org/) + `pytest-cov` | `test`, `test-cov`                | `[tool.pytest.ini_options]`, `[tool.coverage.*]` |
| Dep audit      | [py-audit](https://pypi.org/project/py-audit/) | `audit`                           | suppressions from `openvex.json` via `scripts/py_audit_ignores_from_vex.py` |
| Secret scan    | [gitleaks](https://github.com/gitleaks/gitleaks) | `find-secrets`                    | `.gitleaks.toml`                         |
| Vuln scan      | [trivy](https://github.com/aquasecurity/trivy) (fs + image) | `trivy`, `trivy-full`, `trivy-image`, `sbom` | `trivy.yaml`, `openvex.json` |
| Sec. policy    | `SECURITY.md` + `CODEOWNERS`  | (reviewer-gated)                  | `SECURITY.md`, `CODEOWNERS`  |
| Pre-commit     | [pre-commit](https://pre-commit.com/) | `pre-commit-install`              | `.pre-commit-config.yaml`                |
| Commit style   | [commitizen](https://commitizen-tools.github.io/commitizen/) | (commit-msg hook)                 | `[tool.commitizen]`                      |
| Releases       | [python-semantic-release](https://python-semantic-release.readthedocs.io/) | `make release`, `.gitlab/ci/release.yml` | `[tool.semantic_release]`                |
| CI             | GitLab CI                     | (CI)                              | `.gitlab-ci.yml`, `.gitlab/ci/*.yml`     |
| Container      | Docker (multi-stage)          | (CI builds on release; locally: `docker buildx build` or `docker compose up -d --build`) | `Dockerfile`, `.dockerignore`, `docker-compose.yaml`, `.gitlab/ci/docker.yml` |
| Dep updates    | [Renovate](https://docs.renovatebot.com/) (self-hosted in GitLab CI) | (scheduled CI)                    | `renovate.json`, `.gitlab/ci/renovate.yml` |

`make check` runs the full local check suite. Two targets are intentionally
excluded: `trivy` (slow; downloads a large vulnerability DB) and
`dockerfile-check` (requires a running Docker daemon — pre-commit's
`hadolint-docker` hook already covers it on Dockerfile changes). Both remain
available as standalone targets. `make fix` runs every auto-fixer.

### Pre-commit is check-only

Pre-commit hooks here only **verify**, never modify files. That means a
failed pre-commit run is always actionable: run `make fix` (or the relevant
sub-target), re-stage, and commit again. The trade-off is that you must
remember to run `make fix` yourself — no silent rewrites mid-commit.

The hook config installs three stages (`default_install_hook_types`):

- **`pre-commit`** — the per-tool checks above, run on staged files. Fast
  and granular: you see exactly which tool failed.
- **`commit-msg`** — commitizen enforces Conventional Commits format.
- **`pre-push`** — runs the full `make check` aggregate once before code
  leaves your machine. This is the same suite CI runs, so a green push
  guarantees a green CI quality stage. It's also the safety net against
  drift between the per-tool hooks and the CI aggregate: any check added to
  `make check` is automatically gated at push-time without touching
  `.pre-commit-config.yaml`.

---

## Customization

### Loosen the lint rules

`[tool.ruff.lint].select` is intentionally broad. To drop a rule family
(say, `D` for docstrings if you're prototyping) add it to the `ignore` list
or remove the code from `select`.

### Lower the coverage / docstring bars

**Recommended:** Edit `fail_under` in `[tool.coverage.report]` and `[tool.interrogate]` (currently 0).

### Switch CI provider

The template ships with GitLab CI (`.gitlab-ci.yml` + `.gitlab/ci/*.yml`)
and `[tool.semantic_release.remote].type = "gitlab"`. For GitHub:

1. Replace `.gitlab*` with a `.github/workflows/` directory that runs
   `make check` on push/PR.
2. Set `[tool.semantic_release.remote].type = "github"`.

### Removing Docker support

The template always ships a Dockerfile, compose file, CI build job, and a
hadolint pre-commit hook. Most projects benefit from keeping them — even
pure libraries get value from a Dockerfile as a reproducible test/demo
environment. If you genuinely don't want any of it, run the four edits
below; together they take under a minute.

1. **Delete the files:**

   ```bash
   git rm Dockerfile .dockerignore docker-compose.yaml \
          .gitlab/ci/docker.yml .gitlab/ci/image-scan.yml
   ```

2. **Drop the `docker` stage** in `.gitlab/ci/base.yml`:

   ```diff
    stages:
      - quality
      - test
      - security
      - release
   -  - docker
      - maintenance
   ```

3. **Remove the hadolint hook** from `.pre-commit-config.yaml` (the entire
   `- repo: https://github.com/hadolint/hadolint` block and any preceding
   comment lines that describe it).

4. **Remove the `dockerfile-check` target** from `Makefile` (the `.PHONY:
   dockerfile-check` line, the recipe, and its leading comment block).
   Also collapse the `make check` aggregate comment back to a single
   `# Excludes trivy because it downloads a large vulnerability DB on
   every run.` since `dockerfile-check` is no longer there to exclude.

Optionally, if still present, also drop the **Container** and **Dockerfile lint** rows from
the Tooling Overview table further up this document.

Finally, prune the now-orphaned **trivy-image** parts from the Tooling Overview table.

---

## Renovate (automated dependency updates)

The template ships a self-hosted Renovate runner. The actual update policy
(grouping, scheduling, lockfile maintenance, security alerts) lives in
[`renovate.json`](../renovate.json); the GitLab CI wiring lives in
[`.gitlab/ci/renovate.yml`](../.gitlab/ci/renovate.yml).

**Activation (one-time):**

1. **Create a token.** Settings → Access Tokens → *Project Access Token*
   (or use a group/personal token if you prefer). Scopes: `api` +
   `write_repository`. Role: Developer or higher.
2. **Expose the token to CI.** Settings → CI/CD → Variables → add
   `RENOVATE_TOKEN`. Mark it **masked** and **protected**.
3. If "Work items" (also known as "Issues") are not activated in the project, do:
  `Project → Settings → General → Visibility, project features, permissions → Work items → Activate (flip the switch) → Scroll down and "Save changes"`
4. **Schedule the pipeline.** Build → Pipeline schedules → New schedule:
   - Description: `Renovate`
   - Interval pattern: e.g. `0 2 * * 1` (Mondays 02:00 UTC)
   - Target branch: your default branch
   - Variables: `RENOVATE` = `true`

That's it. The next scheduled run opens a "Configure Renovate" MR (or, if
onboarding is disabled in `renovate.json` as it is here, goes straight to
opening dependency MRs). Subsequent runs maintain a single
*Dependency Dashboard* issue listing every pending update.

**Why a `RENOVATE=true` variable?** It lets Renovate share the same
pipeline schedule mechanism as everything else without firing the regular
`quality` / `test` / `security` / `release` / `docker` jobs in the same
run. Each of those jobs has a `rules: - if: '$RENOVATE == "true"' when: never`
guard (inherited from `.uv-base` where possible). If you ever add another
scheduled job, give it its own opt-in variable rather than reusing this one.

**What Renovate manages here:**

- `pyproject.toml` runtime + dev dependencies (`pep621` manager) — only
  the **lockfile** is updated by default (`rangeStrategy: update-lockfile`),
  so your `>=X.Y.Z` floor doesn't creep up unnecessarily. Switch to
  `bump` if this is an application rather than a library.
- `uv.lock` weekly via `lockFileMaintenance` (keeps transitive deps fresh
  even when nothing in `pyproject.toml` changed).
- `.pre-commit-config.yaml` hook `rev:` pins (`pre-commit` manager).
- `Dockerfile` and `docker-compose.yaml` base images.
- `.gitlab/ci/*.yml` job `image:` references.

Pre-commit hook revs, ruff (lib + hook), and pytest (+ plugins) are
grouped so they bump together — this keeps `make check` green across each
MR rather than churning through three separate "ruff and ruff-pre-commit
are out of sync" failures.

**Alternative: Mend's hosted Renovate App.** If you'd rather not run
Renovate in CI, install the [Mend Renovate App for GitLab](https://docs.renovatebot.com/modules/platform/gitlab/)
and delete `.gitlab/ci/renovate.yml` plus the `maintenance` stage in
`.gitlab/ci/base.yml`. `renovate.json` is the same either way.

**Loosening / tightening:**

- More aggressive: set `"automerge": true` on the dev-dependencies group
  rule in `renovate.json` (after CI passes, Renovate merges the MR
  itself).
- Quieter: change `"schedule:weekly"` to `"schedule:monthly"`, or lower
  `prConcurrentLimit` / `prHourlyLimit`.
- Application (not library) mode: change `rangeStrategy` to `"bump"` so
  the `pyproject.toml` floor moves alongside the lockfile.

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
