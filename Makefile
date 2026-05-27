PY=uv

# Single source of truth for accepted-risk CVEs: an OpenVEX document.
# Trivy consumes it natively via `--vex`. `pip-audit` does not yet
# (https://github.com/pypa/pip-audit/issues/231), so we shim it through
# `scripts/pip_audit_ignores_from_vex.py`, which emits
# `--ignore-vuln <ID>` flags for every `not_affected` / `fixed`
# statement. The shim writes to stdout only; `check_vex.py` is the
# enforcer (justification, controlled-vocab status, freshness window).
VEX_FILE := openvex.json
PIP_AUDIT_IGNORES := $(shell python3 scripts/pip_audit_ignores_from_vex.py)
TRIVY_VEX_FLAG := --vex $(VEX_FILE)

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
		$(PY) run --no-project --script scripts/bootstrap_template.py; \
	fi
	$(PY) python install $$(cat .python-version)
	$(MAKE) install-dev
	$(MAKE) pre-commit-install

.PHONY: install
install:  ## [setup] Install only production dependencies
	$(PY) sync

.PHONY: install-dev
install-dev:  ## [setup] Install production + development dependencies
	$(PY) sync --dev

.PHONY: pre-commit-install
pre-commit-install:  ## [setup] Install pre-commit hooks
	$(PY) run pre-commit install

# =============================================================================
# Check targets (read-only — used by CI and pre-commit)
# =============================================================================

.PHONY: format-check
format-check:  ## [check] Check code formatting (no changes)
	$(PY) run ruff format --check .

.PHONY: lint-check
lint-check:  ## [check] Run linter without auto-fixing
	$(PY) run ruff check .

.PHONY: type-check
type-check:  ## [check] Type check with ty
	$(PY) run ty check

.PHONY: docstring-check
docstring-check:  ## [check] Check docstring coverage
	$(PY) run interrogate -v

.PHONY: spell-check
spell-check:  ## [check] Spell-check code and docs with codespell
	$(PY) run pre-commit run codespell --all-files

.PHONY: shell-check
shell-check:  ## [check] Lint shell scripts with shellcheck
	$(PY) run pre-commit run shellcheck --all-files

# `dockerfile-check` runs hadolint via Docker and is therefore excluded from
# `make check` — we don't want the CI/pre-push aggregate to require a running
# Docker daemon. Pre-commit's `hadolint-docker` hook already runs it when a
# Dockerfile is staged; this target is for manual / explicit runs.
.PHONY: dockerfile-check
dockerfile-check:  ## [check] Lint Dockerfile with hadolint (requires Docker; opt-in)
	$(PY) run pre-commit run hadolint-docker --all-files

.PHONY: repo-check
repo-check:  ## [check] Run repository hygiene checks from pre-commit
	$(PY) run pre-commit run check-yaml --all-files
	$(PY) run pre-commit run check-toml --all-files
	$(PY) run pre-commit run check-json --all-files
	$(PY) run pre-commit run check-added-large-files --all-files
	$(PY) run pre-commit run check-case-conflict --all-files
	$(PY) run pre-commit run check-merge-conflict --all-files
	$(PY) run pre-commit run check-executables-have-shebangs --all-files
	$(PY) run pre-commit run check-shebang-scripts-are-executable --all-files
	$(PY) run pre-commit run debug-statements --all-files
	$(MAKE) vex-check


.PHONY: vex-check
vex-check:  ## [check] Enforce OpenVEX policy (schema + local freshness 180-day window / impact_statement)
	$(PY) run pre-commit run vex-schema --all-files
	$(PY) run pre-commit run vex-freshness --all-files

.PHONY: audit
audit:  ## [check] Audit dependencies for known vulnerabilities (VEX-suppressed)
	$(PY) run pip-audit $(PIP_AUDIT_IGNORES)

.PHONY: find-secrets
find-secrets:  ## [check] Scan for secrets with gitleaks (uses .gitleaks.toml)
	$(PY) run pre-commit run gitleaks --all-files

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

