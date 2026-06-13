
# Single source of truth for accepted-risk CVEs: an OpenVEX document.
# Trivy consumes it natively via `--vex`. `uv audit` does not yet,
# so we shim it through `scripts/py_audit_ignores_from_vex.py`, which emits
# `--ignore <ID>` flags for every `not_affected` / `fixed`
# statement. The shim writes to stdout only; `check_vex.py` is the
# enforcer (justification, controlled-vocab status, freshness window).
VEX_FILE := openvex.json
PY_AUDIT_IGNORES = $(shell uv run python scripts/py_audit_ignores_from_vex.py)
TRIVY_VEX_FLAG := --vex $(VEX_FILE)
PYTEST_REPORT_ARGS ?= --cov-report=xml

.DEFAULT_GOAL := help

# =============================================================================
# Help
# =============================================================================
#
# Every target's help comment is tagged with a [category]:
#   [setup]   one-time / environment setup
#   [check]   read-only verification (used by CI and pre-commit)
#   [fix]     auto-modifies files
#   [release] cuts a version locally via python-semantic-release
#   [meta]    introspection (help, version)
#   [cleanup] removes local state
#   [danger]  destructive; rendered last and in red
#
# `make help` groups output by category.

.PHONY: help
help:  ## [meta] Show this help message
	@echo "Makefile Commands"
	@echo "================="
	@printf "\n\033[1mSetup\033[0m\n"
	@grep -hE '^[a-zA-Z_-]+:.*?## \[setup\] ' $(MAKEFILE_LIST) | sort | \
		awk 'BEGIN {FS = ":.*?## \\[setup\\] "}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'
	@printf "\n\033[1mCheck (read-only, safe in CI / pre-commit)\033[0m\n"
	@grep -hE '^[a-zA-Z_-]+:.*?## \[check\] ' $(MAKEFILE_LIST) | sort | \
		awk 'BEGIN {FS = ":.*?## \\[check\\] "}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'
	@printf "\n\033[1mFix (modifies files)\033[0m\n"
	@grep -hE '^[a-zA-Z_-]+:.*?## \[fix\] ' $(MAKEFILE_LIST) | sort | \
		awk 'BEGIN {FS = ":.*?## \\[fix\\] "}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'
	@printf "\n\033[1mRelease\033[0m\n"
	@grep -hE '^[a-zA-Z_-]+:.*?## \[release\] ' $(MAKEFILE_LIST) | sort | \
		awk 'BEGIN {FS = ":.*?## \\[release\\] "}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'
	@printf "\n\033[1mOther\033[0m\n"
	@grep -hE '^[a-zA-Z_-]+:.*?## \[(meta|cleanup)\] ' $(MAKEFILE_LIST) | sort | \
		awk 'BEGIN {FS = ":.*?## \\[[a-z]+\\] "}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'
	@printf "\n"
	@grep -hE '^[a-zA-Z_-]+:.*?## \[danger\] ' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## \\[danger\\] "}; {printf "  \033[31m%-20s\033[0m %s\n", $$1, $$2}'

# ============================================================================
# Setup and Installation
# ============================================================================

# `bootstrap` is the single command a fresh clone needs to be productive.
# On the very first run it also executes `scripts/bootstrap_template.py`,
# which renames the placeholder package to one derived from the directory
# name (or whatever the user types at the prompt). That script self-deletes
# afterwards — re-running `make bootstrap` later just (re)installs deps and
# pre-commit hooks, which is what you usually want.
.PHONY: bootstrap
bootstrap:  ## [setup] One-time project init (template rename, on first run) + dev environment setup
	@if [ -f scripts/bootstrap_template.py ]; then \
		uv run --no-project --script scripts/bootstrap_template.py; \
	fi
	uv python install $$(cat .python-version)
	$(MAKE) install-dev
	$(MAKE) pre-commit-install

.PHONY: install
install:  ## [setup] Install only production dependencies
	uv sync

.PHONY: install-dev
install-dev:  ## [setup] Install production + development dependencies
	uv sync --dev

.PHONY: pre-commit-install
pre-commit-install:  ## [setup] Install pre-commit hooks
	uv run pre-commit install

# =============================================================================
# Check targets (read-only — used by CI and pre-commit)
# =============================================================================

.PHONY: format-check
format-check:  ## [check] Check code formatting (no changes)
	uv run ruff format --check .

.PHONY: lint-check
lint-check:  ## [check] Run linter without auto-fixing
	uv run ruff check .

.PHONY: type-check
type-check:  ## [check] Type check with ty
	uv run ty check

.PHONY: docstring-check
docstring-check:  ## [check] Check docstring coverage
	uv run interrogate -v

.PHONY: spell-check
spell-check:  ## [check] Spell-check code and docs with codespell
	uv run pre-commit run codespell --all-files

.PHONY: shell-check
shell-check:  ## [check] Lint shell scripts with shellcheck
	uv run pre-commit run shellcheck --all-files

# `dockerfile-check` runs hadolint via Docker and is therefore excluded from
# `make check` — we don't want the CI/pre-push aggregate to require a running
# Docker daemon. Pre-commit's `hadolint-docker` hook already runs it when a
# Dockerfile is staged; this target is for manual / explicit runs.
.PHONY: dockerfile-check
dockerfile-check:  ## [check] Lint Dockerfile with hadolint (requires Docker; opt-in)
	uv run pre-commit run hadolint-docker --all-files

.PHONY: repo-check
repo-check:  ## [check] Run repository hygiene checks from pre-commit
	uv run pre-commit run check-yaml --all-files
	uv run pre-commit run check-toml --all-files
	uv run pre-commit run check-json --all-files
	uv run pre-commit run check-added-large-files --all-files
	uv run pre-commit run check-case-conflict --all-files
	uv run pre-commit run check-merge-conflict --all-files
	uv run pre-commit run check-executables-have-shebangs --all-files
	uv run pre-commit run check-shebang-scripts-are-executable --all-files
	uv run pre-commit run debug-statements --all-files
	$(MAKE) vex-check


.PHONY: vex-check
vex-check:  ## [check] Enforce OpenVEX policy (schema + local freshness 180-day window / impact_statement)
	uv run pre-commit run vex-schema --all-files
	uv run pre-commit run vex-freshness --all-files

.PHONY: py-audit
py-audit:  ## [check] Audit python dependencies for known vulnerabilities (VEX-suppressed)
	uv audit --locked --output-format json $(PY_AUDIT_IGNORES)

.PHONY: find-secrets
find-secrets:  ## [check] Scan for secrets with gitleaks (uses .gitleaks.toml)
	uv run pre-commit run gitleaks

# Produces sbom.cdx.json —> CycloneDX inventory of every component in the
# uv project. Mirror of the CI `sbom:` job for local use.
.PHONY: sbom
sbom:  ## [check] Generate a CycloneDX SBOM at sbom.cdx.json (opt-in)
	uv export --format cyclonedx1.5 --locked --output-file sbom.cdx.json

.PHONY: trivy
trivy:  ## [check] Scan for vulnerabilities with trivy (uses trivy.yaml + VEX; slow, opt-in)
	docker run --rm -v "$(PWD):/repo" -w /repo ghcr.io/aquasecurity/trivy:latest \
		fs $(TRIVY_VEX_FLAG) .

# `trivy-full` is the informational counterpart of `trivy`: all severities,
# dev deps included, never blocks.
.PHONY: trivy-full
trivy-full:  ## [check] Trivy scan at all severities incl. dev deps (informational; opt-in)
	docker run --rm -v "$(PWD):/repo" -w /repo ghcr.io/aquasecurity/trivy:latest \
		fs --severity LOW,MEDIUM,HIGH,CRITICAL --exit-code 0 --include-dev-deps \
		$(TRIVY_VEX_FLAG) .