# Produces sbom.cdx.json —> CycloneDX inventory of every component in the
# repo. Mirror of the CI `sbom:` job for local use.
.PHONY: sbom
sbom:  ## [check] Generate a CycloneDX SBOM at sbom.cdx.json (opt-in)
	docker run --rm -v "$(PWD):/repo" -w /repo ghcr.io/aquasecurity/trivy:latest \
		fs --format cyclonedx --output sbom.cdx.json --quiet .

# Image-level vuln scan. Local counterpart of the CI `trivy-image:` job.
# Builds the project image, then scans it with Trivy + `openvex.json`.
.PHONY: trivy-image
trivy-image:  ## [check] Build this project's image and scan with trivy + openvex.json
	$(PY) run python scripts/trivy_image_local.py

# Verify a released image's Sigstore signature. Thin wrapper around
# `scripts/verify_image.py`, which reads the platform + host from
# `[tool.semantic_release.remote]` in pyproject.toml —> no duplication of
# "what platform are we on" config across files. For tighter cert pinning
# in automated gates, invoke the script directly with `--project <group/repo>`.
.PHONY: verify-image
verify-image:  ## [check] Verify cosign signature of a released image. Usage: make verify-image IMAGE=<ref>
	@if [ -z "$(IMAGE)" ]; then \
		echo "Usage: make verify-image IMAGE=<registry/path>:<tag-or-digest>" >&2; \
		echo "       For automated deploy gates, invoke the script directly:" >&2; \
		echo "         python scripts/verify_image.py --project <group/repo> <IMAGE>" >&2; \
		exit 1; \
	fi
	$(PY) run python scripts/verify_image.py "$(IMAGE)"

.PHONY: test
test:  ## [check] Run tests with pytest
	$(PY) run pytest

.PHONY: test-cov
test-cov:  ## [check] Run tests with coverage report
	$(PY) run pytest --cov --cov-report=term-missing --cov-report=xml

# `check` is the aggregate the CI pipeline and pre-commit can rely on.
# Docker-dependent targets (`trivy`, `trivy-full`, `trivy-image`, `sbom`, `dockerfile-check`)
# are intentionally excluded so `make check` runs without a Docker daemon.
# pre-commit's `hadolint-docker` hook covers Dockerfile linting on changes;
# the trivy/sbom targets are opt-in and slow (vuln DB download).
.PHONY: check
check: repo-check format-check lint-check type-check docstring-check spell-check shell-check test-cov audit find-secrets  ## [check] Run the full local check suite (no file changes)

# =============================================================================
# Fix targets (modify files — run locally before committing)
# =============================================================================

.PHONY: format
format:  ## [fix] Format code (ruff)
	$(PY) run ruff format .

.PHONY: lint
lint:  ## [fix] Lint and auto-fix issues (ruff)
	$(PY) run ruff check --fix .

.PHONY: repo-fix
repo-fix:  ## [fix] Auto-fix whitespace and end-of-file issues
	$(PY) run pre-commit run trailing-whitespace --all-files || true
	$(PY) run pre-commit run end-of-file-fixer --all-files || true

# `fix` runs every auto-fixer the project knows about
.PHONY: fix
fix: format lint repo-fix  ## [fix] Run every auto-fixer (format + lint + repo-fix)

# =============================================================================
# Release (local; CI uses scripts/release.sh)
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
	$(PY) run semantic-release --noop version

.PHONY: release
release:  ## [release] Cut a new version locally (no push)
	$(PY) run semantic-release version --no-push

# =============================================================================
# Misc
# =============================================================================

.PHONY: version
version:  ## [meta] Show current version
	@$(PY) run python -c "import tomllib; print(tomllib.load(open('pyproject.toml', 'rb'))['project']['version'])"

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
	$(PY) run pre-commit uninstall
# clean-all needs to run after "pre-commit uninstall" because uv creates .venv when "pre-commit uninstall" runs
	$(MAKE) clean-all
	$(PY) python uninstall $$(cat .python-version)