# Image-level vuln scan. Local counterpart of the CI `trivy-image:` job.
# Builds the project image, then scans it with Trivy + `openvex.json`.
.PHONY: trivy-image
trivy-image:  ## [check] Build this project's image and scan with trivy + openvex.json
	uv run python scripts/trivy_image_local.py

.PHONY: test
test:  ## [check] Run tests with pytest
	uv run pytest

.PHONY: test-cov
test-cov:  ## [check] Run tests with coverage report
	uv run pytest --cov --cov-report=term-missing $(PYTEST_REPORT_ARGS)

# `check` is the aggregate the CI pipeline and pre-commit can rely on.
# Docker-dependent targets (`trivy`, `trivy-full`, `trivy-image`, `dockerfile-check`)
# are intentionally excluded so `make check` runs without a Docker daemon.
# pre-commit's `hadolint-docker` hook covers Dockerfile linting on changes;
# the trivy targets are opt-in and slow (vuln DB download).
.PHONY: check
check: repo-check format-check lint-check type-check docstring-check spell-check shell-check test-cov py-audit find-secrets  ## [check] Run the full local check suite (no file changes)

# =============================================================================
# Fix targets (modify files — run locally before committing)
# =============================================================================

.PHONY: format
format:  ## [fix] Format code (ruff)
	uv run ruff format .

.PHONY: lint
lint:  ## [fix] Lint and auto-fix issues (ruff)
	uv run ruff check --fix .

.PHONY: repo-fix
repo-fix:  ## [fix] Auto-fix whitespace and end-of-file issues
	uv run pre-commit run trailing-whitespace --all-files || true
	uv run pre-commit run end-of-file-fixer --all-files || true

# `fix` runs every auto-fixer the project knows about
.PHONY: fix
fix: format lint repo-fix  ## [fix] Run every auto-fixer (format + lint + repo-fix)

# =============================================================================
# Release (local; CI uses .gitlab/ci/release.yml)
# =============================================================================
#
# `make release` bumps the version, regenerates CHANGELOG.md, tags, 
# but does NOT push. All based on conventional commits since the last
# tag. Settings live under `[tool.semantic_release]` in pyproject.toml.
#
# `make release-dry` previews the bump without touching the working tree or
# remote. Run it first.

.PHONY: release-dry
release-dry:  ## [release] Preview the next version bump (no commits, no tags, no push)
	uv run semantic-release --noop version

.PHONY: release
release:  ## [release] Create a new version locally (no push)
	uv run semantic-release version --no-push

# =============================================================================
# Misc
# =============================================================================

.PHONY: version
version:  ## [meta] Show current version
	@uv run python -c "import tomllib; print(tomllib.load(open('pyproject.toml', 'rb'))['project']['version'])"

# =============================================================================
# Cleanup
# =============================================================================

.PHONY: clean
clean:  ## [cleanup] Remove local build, test, and cache artifacts
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
	find . -type f -name "*.pyo" -delete
	find . -type d -name "*.egg-info" -exec rm -rf {} +
	find . -type f -name "*.log" -delete
	rm -rf .cache .hypothesis .nox .pytest_cache .ruff_cache .tox
	rm -rf .uv-cache .eggs build dist htmlcov sdist
	rm -f .coverage coverage.xml report.xml release.env sbom.cdx.json

.PHONY: clean-all
clean-all: clean  ## [cleanup] Remove cache files and virtual environment
	rm -rf .venv/

# `teardown` is the inverse of `bootstrap`'s *environment* setup only — it
# removes the venv, pre-commit hook, and pinned Python toolchain.
.PHONY: teardown
teardown:  ## [danger] Remove dev environment (venv, pre-commit hook, pinned Python).
	uv run pre-commit uninstall
# clean-all needs to run after "pre-commit uninstall" because uv creates .venv when "pre-commit uninstall" runs
	$(MAKE) clean-all
	uv python uninstall $$(cat .python-version)
